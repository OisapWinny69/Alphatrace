"""Typed domain models used by the offline research pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EvidenceRole = Literal["supporting", "opposing", "context"]
EvidenceStrength = Literal["Strong", "Moderate", "Weak"]
TestStatus = Literal["PASS", "FAIL", "INCONCLUSIVE"]
VerificationStatus = Literal["verified", "normalized_match", "unverified", "failed"]
ClaimType = Literal[
    "discovery",
    "why_it_matters",
    "counterargument",
    "falsification_condition",
    "context",
]
ClaimStatus = Literal["validated", "downgraded", "rejected"]
ConflictSeverity = Literal["low", "material", "critical"]
ConflictStatus = Literal["open", "explained", "resolved"]
EventStatus = Literal["complete", "warning", "failed"]


@dataclass(frozen=True)
class CompanyIdentity:
    symbol: str
    name: str
    business_model: str
    sector: str
    exchange: str
    peers: tuple[str, ...]
    ir_url: str


@dataclass(frozen=True)
class SourceDocument:
    id: str
    title: str
    publisher: str
    publisher_family: str
    document_type: str
    url: str
    publication_date: str
    reporting_period: str
    source_tier: int
    fixture: bool = True
    canonical_url: str = ""
    retrieval_status: Literal["retrieved", "cached", "failed", "fixture"] = "fixture"
    content_hash: str = ""


@dataclass(frozen=True)
class Fact:
    id: str
    company: str
    metric: str
    value: float
    unit: str
    period: str
    source_document_id: str
    page_number: int
    exact_quote: str
    publisher_family: str
    source_tier: int
    source_url: str = ""
    segment: str = ""
    scope: str = "unknown"
    quote_verification: VerificationStatus = "verified"


@dataclass(frozen=True)
class Calculation:
    id: str
    name: str
    formula: str
    result: float
    unit: str
    input_fact_ids: tuple[str, ...]
    interpretation: str


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    claim: str
    source_document_id: str
    source_title: str
    publisher: str
    source_tier: int
    url: str
    period: str
    page: int
    quote: str
    role: EvidenceRole
    publisher_family: str
    verification_status: VerificationStatus = "verified"
    claim_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: ClaimType
    evidence_ids: tuple[str, ...]
    calculation_ids: tuple[str, ...] = field(default_factory=tuple)
    independent_source_families: int = 0
    confidence: float = 0.0
    status: ClaimStatus = "validated"


@dataclass(frozen=True)
class Conflict:
    id: str
    conflict_type: str
    source_a_id: str
    source_b_id: str
    claim_a: str
    claim_b: str
    metric_or_topic: str
    period: str
    severity: ConflictSeverity
    possible_explanation: str
    resolution_status: ConflictStatus
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    calculation_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    statement: str
    lens: str
    score: float
    supporting_evidence_ids: tuple[str, ...]
    opposing_evidence_ids: tuple[str, ...]
    alternative_explanation: str
    status: Literal["survived", "rejected", "candidate"]


@dataclass(frozen=True)
class FalsificationTest:
    id: str
    name: str
    question: str
    status: TestStatus
    explanation: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class TimelineEvent:
    period: str
    label: str
    detail: str
    tone: Literal["signal", "source", "challenge"]


@dataclass(frozen=True)
class ResearchEvent:
    sequence: int
    stage: str
    action: str
    summary: str
    status: EventStatus = "complete"
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    fact_ids: tuple[str, ...] = field(default_factory=tuple)
    calculation_ids: tuple[str, ...] = field(default_factory=tuple)
    hypothesis_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    conflict_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveryReport:
    run_id: str
    mode: str
    company: CompanyIdentity
    discovery: str
    why_it_matters: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    timeline: tuple[TimelineEvent, ...]
    numbers: tuple[Calculation, ...]
    counterargument: str
    falsification_condition: str
    evidence_strength: EvidenceStrength
    strength_reasoning: str
    hypotheses: tuple[Hypothesis, ...]
    falsification_tests: tuple[FalsificationTest, ...]
    metrics: dict[str, Any]
    stages: tuple[str, ...]
    notice: str
    claims: tuple[Claim, ...] = field(default_factory=tuple)
    conflicts: tuple[Conflict, ...] = field(default_factory=tuple)
    events: tuple[ResearchEvent, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRun:
    run_id: str
    status: str
    report: DiscoveryReport
    events: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "events": list(self.events),
            "report": self.report.to_dict(),
        }
