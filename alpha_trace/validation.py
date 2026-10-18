"""Validation rules for auditable research reports."""

from __future__ import annotations

from .models import DiscoveryReport


def validate_report(report: DiscoveryReport) -> None:
    """Reject reports that contain unsupported or unverifiable major claims."""

    evidence_by_id = {item.id: item for item in report.evidence}
    calculations_by_id = {item.id: item for item in report.numbers}
    hypothesis_ids = {item.id for item in report.hypotheses}

    if not report.claims:
        raise ValueError("Report must contain a claim ledger")

    for claim in report.claims:
        if claim.status == "rejected":
            continue
        if not claim.evidence_ids:
            raise ValueError(f"Claim {claim.id} has no evidence")
        missing_evidence = set(claim.evidence_ids) - evidence_by_id.keys()
        if missing_evidence:
            raise ValueError(f"Claim {claim.id} references missing evidence")
        if any(
            evidence_by_id[evidence_id].verification_status not in {"verified", "normalized_match"}
            for evidence_id in claim.evidence_ids
        ):
            raise ValueError(f"Claim {claim.id} references an unverified quote")
        missing_calculations = set(claim.calculation_ids) - calculations_by_id.keys()
        if missing_calculations:
            raise ValueError(f"Claim {claim.id} references missing calculations")

    for conflict in report.conflicts:
        if conflict.source_a_id not in {item.source_document_id for item in report.evidence}:
            raise ValueError(f"Conflict {conflict.id} references an unknown source")
        if conflict.source_b_id not in {item.source_document_id for item in report.evidence}:
            raise ValueError(f"Conflict {conflict.id} references an unknown source")
        if any(evidence_id not in evidence_by_id for evidence_id in conflict.evidence_ids):
            raise ValueError(f"Conflict {conflict.id} references missing evidence")
        if any(calculation_id not in calculations_by_id for calculation_id in conflict.calculation_ids):
            raise ValueError(f"Conflict {conflict.id} references missing calculations")

    for hypothesis in report.hypotheses:
        if hypothesis.id not in hypothesis_ids:
            raise ValueError("Hypothesis identity validation failed")
