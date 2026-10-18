import tempfile
import unittest
from pathlib import Path

from alpha_trace.engine import run_research
from alpha_trace.store import ResearchStore


class StoreTests(unittest.TestCase):
    def test_completed_run_and_indexes_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(Path(directory) / "runs.sqlite3")
            report = run_research("ICICIBANK")
            store.save_report(report)

            run = store.get_run(report.run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "complete")
            self.assertEqual(store.get_report(report.run_id)["discovery"], report.discovery)
            self.assertEqual(len(store.get_events(report.run_id)), len(report.events))
            self.assertEqual(len(store.get_evidence(report.run_id)), len(report.evidence))
            self.assertEqual(len(store.get_claims(report.run_id)), len(report.claims))
            self.assertEqual(len(store.get_conflicts(report.run_id)), len(report.conflicts))

    def test_unknown_run_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(Path(directory) / "runs.sqlite3")
            self.assertIsNone(store.get_run("missing"))
            self.assertIsNone(store.get_report("missing"))
            self.assertEqual(store.get_events("missing"), [])


if __name__ == "__main__":
    unittest.main()
