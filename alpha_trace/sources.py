"""Public-source discovery, retrieval, caching, and quote verification.

The module deliberately keeps search results separate from evidence. A search
result is only a candidate URL; it becomes usable evidence after retrieval,
parsing, and quote verification succeed.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import VerificationStatus


USER_AGENT = "AlphaTrace/0.2 (public-source-research; contact via repository)"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_DOCUMENT_BYTES = 32 * 1024 * 1024


class SourceError(RuntimeError):
    """Expected public-source failure that should be visible as partial coverage."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float | None = None


@dataclass(frozen=True)
class RetrievedDocument:
    url: str
    final_url: str
    content_type: str
    status_code: int
    body: bytes
    content_hash: str
    from_cache: bool = False


@dataclass(frozen=True)
class ParsedDocument:
    url: str
    title: str
    text: str
    content_hash: str
    content_type: str
    page_count: int | None = None
    pages: tuple[str, ...] = ()
    period_hint: str = ""


@dataclass(frozen=True)
class QuoteMatch:
    status: VerificationStatus
    start: int | None
    end: int | None
    matched_text: str = ""


class SearchProvider(Protocol):
    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        ...


def validate_public_url(url: str) -> str:
    """Validate a public HTTP(S) URL before it is requested or displayed."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceError("Only public http(s) URLs are supported")
    if parsed.username or parsed.password:
        raise SourceError("URLs with embedded credentials are not allowed")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise SourceError("Local hostnames are not public sources")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise SourceError("Private or local network addresses are not public sources")
    return url


class DocumentCache:
    """Content-addressed-on-URL cache kept outside the public static directory."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv("ALPHATRACE_CACHE_DIR") or Path("data") / "cache"
        self.root = Path(configured)
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / f"{key}.body", self.root / f"{key}.json"

    def load(self, url: str) -> RetrievedDocument | None:
        body_path, metadata_path = self._paths(url)
        if not body_path.exists() or not metadata_path.exists():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body = body_path.read_bytes()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return RetrievedDocument(
            url=url,
            final_url=str(metadata.get("final_url", url)),
            content_type=str(metadata.get("content_type", "application/octet-stream")),
            status_code=int(metadata.get("status_code", 200)),
            body=body,
            content_hash=hashlib.sha256(body).hexdigest(),
            from_cache=True,
        )

    def save(self, document: RetrievedDocument) -> None:
        body_path, metadata_path = self._paths(document.url)
        body_path.write_bytes(document.body)
        metadata_path.write_text(
            json.dumps(
                {
                    "final_url": document.final_url,
                    "content_type": document.content_type,
                    "status_code": document.status_code,
                    "content_hash": document.content_hash,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


class PublicSourceFetcher:
    """Fetch public documents with bounded size, timeouts, and a local cache."""

    def __init__(
        self,
        cache: DocumentCache | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.cache = cache or DocumentCache()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.opener = opener

    def fetch(self, url: str, allow_cache: bool = True) -> RetrievedDocument:
        validate_public_url(url)
        if allow_cache:
            cached = self.cache.load(url)
            if cached:
                return cached
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.1"})
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            validate_public_url(final_url)
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise SourceError("Source document exceeds the configured size limit")
            content_type = str(response.headers.get("Content-Type", "application/octet-stream")).split(";", 1)[0].lower()
            document = RetrievedDocument(
                url=url,
                final_url=final_url,
                content_type=content_type,
                status_code=int(getattr(response, "status", 200)),
                body=body,
                content_hash=hashlib.sha256(body).hexdigest(),
            )
        except HTTPError as error:
            raise SourceError(f"Source returned HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise SourceError(f"Source retrieval failed: {error}") from error
        self.cache.save(document)
        return document


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        self.parts.append(cleaned)
        if self._in_title:
            self.title_parts.append(cleaned)


def parse_document(document: RetrievedDocument) -> ParsedDocument:
    """Parse HTML or a PDF when the Docker-provided ``pdftotext`` is available."""

    content_type = document.content_type
    if "pdf" in content_type or document.final_url.lower().split("?", 1)[0].endswith(".pdf"):
        executable = shutil.which("pdftotext")
        if not executable:
            raise SourceError("PDF parser is unavailable; install poppler-utils or configure a parser adapter")
        pdf_path = ""
        text_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
                pdf_file.write(document.body)
                pdf_path = pdf_file.name
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as text_file:
                text_path = text_file.name
            result = subprocess.run(
                [executable, "-layout", pdf_path, text_path],
                capture_output=True,
                check=True,
                timeout=30,
            )
            text = Path(text_path).read_text(encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as error:
            raise SourceError(f"PDF parsing failed: {error}") from error
        finally:
            for temporary_path in (pdf_path, text_path):
                if temporary_path:
                    try:
                        Path(temporary_path).unlink(missing_ok=True)
                    except OSError:
                        pass
        pages = tuple(page.strip() for page in text.split("\f") if page.strip())
        return ParsedDocument(
            url=document.final_url,
            title=document.final_url,
            text="\n\n".join(pages),
            content_hash=document.content_hash,
            content_type=content_type,
            page_count=len(pages),
            pages=pages,
        )
    if "html" not in content_type and "text" not in content_type and not document.body.lstrip().startswith(b"<"):
        raise SourceError("Unsupported source document type")
    parser = _VisibleTextParser()
    try:
        parser.feed(document.body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as error:  # HTMLParser can fail on malformed custom input.
        raise SourceError(f"HTML parsing failed: {error}") from error
    return ParsedDocument(
        url=document.final_url,
        title=" ".join(parser.title_parts) or document.final_url,
        text="\n".join(parser.parts),
        content_hash=document.content_hash,
        content_type=content_type,
        page_count=1,
        pages=("\n".join(parser.parts),),
    )


def _normalize_for_match(value: str) -> str:
    value = value.casefold().replace("\u2018", "'").replace("\u2019", "'")
    value = re.sub(r"[^\w%.,:/+\- ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def verify_quote(document_text: str, quote: str) -> QuoteMatch:
    """Verify an exact quote, allowing only controlled whitespace/punctuation normalization."""

    if not document_text.strip() or not quote.strip():
        return QuoteMatch("failed", None, None)
    exact_start = document_text.find(quote)
    if exact_start >= 0:
        return QuoteMatch("verified", exact_start, exact_start + len(quote), quote)

    normalized_document = _normalize_for_match(document_text)
    normalized_quote = _normalize_for_match(quote)
    normalized_start = normalized_document.find(normalized_quote)
    if normalized_start >= 0:
        return QuoteMatch("normalized_match", normalized_start, normalized_start + len(normalized_quote), normalized_quote)
    return QuoteMatch("failed", None, None)


class TavilySearchProvider:
    """Minimal Tavily adapter; API results remain candidate sources until fetched."""

    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None, opener: Callable[..., Any] = urlopen) -> None:
        # ``""`` is an intentional disabled value for offline tests and
        # callers that want to override a configured process environment.
        self.api_key = os.getenv("TAVILY_API_KEY", "") if api_key is None else api_key
        self.opener = opener

    def search(self, query: str, max_results: int = 8) -> list[SearchResult]:
        if not self.api_key:
            raise SourceError("Tavily search is not configured")
        payload = json.dumps(
            {"api_key": self.api_key, "query": query, "max_results": max(1, min(max_results, 20)), "search_depth": "advanced"}
        ).encode("utf-8")
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            response = self.opener(request, timeout=DEFAULT_TIMEOUT_SECONDS)
            result = json.loads(response.read(DEFAULT_MAX_DOCUMENT_BYTES).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SourceError(f"Search provider failed: {error}") from error
        items = result.get("results", []) if isinstance(result, dict) else []
        output: list[SearchResult] = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            try:
                validate_public_url(item["url"])
            except SourceError:
                continue
            score = item.get("score")
            output.append(SearchResult(str(item.get("title", item["url"])), item["url"], str(item.get("content", "")), float(score) if score is not None else None))
        return output


class PublicSourceCollector:
    """Discover candidates and return only documents that were retrieved and parsed."""

    def __init__(self, search: SearchProvider, fetcher: PublicSourceFetcher | None = None) -> None:
        self.search_provider = search
        self.fetcher = fetcher or PublicSourceFetcher()

    def collect(self, query: str, max_results: int = 8) -> tuple[list[SearchResult], list[ParsedDocument], list[str]]:
        candidates = self.search_provider.search(query, max_results=max_results)
        parsed: list[ParsedDocument] = []
        warnings: list[str] = []
        for candidate in candidates:
            try:
                parsed.append(parse_document(self.fetcher.fetch(candidate.url)))
            except SourceError as error:
                warnings.append(f"{candidate.url}: {error}")
        return candidates, parsed, warnings
