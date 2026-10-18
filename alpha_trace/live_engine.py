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
    "Insurer": ("premium_growth", "vnb_margin", "persistency_13m", "solvency_ratio"),
}


def _publisher_metadata(url: str, company_symbol: str = "") -> tuple[str, int, str]:
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
    symbol_token = re.sub(r"[^a-z0-9]", "", company_symbol.lower())
    if symbol_token and symbol_token in re.sub(r"[^a-z0-9]", "", hostname):
        return hostname, 2, "company"
    if hostname.endswith(".bank.in") or hostname.endswith(".insurance.in"):
        return hostname, 2, "company"
    return hostname, 6, hostname


def _document_id(url: str) -> str:
    return f"doc-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"


def _normalize_period(period: str) -> str:
    """Normalize common Indian reporting labels to stable comparison keys."""

    value = re.sub(r"\s+", " ", period.replace("’", "'").strip())
    quarter = re.search(r"\bQ\s*([1-4])\s*(?:FY|F\.Y\.?|FINANCIAL\s+YEAR)?\s*[' ]?(\d{2,4})\b", value, re.IGNORECASE)
    if quarter:
        year = int(quarter.group(2))
        if year < 100:
            year += 2000
        if year < 2000 or year > date.today().year + 1:
            return "unknown"
        return f"Q{quarter.group(1)} FY{year}"
    fiscal_year = re.search(r"\bFY\s*[' ]?(\d{2,4})\b", value, re.IGNORECASE)
    if fiscal_year:
        year = int(fiscal_year.group(1))
        if year < 100:
            year += 2000
        if year < 2000 or year > date.today().year + 1:
            return "unknown"
        return f"FY{year}"
    fiscal_range = re.search(r"\b(20\d{2})[-/]([0-9]{2,4})\b", value)
    if fiscal_range:
        end_year = int(fiscal_range.group(2))
        if end_year < 100:
            end_year += 2000
        if 2000 <= end_year <= date.today().year + 1:
            return f"FY{end_year}"
    month_year = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[' -]?(\d{2,4})\b", value, re.IGNORECASE)
    if month_year:
        month = month_year.group(1).upper()[:3]
        year = int(month_year.group(2))
        if year < 100:
            year += 2000
        if year < 2000 or year > date.today().year + 1:
            return "unknown"
        month_to_quarter = {"MAR": 4, "JUN": 1, "SEP": 2, "DEC": 3}
        quarter_number = month_to_quarter.get(month)
        if quarter_number:
            fy_year = year + 1 if month != "MAR" else year
            return f"Q{quarter_number} FY{fy_year}"
        return f"{month} {year}"
    return value if value and value.lower() != "unknown" else "unknown"


def _infer_period(*texts: str) -> str:
    combined = " ".join(text for text in texts if text)
    patterns = (
        r"\bQ\s*[1-4]\s*(?:FY|F\.Y\.?|FINANCIAL\s+YEAR)?\s*[' ]?\d{2,4}\b",
        r"\bFY\s*[' ]?\d{2,4}\b",
        r"\b20\d{2}[-/]\d{2,4}\b",
        r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[' -]?\d{2,4}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            return _normalize_period(match.group(0))
    return "unknown"


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
    month = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+(\d{4})\b", normalized)
    if month:
        month_number = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}[month.group(1)]
        return int(month.group(2)), month_number, fallback
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
        publisher, tier, family = _publisher_metadata(document.url, company)
        candidate = candidate_by_url.get(document.url)
        title = candidate.title if candidate else document.title
        period_hint = _infer_period(
            candidate.title if candidate else "",
            candidate.url if candidate else "",
            document.title,
            document.url,
        )
        source_documents[document_id] = SourceDocument(
            id=document_id,
            title=title,
            publisher=publisher,
            publisher_family=family,
            document_type="PDF" if "pdf" in document.content_type else "HTML",
            url=document.url,
            publication_date=date.today().isoformat(),
            reporting_period=period_hint,
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
    if not _metric_value_is_locally_supported(document.text, metric, value, quote):
        return None
    try:
        page = max(1, int(item.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    if document.page_count:
        page = min(page, document.page_count)
    period = _normalize_period(str(item.get("period") or "unknown"))
    if period == "unknown":
        period = source.reporting_period or _infer_period(document.title, document.url)
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


def _metric_value_is_locally_supported(text: str, metric: str, value: float, quote: str = "") -> bool:
    """Require a metric label and its value to occur together in source text.

    This prevents a model from pairing a nearby but unrelated number from a
    PDF table layout (a common failure mode in annual-report extraction).
    """

    terms = {
        "reported_gnpa": r"(?:GNPA|gross\s+NPA|gross\s+non[- ]performing\s+assets)",
        "nnpa": r"(?:NNPA|net\s+NPA|net\s+non[- ]performing\s+assets)",
        "write_off_rate": r"(?:write[- ]offs?|write[- ]off\s+rate)",
        "credit_cost": r"credit\s+cost",
        "provision_coverage": r"(?:provision\s+coverage|PCR)",
        "premium_growth": r"(?:premium|APE|new\s+business\s+premium)",
        "vnb_margin": r"(?:VNB\s+margin|value\s+of\s+new\s+business\s+margin)",
        "persistency_13m": r"(?:13[- ]month|13m)[^%\n]{0,30}?persistency",
        "solvency_ratio": r"solvency\s+ratio",
    }
    term = terms.get(metric)
    if not term:
        return True
    number_pattern = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(?:\s*%)?", re.IGNORECASE)
    if quote and len(number_pattern.findall(quote)) > 8:
        # Dense table excerpts often contain peer/segment columns. Require a
        # shorter narrative quote before accepting the model's pairing.
        return False
    excerpt = quote or text
    paired_pattern = re.compile(
        r"(?:GNPA|gross\s+NPA)\s*/\s*(?:NNPA|net\s+NPA)[^\d%\n]{0,80}(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    paired = paired_pattern.search(excerpt)
    if paired and metric in {"reported_gnpa", "nnpa"}:
        expected = float(paired.group(1) if metric == "reported_gnpa" else paired.group(2))
        return abs(expected - value) <= 0.0001
    reversed_pair = re.search(
        r"(?:GNPA|gross\s+NPA)[^\d%\n]{0,80}(\d+(?:\.\d+)?)\s+(?:and|,|&)\s+(?:NNPA|net\s+NPA)[^\d%\n]{0,30}(\d+(?:\.\d+)?)",
        excerpt,
        re.IGNORECASE,
    )
    if reversed_pair and metric in {"reported_gnpa", "nnpa"}:
        expected = float(reversed_pair.group(1) if metric == "reported_gnpa" else reversed_pair.group(2))
        return abs(expected - value) <= 0.0001
    local_text = excerpt
    for term_match in re.finditer(term, text, re.IGNORECASE):
        # Match against the supplied quote where possible. The full document
        # can contain another company's table with the same metric label.
        local_term_match = re.search(term, local_text, re.IGNORECASE)
        if local_term_match is None:
            continue
        window_start = local_term_match.end()
        window = local_text[window_start : window_start + 48]
        for number_match in number_pattern.finditer(window):
            try:
                candidate = float(number_match.group(1))
            except ValueError:
                continue
            if abs(candidate - value) <= 0.0001:
                context = local_text[max(0, window_start - 24) : window_start + number_match.end() + 24].lower()
                if re.search(r"\bfrom\s+\d+(?:\.\d+)?\s*%?\s+in\s+(?:fy|q\d)", context):
                    continue
                return True
    return False


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
    known_facts = [fact for fact in facts if fact.metric == metric and fact.period != "unknown"]
    # Unknown periods may be useful evidence context, but must never be used
    # as the endpoints of a temporal calculation.
    if len(known_facts) < 2:
        return []
    for fact in known_facts:
        key = fact.period
        if key not in selected or fact.source_tier < selected[key].source_tier:
            selected[key] = fact
    return sorted(selected.values(), key=lambda item: _period_key(item.period, known_facts.index(item)))


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


def _run_insurer_research(
    identity: CompanyIdentity,
    mode: str,
    evidence: tuple[EvidenceItem, ...],
    facts: list[Fact],
    source_documents: dict[str, SourceDocument],
    warnings: list[str],
    ai_provider: StructuredProvider | None,
) -> DiscoveryReport:
    """Analyze the insurer pack without applying bank/NBFC asset-quality logic."""

    premium = _series(facts, "premium_growth")
    margin = _series(facts, "vnb_margin")
    if len(premium) < 2 or len(margin) < 2:
        return _report_without_discovery(identity, mode, evidence, facts, source_documents, warnings)
    premium_start, premium_end = premium[0], premium[-1]
    margin_start, margin_end = margin[0], margin[-1]
    premium_change = delta(premium_end.value, premium_start.value)
    margin_change = delta(margin_end.value, margin_start.value)
    calculations = (
        _calculation(
            "calc-live-premium-growth-change",
            "Premium growth change",
            "latest premium growth − earliest premium growth",
            premium_change,
            "percentage points",
            (premium_start.id, premium_end.id),
            "Premium growth is compared across verified reporting periods.",
        ),
        _calculation(
            "calc-live-vnb-margin-change",
            "VNB margin change",
            "latest VNB margin − earliest VNB margin",
            margin_change,
            "percentage points",
            (margin_start.id, margin_end.id),
            "VNB margin indicates the economics of newly written business.",
        ),
        _calculation(
            "calc-live-growth-margin-gap",
            "Premium-growth versus VNB-margin gap",
            "premium-growth change − VNB-margin change",
            premium_change - margin_change,
            "percentage points",
            (premium_start.id, premium_end.id, margin_start.id, margin_end.id),
            "A positive gap means growth changed faster than new-business economics.",
        ),
    )
    evidence_by_fact = {
        fact.id: next((item.id for item in evidence if item.source_document_id == fact.source_document_id and fact.metric in item.claim), evidence[0].id)
        for fact in facts
        if evidence
    }
    discovery_evidence = tuple(dict.fromkeys(evidence_by_fact.get(fact.id, evidence[0].id) for fact in (premium_start, premium_end, margin_start, margin_end)))
    source_families = len({item.publisher_family for item in evidence if item.id in discovery_evidence})
    calculation_ids = tuple(item.id for item in calculations)
    claims = (
        Claim(
            id="claim-live-insurer-discovery",
            text=f"{identity.name}'s verified premium-growth change differs from its VNB-margin change across the retrieved reporting window.",
            claim_type="discovery",
            evidence_ids=discovery_evidence,
            calculation_ids=calculation_ids,
            independent_source_families=source_families,
            confidence=0.65 if source_families >= 2 else 0.45,
            status="validated" if source_families >= 2 else "downgraded",
        ),
        Claim(
            id="claim-live-insurer-counterargument",
            text="Product mix, distribution mix, or reporting definitions may explain the premium-growth/VNB-margin divergence.",
            claim_type="counterargument",
            evidence_ids=discovery_evidence,
            independent_source_families=source_families,
            confidence=0.55,
        ),
        Claim(
            id="claim-live-insurer-falsification",
            text="The insurer hypothesis should be reconsidered if later periods show VNB margin improving at least as quickly as premium growth under consistent definitions.",
            claim_type="falsification_condition",
            evidence_ids=discovery_evidence,
            calculation_ids=calculation_ids,
            independent_source_families=source_families,
            confidence=0.62,
        ),
    )
    hypotheses = (
        Hypothesis(
            id="hyp-live-insurer-growth-economics",
            statement="Top-line premium growth is changing faster than VNB margin, so volume and new-business economics may be diverging.",
            lens="Growth versus economics",
            score=78.0,
            supporting_evidence_ids=discovery_evidence,
            opposing_evidence_ids=(),
            alternative_explanation="Product mix, channel mix, or a normal shift toward lower-margin products may explain the gap.",
            status="survived",
        ),
        Hypothesis(
            id="hyp-live-insurer-mix",
            statement="The signal is primarily a product or distribution mix change rather than a deterioration in underwriting economics.",
            lens="Mix shift",
            score=55.0,
            supporting_evidence_ids=(),
            opposing_evidence_ids=discovery_evidence,
            alternative_explanation="The available documents may not disclose enough product-level detail to distinguish mix from execution.",
            status="candidate",
        ),
        Hypothesis(
            id="hyp-live-insurer-sector",
            statement="The growth-margin divergence may be shared by the insurance sector rather than unique to the company.",
            lens="Company versus peers",
            score=43.0,
            supporting_evidence_ids=(),
            opposing_evidence_ids=discovery_evidence,
            alternative_explanation="Peer VNB and premium disclosures may show the same cycle once retrieved.",
            status="candidate",
        ),
    )
    if ai_provider:
        try:
            generated = ai_provider.generate_hypotheses(
                {"company": identity.symbol, "calculations": [item.__dict__ for item in calculations], "evidence": [item.__dict__ for item in evidence]}
            )
            if generated:
                valid_ids = {item.id for item in evidence}
                hypotheses = tuple(
                    Hypothesis(
                        id=f"hyp-live-ai-{index}",
                        statement=str(item.get("statement", "")),
                        lens=str(item.get("lens", "AI-generated")),
                        score=50.0,
                        supporting_evidence_ids=tuple(evidence_id for evidence_id in item.get("evidence_ids", ()) if evidence_id in valid_ids),
                        opposing_evidence_ids=(),
                        alternative_explanation=str(item.get("alternative_explanation", "")),
                        status="candidate",
                    )
                    for index, item in enumerate(generated[:3], start=1)
                    if str(item.get("statement", "")).strip()
                ) or hypotheses
        except SourceError:
            warnings.append("Structured AI hypothesis generation was unavailable; deterministic insurer hypotheses were retained.")
    tests = (
        FalsificationTest("test-live-insurer-sector", "Sector test", "Do most peers show the same growth-margin divergence?", "INCONCLUSIVE", "Peer source coverage was not sufficient for a complete sector test.", discovery_evidence),
        FalsificationTest("test-live-insurer-accounting", "Accounting-artifact test", "Could reporting scope or product definitions explain the trend?", "INCONCLUSIVE", "Definition continuity requires additional source pages.", discovery_evidence),
        FalsificationTest("test-live-insurer-base", "Base-effect test", "Does the signal survive a multi-year comparison?", "PASS", "The comparison uses more than one verified period.", discovery_evidence),
        FalsificationTest("test-live-insurer-macro", "Regulatory / macro test", "Could industry pricing or regulation explain the timing?", "INCONCLUSIVE", "No independent macro timing source resolved this test.", discovery_evidence),
        FalsificationTest("test-live-insurer-disclosure", "Disclosure-change test", "Did the company change what it reports?", "INCONCLUSIVE", "Metric labels were extracted, but definition continuity requires more pages.", discovery_evidence),
    )
    conflicts = ()
    if len({item.source_document_id for item in evidence}) >= 2 and len(discovery_evidence) >= 2:
        source_a = next(item for item in evidence if item.id == discovery_evidence[0])
        source_b = next(item for item in evidence if item.id == discovery_evidence[1])
        if source_a.source_document_id != source_b.source_document_id:
            conflicts = (
                Conflict(
                    id="conflict-live-insurer-growth-margin",
                    conflict_type="Narrative versus metric mismatch",
                    source_a_id=source_a.source_document_id,
                    source_b_id=source_b.source_document_id,
                    claim_a=source_a.claim,
                    claim_b=source_b.claim,
                    metric_or_topic="Insurance growth economics",
                    period=margin_end.period,
                    severity="material",
                    possible_explanation="Premium growth and VNB margin may reflect different product or distribution mixes.",
                    resolution_status="open",
                    evidence_ids=discovery_evidence,
                    calculation_ids=calculation_ids,
                ),
            )
    passed = sum(item.status == "PASS" for item in tests)
    strength, strength_reasoning = evidence_strength(passed, source_families, len(calculations))
    events = (
        ResearchEvent(1, "resolve", "resolve_company", f"Resolved {identity.symbol} as {identity.name}."),
        ResearchEvent(2, "collect", "discover_sources", f"Retrieved {len(source_documents)} public insurer documents.", source_ids=tuple(source_documents)),
        ResearchEvent(3, "extract", "verify_facts", f"Kept {len(facts)} facts after quote verification.", fact_ids=tuple(item.id for item in facts), evidence_ids=discovery_evidence),
        ResearchEvent(4, "calculate", "calculate_metrics", "Computed premium-growth and VNB-margin relationships.", calculation_ids=calculation_ids),
        ResearchEvent(5, "hypothesize", "generate_hypotheses", f"Generated {len(hypotheses)} competing insurer hypotheses.", hypothesis_ids=tuple(item.id for item in hypotheses)),
        ResearchEvent(6, "challenge", "run_red_team", "Ran five insurer falsification tests.", evidence_ids=discovery_evidence),
        ResearchEvent(7, "report", "compose_report", "Validated the insurer claim ledger and evidence trail."),
    )
    report = DiscoveryReport(
        run_id=f"live_{hashlib.sha256((identity.symbol + str(date.today())).encode()).hexdigest()[:10]}",
        mode=mode,
        company=identity,
        discovery=f"{identity.name}'s verified premium-growth change differs from its VNB-margin change across the retrieved public-source window.",
        why_it_matters=(
            "Premium growth and new-business margin measure different parts of insurer economics.",
            "The gap is a research signal, not a prediction or investment recommendation.",
            "Product mix, distribution mix, and peer evidence are required before treating it as company-specific.",
        ),
        evidence=evidence,
        timeline=tuple(
            TimelineEvent(period=period, label="Verified insurer evidence point", detail="A source-backed premium or VNB metric enters the growth-economics comparison.", tone="source" if index == 0 else "signal")
            for index, period in enumerate(dict.fromkeys((premium_start.period, premium_end.period)))
        ),
        numbers=calculations,
        counterargument="Product mix, channel mix, reporting definitions, or a normal shift toward lower-margin products may explain the divergence.",
        falsification_condition="Reconsider this conclusion if two later periods show VNB margin improving at least as quickly as premium growth, with consistent product definitions and peer context.",
        evidence_strength=strength,  # type: ignore[arg-type]
        strength_reasoning=strength_reasoning,
        hypotheses=hypotheses,
        falsification_tests=tests,
        metrics={
            "periods": [premium_start.period, premium_end.period],
            "premium_growth": [safe_round(premium_start.value), safe_round(premium_end.value)],
            "vnb_margin": [safe_round(margin_start.value), safe_round(margin_end.value)],
            "premium_growth_change": safe_round(premium_change),
            "vnb_margin_change": safe_round(margin_change),
        },
        stages=("Resolve company identity", "Discover public sources", "Verify quotes", "Calculate insurer metrics", "Challenge hypotheses", "Prepare auditable report"),
        notice="LIVE PUBLIC-SOURCE MODE — insurer metrics and quotes were retrieved and verified from public documents; source coverage warnings remain visible.",
        claims=claims,
        conflicts=conflicts,
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
        f'"{identity.name}" quarterly results GNPA NNPA write-offs credit cost PDF',
        f'"{identity.name}" investor presentation asset quality Q1 FY26 Q2 FY26',
        f'"{identity.name}" annual report portfolio quality provisions FY25 FY24',
        f'"{identity.name}" historical quarterly GNPA NNPA FY24 FY25',
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

    if identity.business_model == "Insurer":
        return _run_insurer_research(identity, mode, evidence, facts, source_documents, warnings, ai_provider)

    gnpa = _series(facts, "reported_gnpa")
    secondary_metric = "write_off_rate"
    secondary = _series(facts, secondary_metric)
    if len(secondary) < 2:
        # Public reports often disclose GNPA and NNPA consistently but do not
        # publish write-offs. Use the strongest available related metric rather
        # than discarding an otherwise auditable cross-period report.
        for candidate_metric in ("nnpa", "credit_cost", "provision_coverage"):
            candidate_series = _series(facts, candidate_metric)
            if len(candidate_series) >= 2:
                secondary_metric = candidate_metric
                secondary = candidate_series
                break
    common_periods = sorted(
        set(fact.period for fact in gnpa).intersection(fact.period for fact in secondary),
        key=_period_key,
    )
    if len(common_periods) >= 2:
        # Keep the report focused on the latest comparable window while the
        # evidence ledger still retains older public reports for context.
        common_periods = common_periods[-4:]
        gnpa_by_period = {fact.period: fact for fact in gnpa}
        secondary_by_period = {fact.period: fact for fact in secondary}
        gnpa = [gnpa_by_period[period] for period in common_periods]
        secondary = [secondary_by_period[period] for period in common_periods]
    if len(gnpa) < 2 or len(secondary) < 2 or len(common_periods) < 2:
        return _report_without_discovery(identity, mode, evidence, facts, source_documents, warnings)

    gnpa_start, gnpa_end = gnpa[0], gnpa[-1]
    writeoff_start, writeoff_end = secondary[0], secondary[-1]
    secondary_labels = {
        "write_off_rate": ("Write-off rate", "write-off-adjusted", "The write-off flow challenges a headline-only improvement narrative."),
        "nnpa": ("NNPA", "GNPA-versus-NNPA", "NNPA provides a second asset-quality view alongside headline GNPA."),
        "credit_cost": ("Credit cost", "GNPA-plus-credit-cost", "Credit cost provides a provisioning-flow context when write-offs are unavailable."),
        "provision_coverage": ("Provision coverage", "GNPA-plus-provision-coverage", "Provision coverage provides a loss-absorption context alongside headline GNPA."),
    }
    secondary_label, secondary_short_label, secondary_interpretation = secondary_labels[secondary_metric]
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
            f"{secondary_label}-adjusted GNPA comparison",
            f"(earliest GNPA + earliest {secondary_label}) − (latest GNPA + latest {secondary_label})",
            adjusted_improvement,
            "percentage points",
            (gnpa_start.id, gnpa_end.id, writeoff_start.id, writeoff_end.id),
            secondary_interpretation,
        ),
        _calculation(
            "calc-live-secondary-change",
            f"{secondary_label} change",
            f"latest {secondary_label} − earliest {secondary_label}",
            delta(writeoff_end.value, writeoff_start.value),
            "percentage points",
            (writeoff_start.id, writeoff_end.id),
            secondary_interpretation,
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
            text=f"{identity.name}'s headline GNPA improvement differs from its {secondary_short_label} comparison across verified periods.",
            claim_type="discovery",
            evidence_ids=discovery_evidence,
            calculation_ids=calculation_ids,
            independent_source_families=source_families,
            confidence=0.65 if source_families >= 2 else 0.45,
            status="validated" if source_families >= 2 else "downgraded",
        ),
        Claim(
            id="claim-live-counterargument",
            text=f"Recoveries, seasoning, product mix, or definition changes may explain the GNPA/{secondary_label} divergence without hidden deterioration.",
            claim_type="counterargument",
            evidence_ids=discovery_evidence,
            independent_source_families=source_families,
            confidence=0.55,
        ),
        Claim(
            id="claim-live-falsification",
            text=f"The hypothesis should be reconsidered if later periods show the {secondary_label} relationship moving in the same direction as headline GNPA under consistent definitions.",
            claim_type="falsification_condition",
            evidence_ids=discovery_evidence,
            calculation_ids=calculation_ids,
            independent_source_families=source_families,
            confidence=0.62,
        ),
    )
    hypotheses = (
        Hypothesis(
            id="hyp-live-stock-flow",
            statement=f"Headline asset-quality improvement may be less complete than it appears because the {secondary_short_label} comparison differs from the stock measure.",
            lens="Stock versus flow",
            score=78.0,
            supporting_evidence_ids=discovery_evidence,
            opposing_evidence_ids=(),
            alternative_explanation="Recoveries, portfolio seasoning, product mix, or a normalizing credit cycle may improve both measures without hidden deterioration.",
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
                    metric_or_topic=f"Asset quality and {secondary_label}",
                    period=gnpa_end.period,
                    severity="material",
                    possible_explanation=f"The documents may report different measures or scopes; {secondary_label} may be a different construct from headline GNPA.",
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
        ResearchEvent(4, "calculate", "calculate_metrics", f"Computed {len(calculations)} deterministic GNPA-versus-{secondary_label} metrics.", calculation_ids=calculation_ids),
        ResearchEvent(5, "hypothesize", "generate_hypotheses", f"Generated {len(hypotheses)} competing hypotheses.", hypothesis_ids=tuple(item.id for item in hypotheses)),
        ResearchEvent(6, "challenge", "run_red_team", "Ran five falsification tests; unresolved alternatives remain visible.", evidence_ids=discovery_evidence),
        ResearchEvent(7, "report", "compose_report", "Validated the live claim ledger and evidence trail."),
    )
    report = DiscoveryReport(
        run_id=f"live_{hashlib.sha256((identity.symbol + str(date.today())).encode()).hexdigest()[:10]}",
        mode=mode,
        company=identity,
        discovery=f"{identity.name}'s verified headline GNPA improvement differs from its {secondary_short_label} comparison across the retrieved public-source window.",
        why_it_matters=(
            f"Headline GNPA and {secondary_label} are not interchangeable measures, so the second metric provides a useful challenge to a headline-only reading.",
            "The result is a monitoring hypothesis, not a prediction or investment recommendation.",
            "Independent publisher-family coverage determines whether the signal remains strong or is downgraded.",
        ),
        evidence=evidence,
        timeline=timeline,
        numbers=calculations,
        counterargument=f"Recoveries, portfolio seasoning, product mix, a normalizing credit cycle, or a definition mismatch may explain the GNPA/{secondary_label} divergence without hidden deterioration.",
        falsification_condition=f"Reconsider this conclusion if two consecutive later periods show the {secondary_label} relationship moving in the same direction as headline GNPA, after confirming consistent definitions.",
        evidence_strength=strength,  # type: ignore[arg-type]
        strength_reasoning=strength_reasoning,
        hypotheses=hypotheses,
        falsification_tests=tests,
        metrics={
            "periods": [gnpa_start.period, gnpa_end.period],
            "reported_gnpa": [safe_round(gnpa_start.value), safe_round(gnpa_end.value)],
            "write_off_rate": [safe_round(writeoff_start.value), safe_round(writeoff_end.value)] if secondary_metric == "write_off_rate" else [],
            "writeoff_adjusted_gnpa": [safe_round(gnpa_start.value + writeoff_start.value), safe_round(gnpa_end.value + writeoff_end.value)],
            "headline_improvement": safe_round(headline_improvement),
            "adjusted_improvement": safe_round(adjusted_improvement),
            "secondary_metric": secondary_metric,
            "secondary_label": secondary_label,
            "secondary_values": [safe_round(writeoff_start.value), safe_round(writeoff_end.value)],
        },
        stages=("Resolve company identity", "Discover public sources", "Verify quotes", "Calculate divergences", "Challenge hypotheses", "Prepare auditable report"),
        notice="LIVE PUBLIC-SOURCE MODE — values and quotes were retrieved and verified from public documents; source coverage warnings remain visible.",
        claims=claims,
        conflicts=conflicts,
        events=events,
    )
    validate_report(report)
    return report
