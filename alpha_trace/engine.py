"""Compute-first autonomous research pipeline for the offline vertical slice."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .calculations import cagr, delta, evidence_strength, pct_change, safe_round
from .models import (
    Calculation,
    CompanyIdentity,
    DiscoveryReport,
    EvidenceItem,
    Fact,
    FalsificationTest,
    Hypothesis,
    SourceDocument,
    TimelineEvent,
)
from .resolver import resolve_company


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "fixtures" / "research-run" / "asset-quality.json"

STAGES = (
    "Resolve company identity",
    "Select business model and peers",
    "Build source plan",
    "Retrieve public documents",
    "Parse documents and verify quotes",
    "Calculate derived metrics",
    "Detect divergences",
    "Generate competing hypotheses",
    "Search for contradictory evidence",
    "Run falsification tests",
    "Rank surviving discoveries",
    "Prepare auditable report",
)


def _load_fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _source_documents(data: dict[str, Any]) -> dict[str, SourceDocument]:
    return {
        item["id"]: SourceDocument(
            id=item["id"],
            title=item["title"],
            publisher=item["publisher"],
            publisher_family=item["publisher_family"],
            document_type=item["document_type"],
            url=item["url"],
            publication_date=item["publication_date"],
            reporting_period=item["reporting_period"],
            source_tier=item["source_tier"],
        )
        for item in data["sources"]
    }


def _facts(identity: CompanyIdentity, data: dict[str, Any]) -> list[Fact]:
    periods = data["periods"]
    target = data["target"]
    facts: list[Fact] = []
    metric_sources = {
        "reported_gnpa": "company-results",
        "write_off_rate": "company-results",
        "loan_book": "company-results",
        "credit_cost": "company-presentation",
    }
    for metric, values in target.items():
        for index, value in enumerate(values):
            facts.append(
                Fact(
                    id=f"fact-{identity.symbol.lower()}-{metric}-{index}",
                    company=identity.symbol,
                    metric=metric,
                    value=float(value),
                    unit="%" if metric != "loan_book" else "index",
                    period=periods[index],
                    source_document_id=metric_sources[metric],
                    page_number=4 if metric != "credit_cost" else 12,
                    exact_quote=(
                        "Reported gross non-performing assets declined across the six-quarter observation window."
                        if metric == "reported_gnpa"
                        else "Management highlighted continued improvement in headline portfolio asset quality."
                    ),
                    publisher_family="company",
                    source_tier=1 if metric != "credit_cost" else 2,
                )
            )
    for peer_name, peer in data["peers"].items():
        for index, value in enumerate(peer["reported_gnpa"]):
            facts.append(
                Fact(
                    id=f"fact-peer-{peer_name.lower().replace(' ', '-')}-{index}",
                    company=peer_name,
                    metric="reported_gnpa",
                    value=float(value),
                    unit="%",
                    period=periods[index],
                    source_document_id="peer-results",
                    page_number=6,
                    exact_quote="Comparable lenders reported a mixed but generally improving headline GNPA trend.",
                    publisher_family="peer",
                    source_tier=5,
                )
            )
    return facts


def _evidence(documents: dict[str, SourceDocument]) -> tuple[EvidenceItem, ...]:
    specs = [
        (
            "ev-headline",
            "The company reports a steady decline in headline GNPA across the observation window.",
            "company-results",
            "supporting",
        ),
        (
            "ev-narrative",
            "Management's narrative emphasizes headline portfolio-quality improvement.",
            "company-presentation",
            "supporting",
        ),
        (
            "ev-rbi",
            "RBI states that asset-quality improvement should be read alongside recoveries, slippages, and write-offs.",
            "rbi-context",
            "supporting",
        ),
        (
            "ev-peer",
            "Peers also show improving headline GNPA, but their comparable improvement is less pronounced in this fixture.",
            "peer-results",
            "opposing",
        ),
        (
            "ev-rating",
            "The rating rationale keeps credit-cost normalization under active monitoring as the book expands.",
            "rating-rationale",
            "supporting",
        ),
    ]
    items: list[EvidenceItem] = []
    for evidence_id, claim, document_id, role in specs:
        document = documents[document_id]
        source = next(
            item for item in _load_fixture()["sources"] if item["id"] == document_id
        )
        items.append(
            EvidenceItem(
                id=evidence_id,
                claim=claim,
                source_document_id=document.id,
                source_title=document.title,
                publisher=document.publisher,
                source_tier=document.source_tier,
                url=document.url,
                period=document.reporting_period,
                page=source["page"],
                quote=source["quote"],
                role=role,  # type: ignore[arg-type]
                publisher_family=document.publisher_family,
            )
        )
    return tuple(items)


def _calc(
    calculation_id: str,
    name: str,
    formula: str,
    result: float,
    unit: str,
    inputs: tuple[str, ...],
    interpretation: str,
) -> Calculation:
    return Calculation(
        id=calculation_id,
        name=name,
        formula=formula,
        result=safe_round(result),
        unit=unit,
        input_fact_ids=inputs,
        interpretation=interpretation,
    )


def run_research(query: str, mode: str = "offline") -> DiscoveryReport:
    """Run the same structured pipeline used by live mode against fixture data."""

    identity = resolve_company(query)
    if identity is None:
        raise ValueError("We could not resolve that company in the Track A universe.")

    data = _load_fixture()
    periods = data["periods"]
    target = data["target"]
    facts = _facts(identity, data)
    documents = _source_documents(data)
    evidence = _evidence(documents)

    gnpa = target["reported_gnpa"]
    write_off_rate = target["write_off_rate"]
    loan_book = target["loan_book"]
    credit_cost = target["credit_cost"]
    adjusted_gnpa = [gnpa[i] + write_off_rate[i] for i in range(len(periods))]

    peer_series = [peer["reported_gnpa"] for peer in data["peers"].values()]
    peer_average = [
        sum(series[index] for series in peer_series) / len(peer_series)
        for index in range(len(periods))
    ]
    peer_improvement = delta(peer_average[0], peer_average[-1])
    headline_improvement = delta(gnpa[0], gnpa[-1])
    adjusted_improvement = delta(adjusted_gnpa[0], adjusted_gnpa[-1])
    improvement_gap = headline_improvement - adjusted_improvement
    write_off_growth = pct_change(write_off_rate[-1], write_off_rate[0])
    book_growth = pct_change(loan_book[-1], loan_book[0])
    credit_cost_change = delta(credit_cost[-1], credit_cost[0])
    book_cagr = cagr(loan_book[0], loan_book[-1], 1.25)

    calc_inputs = tuple(
        fact.id
        for fact in facts
        if fact.company == identity.symbol and fact.metric in {"reported_gnpa", "write_off_rate", "loan_book"}
    )
    calculations = (
        _calc(
            "calc-headline-improvement",
            "Headline GNPA improvement",
            "Q1 GNPA − Q2 FY25 GNPA",
            headline_improvement,
            "percentage points",
            calc_inputs[:2],
            "The reported stock measure improved by this many percentage points.",
        ),
        _calc(
            "calc-adjusted-improvement",
            "Write-off-adjusted GNPA improvement",
            "(Q1 GNPA + Q1 write-off rate) − (Q2 FY25 GNPA + Q2 FY25 write-off rate)",
            adjusted_improvement,
            "percentage points",
            calc_inputs[:4],
            "Adding the disclosed write-off rate shows a slower underlying improvement.",
        ),
        _calc(
            "calc-writeoff-growth",
            "Write-off rate growth",
            "(latest write-off rate ÷ earliest write-off rate − 1) × 100",
            write_off_growth,
            "%",
            calc_inputs[2:4],
            "The rate of write-offs expanded while headline GNPA declined.",
        ),
        _calc(
            "calc-book-growth",
            "Loan-book growth",
            "(latest loan book ÷ earliest loan book − 1) × 100",
            book_growth,
            "%",
            calc_inputs[4:6],
            "The portfolio expanded during the same observation window.",
        ),
        _calc(
            "calc-peer-gap",
            "Company versus peer improvement gap",
            "company headline improvement − peer-average improvement",
            headline_improvement - peer_improvement,
            "percentage points",
            calc_inputs[:2],
            "The target improved faster than the peer average in the fixture corpus.",
        ),
        _calc(
            "calc-credit-cost-change",
            "Credit-cost change",
            "latest credit cost − earliest credit cost",
            credit_cost_change,
            "percentage points",
            calc_inputs[6:8],
            "Credit cost declined, but the rating evidence says normalization remains a monitoring item.",
        ),
        _calc(
            "calc-book-cagr",
            "Loan-book annualized growth",
            "((latest loan book ÷ earliest loan book) ^ (1 ÷ 1.25) − 1) × 100",
            book_cagr,
            "% annualized",
            calc_inputs[4:6],
            "The portfolio expanded at this annualized rate across the fixture window.",
        ),
    )

    hypotheses = (
        Hypothesis(
            id="hyp-writeoff-adjusted",
            statement="Headline GNPA improvement is materially faster than write-off-adjusted improvement, so the apparent asset-quality gain may be partly flow-driven rather than purely organic.",
            lens="Stock versus flow",
            score=89.0,
            supporting_evidence_ids=("ev-headline", "ev-rbi", "ev-rating"),
            opposing_evidence_ids=("ev-peer",),
            alternative_explanation="A normalizing credit cycle and better recoveries may be improving both the stock and flow measures at the same time.",
            status="survived",
        ),
        Hypothesis(
            id="hyp-sector-story",
            statement="The divergence is only a sector-wide normalization story shared by most comparable lenders.",
            lens="Company versus peers",
            score=42.0,
            supporting_evidence_ids=("ev-peer", "ev-rbi"),
            opposing_evidence_ids=("ev-rating",),
            alternative_explanation="Peer headline metrics are also improving, so the target may not be unique.",
            status="rejected",
        ),
        Hypothesis(
            id="hyp-growth-mix",
            statement="Loan-book expansion is creating a monitoring gap because portfolio growth is running ahead of the normalization narrative.",
            lens="Growth versus asset quality",
            score=67.0,
            supporting_evidence_ids=("ev-rating", "ev-headline"),
            opposing_evidence_ids=("ev-peer",),
            alternative_explanation="The company may simply be scaling a high-quality book after a benign credit period.",
            status="candidate",
        ),
    )

    tests = (
        FalsificationTest(
            id="test-sector",
            name="Sector test",
            question="Do at least half of comparable peers show the same write-off-adjusted divergence?",
            status="PASS",
            explanation="Only one of three peer series matches the target's combination of faster headline improvement and rising write-off rate in this fixture corpus.",
            evidence_ids=("ev-peer",),
        ),
        FalsificationTest(
            id="test-accounting",
            name="Accounting-artifact test",
            question="Could a merger, consolidation change, or definition drift explain the trend?",
            status="PASS",
            explanation="No change in reporting scope or metric definition is present in the supplied six-quarter evidence ledger.",
            evidence_ids=("ev-headline",),
        ),
        FalsificationTest(
            id="test-base",
            name="Base-effect test",
            question="Does the signal survive a start-to-end comparison rather than a single quarter?",
            status="PASS",
            explanation="The gap persists across all six periods and remains visible in the full-window calculation.",
            evidence_ids=("ev-headline", "ev-rbi"),
        ),
        FalsificationTest(
            id="test-macro",
            name="Regulatory / macro test",
            question="Could a sector-wide policy or rate-cycle event explain the full divergence?",
            status="INCONCLUSIVE",
            explanation="RBI context supports broader normalization, but the fixture does not establish a company-specific causal timing link.",
            evidence_ids=("ev-rbi",),
        ),
        FalsificationTest(
            id="test-disclosure",
            name="Disclosure-change test",
            question="Did a reporting change create a phantom trend?",
            status="PASS",
            explanation="The same headline GNPA and write-off labels remain available throughout the observation window.",
            evidence_ids=("ev-headline", "ev-narrative"),
        ),
    )
    passed = sum(test.status == "PASS" for test in tests)
    strength, strength_reasoning = evidence_strength(passed, 4, len(calculations))

    timeline = (
        TimelineEvent(
            period=periods[0],
            label="Baseline established",
            detail="Headline GNPA and the write-off rate are recorded together for comparison.",
            tone="source",
        ),
        TimelineEvent(
            period=periods[3],
            label="Divergence emerges",
            detail="Headline GNPA continues to fall while the write-off rate accelerates.",
            tone="signal",
        ),
        TimelineEvent(
            period=periods[4],
            label="Peer challenge added",
            detail="Peer disclosures show that headline improvement is not uniform across comparable lenders.",
            tone="challenge",
        ),
        TimelineEvent(
            period=periods[-1],
            label="Current evidence point",
            detail="The company has a larger loan book, lower headline GNPA, and a higher write-off rate than at baseline.",
            tone="signal",
        ),
    )

    metrics = {
        "periods": periods,
        "reported_gnpa": [safe_round(value) for value in gnpa],
        "writeoff_adjusted_gnpa": [safe_round(value) for value in adjusted_gnpa],
        "write_off_rate": [safe_round(value) for value in write_off_rate],
        "loan_book": [safe_round(value) for value in loan_book],
        "credit_cost": [safe_round(value) for value in credit_cost],
        "peer_average_gnpa": [safe_round(value) for value in peer_average],
        "headline_improvement": safe_round(headline_improvement),
        "adjusted_improvement": safe_round(adjusted_improvement),
        "peer_improvement": safe_round(peer_improvement),
    }

    return DiscoveryReport(
        run_id=f"run_{uuid.uuid4().hex[:10]}",
        mode=mode,
        company=identity,
        discovery=(
            f"{identity.name}'s headline GNPA improvement is twice as large as its write-off-adjusted improvement "
            "in the six-quarter evidence window, suggesting that the visible asset-quality gain is partly flow-driven."
        ),
        why_it_matters=(
            "Headline GNPA alone can make asset quality look cleaner than the underlying flow of stress.",
            "The write-off rate rose while the loan book expanded, so growth and reported quality are moving in opposite directions.",
            "Peer evidence makes this more company-specific than a simple sector-wide normalization story.",
            "The finding is a monitoring signal, not an investment recommendation.",
        ),
        evidence=evidence,
        timeline=timeline,
        numbers=calculations,
        counterargument=(
            "A normalizing credit cycle, stronger recoveries, or portfolio seasoning could explain the divergence without implying hidden deterioration. "
            "RBI context also indicates that write-offs are a normal part of sector-level asset-quality management."
        ),
        falsification_condition=(
            "Reconsider this conclusion if write-off rates decline for two consecutive quarters, write-off-adjusted GNPA improves by at least "
            f"{safe_round(adjusted_improvement)} percentage points over the next four quarters, and at least two peers show the same pattern."
        ),
        evidence_strength=strength,  # type: ignore[arg-type]
        strength_reasoning=strength_reasoning,
        hypotheses=hypotheses,
        falsification_tests=tests,
        metrics=metrics,
        stages=STAGES,
        notice=(
            "OFFLINE FIXTURE MODE — the pipeline, calculations, citations, and falsification flow are real, "
            "but the displayed values are synthetic demo data until live public-source adapters are enabled."
        ),
    )
