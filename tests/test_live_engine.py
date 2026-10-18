import hashlib
import unittest

from alpha_trace.live_engine import run_live_research
from alpha_trace.sources import RetrievedDocument, SearchResult, TavilySearchProvider


class FakeSearch:
    def search(self, query: str, max_results: int = 8):
        return [
            SearchResult("Q1 filing", "https://rbi.org.in/q1.html", ""),
            SearchResult("Q2 filing", "https://nseindia.com/q2.html", ""),
        ]


class FakeFetcher:
    bodies = {
        "https://rbi.org.in/q1.html": b"<html><title>Q1</title><body>GNPA was 1.10% and write-off rate was 0.18%.</body></html>",
        "https://nseindia.com/q2.html": b"<html><title>Q2</title><body>GNPA was 0.70% and write-off rate was 0.37%.</body></html>",
    }

    def fetch(self, url: str):
        body = self.bodies[url]
        return RetrievedDocument(url, url, "text/html", 200, body, hashlib.sha256(body).hexdigest())


class FakeAI:
    def extract_facts(self, document, metrics):
        if "q1" in document.url:
            period = "Q1 FY25"
            values = (1.10, 0.18)
        else:
            period = "Q2 FY25"
            values = (0.70, 0.37)
        return [
            {"metric": "reported_gnpa", "value": values[0], "unit": "%", "period": period, "quote": document.text, "page": 1},
            {"metric": "write_off_rate", "value": values[1], "unit": "%", "period": period, "quote": document.text, "page": 1},
        ]

    def generate_hypotheses(self, context):
        return []


class LiveEngineTests(unittest.TestCase):
    def test_live_engine_uses_verified_sources_and_deterministic_calculations(self):
        report = run_live_research(
            "HDFCBANK",
            search_provider=FakeSearch(),
            fetcher=FakeFetcher(),
            ai_provider=FakeAI(),
        )
        self.assertEqual(report.mode, "live")
        self.assertIn("differs", report.discovery)
        self.assertEqual(report.metrics["headline_improvement"], 0.4)
        self.assertEqual(report.metrics["adjusted_improvement"], 0.21)
        self.assertGreaterEqual(len(report.claims), 1)
        self.assertGreaterEqual(len(report.conflicts), 1)
        self.assertTrue(all(item.verification_status in {"verified", "normalized_match"} for item in report.evidence))
        self.assertTrue(any(event.action == "run_red_team" for event in report.events))

    def test_live_engine_with_missing_search_configuration_withholds_discovery(self):
        report = run_live_research("HDFCBANK", TavilySearchProvider(api_key=""))
        self.assertIn("No strong discovery found", report.discovery)
        self.assertEqual(report.evidence_strength, "Weak")
        self.assertTrue(all(test.status == "INCONCLUSIVE" for test in report.falsification_tests))


if __name__ == "__main__":
    unittest.main()
