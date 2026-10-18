"""Optional structured reasoning providers and conservative fact extraction."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .sources import ParsedDocument, SourceError


class StructuredProvider(Protocol):
    def extract_facts(self, document: ParsedDocument, metrics: tuple[str, ...]) -> list[dict[str, Any]]:
        ...

    def generate_hypotheses(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        ...


class OpenAICompatibleProvider:
    """Server-side structured JSON adapter for OpenAI-compatible chat APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        opener=urlopen,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("AI_MODEL", "")
        configured_base = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.endpoint = configured_base.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += "/chat/completions"
        self.opener = opener

    def _complete_json(self, system: str, user: str, max_tokens: int = 2000) -> Any:
        if not self.api_key or not self.model:
            raise SourceError("Structured AI provider is not configured")
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            response = self.opener(request, timeout=30)
            raw = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
            content = raw["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise SourceError("Structured AI response content was not text")
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.DOTALL)
            return json.loads(content)
        except HTTPError as error:
            raise SourceError(f"Structured AI provider returned HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError) as error:
            raise SourceError(f"Structured AI provider failed: {error}") from error

    def extract_facts(self, document: ParsedDocument, metrics: tuple[str, ...]) -> list[dict[str, Any]]:
        system = (
            "You extract only explicitly stated financial facts from a public document. "
            "Return JSON with a facts array. Never calculate, infer, or invent values. "
            "Each fact must include metric, value, unit, period, quote, and page. "
            "The quote must be copied verbatim from the supplied document text. "
            f"Allowed metrics: {', '.join(metrics)}."
        )
        user = f"Document URL: {document.url}\nDocument text:\n{document.text[:120000]}"
        result = self._complete_json(system, user)
        facts = result.get("facts", []) if isinstance(result, dict) else []
        return [item for item in facts if isinstance(item, dict)]

    def generate_hypotheses(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        system = (
            "Generate three competing financial research hypotheses from validated facts and calculations. "
            "Return JSON with a hypotheses array. Do not add numbers, URLs, or facts not present in the input. "
            "Each hypothesis must include statement, lens, alternative_explanation, and evidence_ids."
        )
        result = self._complete_json(system, json.dumps(context, ensure_ascii=False), max_tokens=1400)
        hypotheses = result.get("hypotheses", []) if isinstance(result, dict) else []
        return [item for item in hypotheses if isinstance(item, dict)]


@dataclass(frozen=True)
class HeuristicFactExtractor:
    """No-key fallback that extracts only quoted metric/value pairs."""

    patterns: dict[str, tuple[str, ...]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.patterns is None:
            object.__setattr__(
                self,
                "patterns",
                {
                    "reported_gnpa": (r"(?:gross\s+NPA|GNPA|gross\s+non[- ]performing\s+assets)[^%\n]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "nnpa": (r"(?:NNPA|net\s+NPA|net\s+non[- ]performing\s+assets)[^%\n]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "write_off_rate": (r"(?:write[- ]offs?|write[- ]off\s+rate)[^%\n]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "credit_cost": (r"(?:credit\s+cost)[^%\n]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "provision_coverage": (r"(?:provision\s+coverage|PCR)[^%\n]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "premium_growth": (r"(?:premium|APE|new\s+business\s+premium)[^%\n]{0,100}?(?:growth|grew|up)[^%\n]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "vnb_margin": (r"(?:VNB\s+margin|value\s+of\s+new\s+business\s+margin)[^%\n]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "persistency_13m": (r"(?:13[- ]month|13m)[^%\n]{0,50}?persistency[^%\n]{0,50}?([0-9]+(?:\.[0-9]+)?)\s*%",),
                    "solvency_ratio": (r"(?:solvency\s+ratio)[^%\n]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*(?:x|times)?",),
                },
            )

    def extract_facts(self, document: ParsedDocument, metrics: tuple[str, ...]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for metric in metrics:
            for pattern in self.patterns.get(metric, ()):
                match = re.search(pattern, document.text, flags=re.IGNORECASE)
                if not match:
                    continue
                start = max(0, match.start() - 100)
                end = min(len(document.text), match.end() + 100)
                facts.append(
                    {
                        "metric": metric,
                        "value": float(match.group(1)),
                        "unit": "%",
                        "period": "unknown",
                        "quote": document.text[start:end].strip(),
                        "page": 1,
                    }
                )
        return facts
