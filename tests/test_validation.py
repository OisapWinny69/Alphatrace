import unittest

from alpha_trace.engine import run_research
from alpha_trace.models import Claim
from alpha_trace.validation import validate_report


class ValidationTests(unittest.TestCase):
    def test_pipeline_report_passes_audit_validation(self):
        report = run_research("BAJFINANCE")
        validate_report(report)

    def test_missing_evidence_is_rejected(self):
        report = run_research("HDFCBANK")
        invalid = report.__class__(
            **{
                **report.__dict__,
                "claims": report.claims
                + (
                    Claim(
                        id="claim-invalid",
                        text="Unsupported claim",
                        claim_type="context",
                        evidence_ids=(),
                    ),
                ),
            }
        )
        with self.assertRaisesRegex(ValueError, "has no evidence"):
            validate_report(invalid)


if __name__ == "__main__":
    unittest.main()
