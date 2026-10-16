"""Company and peer resolution for Track A."""

from __future__ import annotations

import re

from .models import CompanyIdentity


_COMPANIES: dict[str, dict[str, object]] = {
    "HDFCBANK": {"name": "HDFC Bank Limited", "model": "Bank"},
    "ICICIBANK": {"name": "ICICI Bank Limited", "model": "Bank"},
    "SBIN": {"name": "State Bank of India", "model": "Bank"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank Limited", "model": "Bank"},
    "AXISBANK": {"name": "Axis Bank Limited", "model": "Bank"},
    "INDUSINDBK": {"name": "IndusInd Bank Limited", "model": "Bank"},
    "BAJFINANCE": {"name": "Bajaj Finance Limited", "model": "NBFC"},
    "BAJAJFINSV": {"name": "Bajaj Finserv Limited", "model": "NBFC"},
    "SHRIRAMFIN": {"name": "Shriram Finance Limited", "model": "NBFC"},
    "JIOFIN": {"name": "Jio Financial Services Limited", "model": "NBFC"},
    "HDFCLIFE": {"name": "HDFC Life Insurance Company Limited", "model": "Insurer"},
    "SBILIFE": {"name": "SBI Life Insurance Company Limited", "model": "Insurer"},
}

_ALIASES = {
    "HDFCBANKLIMITED": "HDFCBANK",
    "HDFCBANK": "HDFCBANK",
    "HDFC BANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK",
    "ICICIBANKLIMITED": "ICICIBANK",
    "STATE BANK OF INDIA": "SBIN",
    "SBI": "SBIN",
    "KOTAK MAHINDRA BANK": "KOTAKBANK",
    "AXIS BANK": "AXISBANK",
    "INDUSIND BANK": "INDUSINDBK",
    "BAJAJ FINANCE": "BAJFINANCE",
    "BAJAJ FINSERV": "BAJAJFINSV",
    "SHRIRAM FINANCE": "SHRIRAMFIN",
    "JIO FINANCIAL": "JIOFIN",
    "HDFC LIFE": "HDFCLIFE",
    "SBI LIFE": "SBILIFE",
}

_PEERS = {
    "Bank": ("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"),
    "NBFC": ("BAJFINANCE", "SHRIRAMFIN", "BAJAJFINSV", "JIOFIN"),
    "Insurer": ("HDFCLIFE", "SBILIFE"),
}


def _canonical_query(query: str) -> str:
    compact = re.sub(r"[^A-Z0-9 ]", "", query.upper()).strip()
    return _ALIASES.get(compact, compact.replace(" ", ""))


def resolve_company(query: str) -> CompanyIdentity | None:
    """Resolve a supported Track A company without network access."""

    symbol = _canonical_query(query)
    record = _COMPANIES.get(symbol)
    if not record:
        return None
    model = str(record["model"])
    peers = tuple(peer for peer in _PEERS[model] if peer != symbol)
    return CompanyIdentity(
        symbol=symbol,
        name=str(record["name"]),
        business_model=model,
        sector="Banking, NBFCs & Financial Services",
        exchange="NSE",
        peers=peers,
        ir_url=f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}",
    )


def supported_companies() -> list[str]:
    return sorted(_COMPANIES)
