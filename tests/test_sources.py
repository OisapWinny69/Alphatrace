import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from alpha_trace.sources import (
    DocumentCache,
    PublicSourceFetcher,
    RetrievedDocument,
    SourceError,
    parse_document,
    validate_public_url,
    verify_quote,
)


class SourceTests(unittest.TestCase):
    def test_public_url_validation_rejects_local_and_credentials(self):
        with self.assertRaises(SourceError):
            validate_public_url("http://127.0.0.1:8000/private")
        with self.assertRaises(SourceError):
            validate_public_url("https://user:password@example.com/report")
        self.assertEqual(validate_public_url("https://example.com/report"), "https://example.com/report")

    def test_quote_verification_supports_exact_and_controlled_normalization(self):
        exact = verify_quote("Asset quality improved.", "Asset quality improved.")
        self.assertEqual(exact.status, "verified")
        normalized = verify_quote("Asset   quality improved.", "Asset quality improved.")
        self.assertEqual(normalized.status, "normalized_match")
        self.assertEqual(verify_quote("Different text", "Asset quality").status, "failed")

    def test_html_parser_excludes_script_and_keeps_title(self):
        body = b"<html><head><title>Public filing</title><script>secret()</script></head><body>GNPA improved <b>in Q2.</b></body></html>"
        document = RetrievedDocument("https://example.com/a", "https://example.com/a", "text/html", 200, body, hashlib.sha256(body).hexdigest())
        parsed = parse_document(document)
        self.assertEqual(parsed.title, "Public filing")
        self.assertIn("GNPA improved", parsed.text)
        self.assertNotIn("secret", parsed.text)

    def test_fetcher_caches_bytes_and_rejects_oversized_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = DocumentCache(Path(directory) / "cache")
            response = Mock()
            response.geturl.return_value = "https://example.com/a"
            response.status = 200
            response.headers = {"Content-Type": "text/html"}
            response.read.return_value = b"<html>evidence</html>"
            opener = Mock(return_value=response)
            fetcher = PublicSourceFetcher(cache=cache, opener=opener, max_bytes=100)
            first = fetcher.fetch("https://example.com/a")
            second = fetcher.fetch("https://example.com/a")
            self.assertFalse(first.from_cache)
            self.assertTrue(second.from_cache)
            opener.assert_called_once()

            large_response = Mock()
            large_response.geturl.return_value = "https://example.com/large"
            large_response.status = 200
            large_response.headers = {"Content-Type": "text/html"}
            large_response.read.return_value = b"x" * 101
            with self.assertRaisesRegex(SourceError, "size limit"):
                PublicSourceFetcher(cache=cache, opener=Mock(return_value=large_response), max_bytes=100).fetch("https://example.com/large")


if __name__ == "__main__":
    unittest.main()
