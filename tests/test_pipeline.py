import unittest

from signal_lens.engine import run_research
from signal_lens.resolver import resolve_company, supported_companies


class PipelineTests(unittest.TestCase):
    def test_resolver_accepts_symbol_and_name(self):
        symbol = resolve_company("BAJFINANCE")
        name = resolve_company("Bajaj Finance")
        self.assertIsNotNone(symbol)
        self.assertIsNotNone(name)
        self.assertEqual(symbol.symbol, name.symbol)
        self.assertEqual(symbol.business_model, "NBFC")

    def test_supported_universe_has_track_a_companies(self):
        self.assertIn("HDFCBANK", supported_companies())
        self.assertIn("SBILIFE", supported_companies())

    def test_unknown_company_is_not_silently_invented(self):
        self.assertIsNone(resolve_company("NOTAREALCOMPANY"))

    def test_complete_offline_report_contains_required_elements(self):
        report = run_research("HDFCBANK")
        self.assertEqual(report.mode, "offline")
        self.assertTrue(report.discovery)
        self.assertGreaterEqual(len(report.why_it_matters), 3)
        self.assertGreaterEqual(len(report.evidence), 3)
        self.assertGreaterEqual(len(report.timeline), 3)
        self.assertGreaterEqual(len(report.numbers), 3)
        self.assertTrue(report.counterargument)
        self.assertTrue(report.falsification_condition)
        self.assertIn(report.evidence_strength, {"Strong", "Moderate", "Weak"})
        self.assertEqual(len(report.hypotheses), 3)
        self.assertEqual(len(report.falsification_tests), 5)
        self.assertTrue(any(item.status == "rejected" for item in report.hypotheses))
        self.assertTrue(all(item.url.startswith("https://") for item in report.evidence))

    def test_unknown_research_input_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "could not resolve"):
            run_research("UNKNOWN")


if __name__ == "__main__":
    unittest.main()
