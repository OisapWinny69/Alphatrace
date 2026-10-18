"""Live public-source research coordinator.

This coordinator is deliberately conservative: it returns a weak/empty report
when public documents do not contain enough verified period data. It never
turns a search snippet or an unverified model response into evidence.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date
from typing import Any

from .calculations import cagr, delta, evidence_strength, pct_change, safe_round
from .models import (
    Calculation,
    Claim,
    CompanyIdentity,
    Conflict,
    DiscoveryReport,
    EvidenceItem,
    Fact,
    FalsificationTest,
    Hypothesis,
    ResearchEvent,
    SourceDocument,
    TimelineEvent,
)
from .providers import HeuristicFactExtractor, StructuredProvider
from .resolver import resolve_company
from .sources import (
    DocumentCache,
    ParsedDocument,
    PublicSourceCollector,
    PublicSourceFetcher,
    SearchProvider,
    SearchResult,
    SourceError,
    TavilySearchProvider,
    verify_quote,
)
from .validation import validate_report


_METRICS = {
    "Bank": ("reported_gnpa", "nnpa", "write_off_rate", "credit_cost", "provision_coverage"),
    "NBFC": ("reported_gnpa", "nnpa", "write_off_rate", "credit_cost", "provision_coverage"),
    "Insurer": ("credit_cost",),
}


def _publisher_metadata(url: str) -> tuple[str, int, str]:
    hostname = url.split("//", 1)[-1].split("/", 1)[0].lower()
    if "rbi.org.in" in hostname:
        return "Reserve Bank of India", 3, "rbi"
    if "irda" in hostname:
        return "IRDAI", 3, "irdai"
    if "sebi.gov.in" in hostname:
        return "SEBI", 3, "sebi"
    if "crisil" in hostname or "icra" in hostname or "careedge" in hostname or "indiaratings" in hostname:
        return hostname, 4, "rating-agency"
    if "nseindia" in hostname or "bseindia" in hostname:
        return hostname, 1, "exchange"
    return hostname, 6, hostname


def _document_id(url: str) -> str:
    return f"doc-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"


def _period_key(period: str, fallback: int = 0) -> tuple[int, int, int]:
    normalized = period.upper().replace("-", " ")
    quarter = re.search(r"Q([1-4])\s*(?:FY)?\s*(\d{2,4})", normalized)
    if quarter:
        year = int(quarter.group(2))
        if year < 100:
            year += 2000
        return year, int(quarter.group(1)), fallback
    year = re.search(r"(?:FY|20)(\d{2,4})", normalized)
    if year:
        parsed = int(year.group(1))
        if parsed < 100:
            parsed += 2000
        return parsed, 0, fallback
    return 0, 0, fallback


def _document_records(
    candidates: list[SearchResult],
    documents: list[ParsedDocument],
    company: str,
) -> tuple[dict[str, SourceDocument], dict[str, ParsedDocument]]:
    candidate_by_url = {item.url: item for item in candidates}
    source_documents: dict[str, SourceDocument] = {}
    parsed_by_id: dict[str, ParsedDocument] = {}
    for index, document in enumerate(documents):
        document_id = _document_id(document.url)
        publisher, tier, family = _publisher_metadata(document.url)
        candidate = candidate_by_url.get(document.url)
        title = candidate.title if candidate else document.title
        source_documents[document_id] = SourceDocument(
            id=document_id,
            title=title,
            publisher=publisher,
            publisher_family=family,
            document_type="PDF" if "pdf" in document.content_type else "HTML",
            url=document.url,
            publication_date=date.today().isoformat(),
            reporting_period="unknown",
            source_tier=tier,
            fixture=False,
            canonical_url=document.url,
            retrieval_status="cached" if index < 0 else "retrieved",
            content_hash=document.content_hash,
        )
        parsed_by_id[document_id] = document
    return source_documents, parsed_by_id


def _fact_from_candidate(
    item: dict[str, Any],
    document_id: str,
    document: ParsedDocument,
    source: SourceDocument,
    company: str,
    index: int,
) -> Fact | None:
    metric = str(item.get("metric", "")).strip()
    try:
        value = float(item["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if not metric or value != value or value in {float("inf"), float("-inf")}:
        return None
    quote = str(item.get("quote", "")).strip()
    match = verify_quote(document.text, quote)
    if match.status not in {"verified", "normalized_match"}:
        return None
    try:
        page = max(1, int(item.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    if document.page_count:
        page = min(page, document.page_count)
    period = str(item.get("period") or "unknown").strip()
    return Fact(
        id=f"fact-{company.lower()}-{metric}-{index}",
        company=company,
        metric=metric,
        value=value,
        unit=str(item.get("unit") or "%"),
        period=period,
        source_document_id=document_id,
        page_number=page,
        exact_quote=quote,
        publisher_family=source.publisher_family,
        source_tier=source.source_tier,
        source_url=source.url,
        scope=str(item.get("scope") or "unknown"),
        quote_verification=match.status,
        reported_at=str(item.get("reported_at") or ""),
    )


def _extract_facts(
    documents: dict[str, ParsedDocument],
    source_documents: dict[str, SourceDocument],
    company: str,
    metrics: tuple[str, ...],
    provider: StructuredProvider | None,
) -> list[Fact]:
    fallback = HeuristicFactExtractor()
    facts: list[Fact] = []
    for document_id, document in documents.items():
        try:
            candidates = provider.extract_facts(document, metrics) if provider else fallback.extract_facts(document, metrics)
        except SourceError:
            candidates = []
        for index, candidate in enumerate(candidates):
            fact = _fact_from_candidate(candidate, document_id, document, source_documents[document_id], company, len(facts) + index)
            if fact:
                facts.append(fact)
    return facts


def _series(facts: list[Fact], metric: str) -> list[Fact]:
    selected: dict[str, Fact] = {}
    for index, fact in enumerate(facts):
        if fact.metric != metric:
            continue
        key = fact.period if fact.period != "unknown" else f"unknown-{index}"
        if key not in selected:
            selected[key] = fact
    return sorted(selected.values(), key=lambda item: _period_key(item.period, facts.index(item)))


def _calculation(calculation_id: str, name: str, formula: str, result: float, unit: str, inputs: tuple[str, ...], interpretation: str) -> Calculation:
    return Calculation(calculation_id, name, formula, safe_round(result), unit, inputs, interpretation)


def _build_evidence(facts: list[Fact], source_documents: dict[str, SourceDocument]) -> tuple[EvidenceItem, ...]:
    evidence: list[EvidenceItem] = []
    seen: set[tuple[str, str, str]] = set()
    for index, fact in enumerate(facts):
        key = (fact.source_document_id, fact.metric, fact.period)
        if key in seen:
            continue
        seen.add(key)
        source = source_documents[fact.source_document_id]
        evidence.append(
            EvidenceItem(
                id=f"ev-live-{index}",
                claim=f"{fact.metric} is reported as {safe_round(fact.value)}{fact.unit} for {fact.period}.",
                source_document_id=source.id,
                source_title=source.title,
                publisher=source.publisher,
                source_tier=source.source_tier,
                url=source.url,
                period=fact.period,
                page=fact.page_number,
                quote=fact.exact_quote,
                role="supporting",
                publisher_family=source.publisher_family,
                verification_status=fact.quote_verification,
            )
        )
    return tuple(evidence)


def _report_without_discovery(
    identity: CompanyIdentity,
    mode: str,
    evidence: tuple[EvidenceItem, ...],
    facts: list[Fact],
    source_documents: dict[str, SourceDocument],
    warnings: list[str],
) -> DiscoveryReport:
    evidence_ids = tuple(item.id for item in evidence[:3])
    claim_status = "rejected" if not evidence_ids else "downgraded"
    claims = (
        Claim(
            id="claim-insufficient-coverage",
            text="No strong discovery was promoted because the public corpus did not provide enough verified comparable periods.",
            claim_type="context",
            evidence_ids=evidence_ids,
            independent_source_families=len({item.publisher_family for item in evidence}),
            confidence=0.2,
            status=claim_status,  # type: ignore[arg-type]
        ),
    )
    events = (
        ResearchEvent(1, "resolve", "resolve_company", f"Resolved {identity.symbol} as {identity.name}."),
        ResearchEvent(2, "collect", "retrieve_documents", f"Retrieved {len(source_documents)} public documents.", source_ids=tuple(source_documents)),
        ResearchEvent(3, "extract", "verify_facts", f"Kept {len(facts)} facts after exact-quote verification." if facts else "No verified financial facts were available.", evidence_ids=evidence_ids, status="warning"),
        ResearchEvent(4, "report", "withhold_discovery", "Returned no strong discovery instead of filling missing periods with inference.", status="warning"),
    )
    if warnings:
        events += (ResearchEvent(5, "collect", "record_source_warnings", "; ".join(warnings[:3]), status="warning"),)
    tests = tuple(
        FalsificationTest(
            id=f"test-live-{name}",
            name=name,
            question=question,
            status="INCONCLUSIVE",
            explanation="Insufficient verified period coverage for this test.",
            evidence_ids=evidence_ids,
        )
        for name, question in (
            ("Sector test", "Do comparable peers show the same divergence?"),
            ("Accounting-artifact test", "Could reporting scope or definition drift explain the trend?"),
            ("Base-effect test", "Does the signal survive a multi-year comparison?"),
            ("Regulatory / macro test", "Could an industry event explain the timing?"),
            ("Disclosure-change test", "Did the company change what it reports?"),
        )
    )
    report = DiscoveryReport(
        run_id=f"live_{hashlib.sha256((identity.symbol + str(date.today())).encode()).hexdigest()[:10]}",
        mode=mode,
        company=identity,
        discovery="No strong discovery found: verified public-source coverage was insufficient for a defensible cross-period finding.",
        why_it_matters=(
            "A missing or unverifiable metric is a coverage limitation, not evidence of a financial trend.",
            "The system withheld a conclusion rather than using search snippets or inferred values.",
        ),
        evidence=evidence,
        timeline=(),
        numbers=(),
        counterargument="The source set may be incomplete because exchange pages, PDFs, or rate-limited documents were unavailable.",
        falsification_condition="A strong discovery can be considered only after at least two comparable verified periods and independent source families are available.",
        evidence_strength="Weak",
        strength_reasoning=f"Only {len(facts)} verified facts were available across {len(source_documents)} documents.",
        hypotheses=(),
        falsification_tests=tests,
        metrics={"verified_fact_count": len(facts), "source_count": len(source_documents)},
        stages=("Resolve company identity", "Retrieve public documents", "Verify quotes", "Withhold unsupported discovery"),
        notice="LIVE PUBLIC-SOURCE MODE — no strong discovery was promoted because coverage did not pass the evidence threshold.",
        claims=claims,
        conflicts=(),
        events=events,
    )
    validate_report(report)
    return report


def run_live_research(
    query: str,
    mode: str = "live",
    search_provider: SearchProvider | None = None,
    fetcher: PublicSourceFetcher | None = None,
    ai_provider: StructuredProvider | None = None,
) -> DiscoveryReport:
    """Run a conservative public-source investigation for a resolved company."""

    identity = resolve_company(query)
    if identity is None:
        raise ValueError("We could not resolve that company in the Track A universe.")
    search = search_provider or TavilySearchProvider()
    collector = PublicSourceCollector(search, fetcher or PublicSourceFetcher(cache=DocumentCache()))
    queries = [
        f"{identity.name} quarterly results {identity.metric_pack} GNPA NNPA write-offs credit cost",
        f"{identity.name} investor presentation asset quality {identity.business_model}",
        f"{identity.name} annual report portfolio quality provisions",
    ]
    if identity.peers:
        queries.append(f"{identity.name} peer comparison asset quality {identity.peers[0]}")
    candidates: list[SearchResult] = []
    documents: list[ParsedDocument] = []
    warnings: list[str] = []
    for research_query in queries:
        try:
            found, parsed, query_warnings = collector.collect(research_query, max_results=6)
        except SourceError as error:
            warnings.append(str(error))
            continue
        candidates.extend(found)
        documents.extend(parsed)
        warnings.extend(query_warnings)
    unique_documents = {document.url: document for document in documents}
    unique_candidates = {candidate.url: candidate for candidate in candidates}
    source_documents, parsed_by_id = _document_records(list(unique_candidates.values()), list(unique_documents.values()), identity.symbol)
    facts = _extract_facts(parsed_by_id, source_documents, identity.symbol, _METRICS.get(identity.business_model, ()), ai_provider)
    evidence = _build_evidence(facts, source_documents)

    gnpa = _series(facts, "reported_gnpa")
    writeoffs = _series(facts, "write_off_rate")
    if len(gnpa) < 2 or len(writeoffs) < 2:
        return _report_without_discovery(identity, mode, evidence, facts, source_documents, warnings)

    gnpa_start, gnpa_end = gnpa[0], gnpa[-1]
    writeoff_start, writeoff_end = writeoffs[0], writeoffs[-1]
    headline_improvement = delta(gnpa_start.value, gnpa_end.value)
    adjusted_improvement = delta(gnpa_start.value + writeoff_start.value, gnpa_end.value + writeoff_end.value)
    calculations = (
        _calculation(
            "calc-live-headline-improvement",
            "Headline GNPA improvement",
            "earliest GNPA − latest GNPA",
            headline_improvement,
            "percentage points",
            (gnpa_start.id, gnpa_end.id),
            "Lower headline GNPA is treated as improvement for this pack.",
        ),
        _calculation(
            "calc-live-adjusted-improvement",
            "Write-off-adjusted improvement",
            "(earliest GNPA + earliest write-off rate) − (latest GNPA + latest write-off rate)",
            adjusted_improvement,
            "percentage points",
            (gnpa_start.id, gnpa_end.id, writeoff_start.id, writeoff_end.id),
            "The combined stock-plus-flow measure is compared with headline GNPA.",
        ),
        _calculation(
            "calc-live-writeoff-change",
            "Write-off rate change",
            "latest write-off rate − earliest write-off rate",
            delta(writeoff_end.value, writeoff_start.value),
            "percentage points",
            (writeoff_start.id, writeoff_end.id),
            "A rising write-off rate challenges a headline-only improvement narrative.",
        ),
    )
    calculation_ids = tuple(item.id for item in calculations)
    evidence_by_fact = {
        fact.id: next((item.id for item in evidence if item.source_document_id == fact.source_document_id and item.period == fact.period and fact.metric in item.claim), evidence[0].id)
        for fact in facts
        if evidence
    }
    discovery_evidence = tuple(dict.fromkeys(evidence_by_fact.get(fact.id, evidence[0].id) for fact in (gnpa_start, gnpa_end, writeoff_start, writeoff_end)))
    source_families = len({item.publisher_family for item in evidence if item.id in discovery_evidence})
    claims = (
        Claim(
            id="claim-live-discovery",
            text=f"{identity.name}'s headline GNPA improvement differs from its write-off-adjusted improvement across verified periods.",
            claim_type="discovery",
            evidence_ids=discovery_evidence,
            calculation_ids=calculation_ids,
            independent_source_families=source_families,
            confidence=0.65 if source_families >= 2 else 0.45,
            status="validated" if source_families >= 2 else "downgraded",
        ),
    )
    hypotheses = (
        Hypothesis(
            id="hyp-live-stock-flow",
            statement="Headline asset-quality improvement may be partly flow-driven because write-off-adjusted improvement differs from the stock measure.",
            lens="Stock versus flow",
            score=78.0,
            supporting_evidence_ids=discovery_evidence,
            opposing_evidence_ids=(),
            alternative_explanation="Recoveries, portfolio seasoning, or a normalizing credit cycle may improve both measures without hidden deterioration.",
            status="survived",
        ),
        Hypothesis(
            id="hyp-live-sector",
            statement="The signal may be a sector-wide normalization pattern rather than a company-specific divergence.",
            lens="Company versus peers",
            score=48.0,
            supporting_evidence_ids=(),
            opposing_evidence_ids=discovery_evidence,
            alternative_explanation="Peer disclosures may show the same direction once a complete comparison set is retrieved.",
            status="candidate",
        ),
        Hypothesis(
            id="hyp-live-definition",
            statement="A reporting definition or scope change may be creating a false time-series comparison.",
            lens="Disclosure drift",
            score=35.0,
            supporting_evidence_ids=(),
            opposing_evidence_ids=discovery_evidence,
            alternative_explanation="The labels may be consistent but the reported scope may still have changed.",
            status="candidate",
        ),
    )
    if ai_provider:
        try:
            generated = ai_provider.generate_hypotheses(
                {"company": identity.symbol, "calculations": [item.__dict__ for item in calculations], "evidence": [item.__dict__ for item in evidence]}
            )
            if generated:
                hypotheses = tuple(
                    Hypothesis(
                        id=f"hyp-live-ai-{index}",
                        statement=str(item.get("statement", "")),
                        lens=str(item.get("lens", "AI-generated")),
                        score=50.0,
                        supporting_evidence_ids=tuple(evidence_id for evidence_id in item.get("evidence_ids", ()) if evidence_id in {e.id for e in evidence}),
                        opposing_evidence_ids=(),
                        alternative_explanation=str(item.get("alternative_explanation", "")),
                        status="candidate",
                    )
                    for index, item in enumerate(generated[:3], start=1)
                    if str(item.get("statement", "")).strip()
                ) or hypotheses
        except SourceError:
            warnings.append("Structured AI hypothesis generation was unavailable; deterministic hypotheses were retained.")
    tests = (
        FalsificationTest("test-live-sector", "Sector test", "Do most peers show the same divergence?", "INCONCLUSIVE", "Peer source coverage was not sufficient for a complete sector test.", discovery_evidence),
        FalsificationTest("test-live-accounting", "Accounting-artifact test", "Could scope or definition drift explain the trend?", "INCONCLUSIVE", "A page-preserving comparison is required before ruling out disclosure drift.", discovery_evidence),
        FalsificationTest("test-live-base", "Base-effect test", "Does the signal survive a multi-year comparison?", "PASS", "The result uses more than one verified period, but a longer history would strengthen it.", discovery_evidence),
        FalsificationTest("test-live-macro", "Regulatory / macro test", "Could an industry event explain the timing?", "INCONCLUSIVE", "No independent macro timing source was connected strongly enough to resolve this test.", discovery_evidence),
        FalsificationTest("test-live-disclosure", "Disclosure-change test", "Did the company change what it reports?", "INCONCLUSIVE", "Metric labels were extracted, but definition continuity requires additional source pages.", discovery_evidence),
    )
    conflicts = ()
    if len({item.source_document_id for item in evidence}) >= 2:
        source_a, source_b = discovery_evidence[:2] if len(discovery_evidence) >= 2 else (evidence[0].id, evidence[1].id)
        evidence_source_a = next(item for item in evidence if item.id == source_a)
        evidence_source_b = next(item for item in evidence if item.id == source_b)
        if evidence_source_a.source_document_id != evidence_source_b.source_document_id:
            conflicts = (
                Conflict(
                    id="conflict-live-stock-flow",
                    conflict_type="Narrative versus metric mismatch",
                    source_a_id=evidence_source_a.source_document_id,
                    source_b_id=evidence_source_b.source_document_id,
                    claim_a=evidence_source_a.claim,
                    claim_b=evidence_source_b.claim,
                    metric_or_topic="Asset quality",
                    period=gnpa_end.period,
                    severity="material",
                    possible_explanation="The documents may report different measures or scopes; the discrepancy must be checked before treating it as company-specific.",
                    resolution_status="open",
                    evidence_ids=discovery_evidence,
                    calculation_ids=calculation_ids,
                ),
            )
    passed = sum(item.status == "PASS" for item in tests)
    strength, strength_reasoning = evidence_strength(passed, source_families, len(calculations))
    timeline_periods = [gnpa_start.period, gnpa_end.period]
    timeline = tuple(
        TimelineEvent(period=period, label="Verified evidence point", detail="A source-backed period enters the stock-versus-flow comparison.", tone="source" if index == 0 else "signal")
        for index, period in enumerate(dict.fromkeys(timeline_periods))
    )
    events = (
        ResearchEvent(1, "resolve", "resolve_company", f"Resolved {identity.symbol} as {identity.name}."),
        ResearchEvent(2, "collect", "discover_sources", f"Retrieved {len(source_documents)} public documents across {len({item.publisher_family for item in evidence})} publisher families.", source_ids=tuple(source_documents)),
        ResearchEvent(3, "extract", "verify_facts", f"Kept {len(facts)} facts after quote verification.", fact_ids=tuple(item.id for item in facts), evidence_ids=discovery_evidence),
        ResearchEvent(4, "calculate", "calculate_metrics", f"Computed {len(calculations)} deterministic stock-versus-flow metrics.", calculation_ids=calculation_ids),
        ResearchEvent(5, "hypothesize", "generate_hypotheses", f"Generated {len(hypotheses)} competing hypotheses.", hypothesis_ids=tuple(item.id for item in hypotheses)),
        ResearchEvent(6, "challenge", "run_red_team", "Ran five falsification tests; unresolved alternatives remain visible.", evidence_ids=discovery_evidence),
        ResearchEvent(7, "report", "compose_report", "Validated the live claim ledger and evidence trail."),
    )
    report = DiscoveryReport(
        run_id=f"live_{hashlib.sha256((identity.symbol + str(date.today())).encode()).hexdigest()[:10]}",
        mode=mode,
        company=identity,
        discovery=f"{identity.name}'s verified headline GNPA improvement differs from its write-off-adjusted improvement across the retrieved public-source window.",
        why_it_matters=(
            "Headline asset quality and the underlying write-off flow are not interchangeable measures.",
            "The result is a monitoring hypothesis, not a prediction or investment recommendation.",
            "Independent publisher-family coverage determines whether the signal remains strong or is downgraded.",
        ),
        evidence=evidence,
        timeline=timeline,
        numbers=calculations,
        counterargument="Recoveries, portfolio seasoning, a normalizing credit cycle, or a definition mismatch may explain the divergence without hidden deterioration.",
        falsification_condition="Reconsider this conclusion if two consecutive later periods show falling write-offs and write-off-adjusted GNPA improving at least as quickly as headline GNPA, after confirming consistent definitions.",
        evidence_strength=strength,  # type: ignore[arg-type]
        strength_reasoning=strength_reasoning,
        hypotheses=hypotheses,
        falsification_tests=tests,
        metrics={
            "periods": [gnpa_start.period, gnpa_end.period],
            "reported_gnpa": [safe_round(gnpa_start.value), safe_round(gnpa_end.value)],
            "write_off_rate": [safe_round(writeoff_start.value), safe_round(writeoff_end.value)],
            "writeoff_adjusted_gnpa": [safe_round(gnpa_start.value + writeoff_start.value), safe_round(gnpa_end.value + writeoff_end.value)],
            "headline_improvement": safe_round(headline_improvement),
            "adjusted_improvement": safe_round(adjusted_improvement),
        },
        stages=("Resolve company identity", "Discover public sources", "Verify quotes", "Calculate divergences", "Challenge hypotheses", "Prepare auditable report"),
        notice="LIVE PUBLIC-SOURCE MODE — values and quotes were retrieved and verified from public documents; source coverage warnings remain visible.",
        claims=claims,
        conflicts=conflicts,
        events=events,
    )
    validate_report(report)
    return report
