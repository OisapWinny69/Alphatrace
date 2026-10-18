import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

import app
from alpha_trace.store import ResearchStore


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app.STORE = ResearchStore(Path(self.temp_dir.name) / "runs.sqlite3")
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.AlphaTraceHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def _json(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_research_run_can_be_reloaded_and_replayed(self):
        created = self._json("POST", "/api/research", {"query": "HDFCBANK", "mode": "offline"})
        run_id = created["run_id"]
        self.assertEqual(created["status"], "complete")

        reloaded = self._json("GET", f"/api/runs/{run_id}")
        self.assertEqual(reloaded["run_id"], run_id)
        self.assertEqual(reloaded["report"]["company"]["symbol"], "HDFCBANK")

        events = self._json("GET", f"/api/runs/{run_id}/events")
        evidence = self._json("GET", f"/api/runs/{run_id}/evidence")
        claims = self._json("GET", f"/api/runs/{run_id}/claims")
        conflicts = self._json("GET", f"/api/runs/{run_id}/conflicts")
        replay = self._json("POST", f"/api/runs/{run_id}/replay")
        self.assertGreaterEqual(len(events["items"]), 10)
        self.assertGreaterEqual(len(evidence["items"]), 3)
        self.assertGreaterEqual(len(claims["items"]), 4)
        self.assertGreaterEqual(len(conflicts["items"]), 2)
        self.assertEqual(replay["events"], events["items"])

    def test_live_mode_with_no_search_key_returns_an_honest_weak_report(self):
        created = self._json("POST", "/api/research", {"query": "HDFCBANK", "mode": "live"})
        self.assertEqual(created["report"]["mode"], "live")
        self.assertIn("No strong discovery found", created["report"]["discovery"])
        self.assertEqual(created["report"]["evidence_strength"], "Weak")

    def test_env_loader_reads_settings_without_overwriting_process_values(self):
        original_root = app.ROOT
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("ALPHATRACE_TEST_MODE=live\n# ignored\n", encoding="utf-8")
            app.ROOT = Path(directory)
            os.environ.pop("ALPHATRACE_TEST_MODE", None)
            app._load_env_file()
            self.assertEqual(os.environ.get("ALPHATRACE_TEST_MODE"), "live")
            os.environ["ALPHATRACE_TEST_MODE"] = "process"
            app._load_env_file()
            self.assertEqual(os.environ.get("ALPHATRACE_TEST_MODE"), "process")
            os.environ.pop("ALPHATRACE_TEST_MODE", None)
        app.ROOT = original_root


if __name__ == "__main__":
    unittest.main()
