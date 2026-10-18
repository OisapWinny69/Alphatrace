import re
import unittest
from pathlib import Path

from reports.generate_report import generate


class ReportPdfTests(unittest.TestCase):
    def test_report_is_a_two_page_pdf_with_clickable_sources(self):
        output = Path("reports") / "AlphaTrace_TrackA_Round1.pdf"
        generate(output)
        payload = output.read_bytes()
        self.assertTrue(payload.startswith(b"%PDF-1.4"))
        self.assertEqual(len(re.findall(rb"/Type /Page(?!s)", payload)), 2)
        self.assertGreaterEqual(payload.count(b"/Subtype /Link"), 4)
        self.assertIn(b"https://www.nseindia.com/", payload)
        self.assertIn(b"No strong discovery found", payload)
        self.assertGreater(len(payload), 10_000)


if __name__ == "__main__":
    unittest.main()
