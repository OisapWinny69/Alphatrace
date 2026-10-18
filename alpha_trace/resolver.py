"""Company and peer resolution for Track A."""

from __future__ import annotations

import re

from .models import CompanyIdentity


_COMPANIES: dict[str, dict[str, object]] = {
    # Banks: NIFTY 50 constituents plus listed same-sector fallback peers.
    "HDFCBANK": {"name": "HDFC Bank Limited", "model": "Bank"},
    "ICICIBANK": {"name": "ICICI Bank Limited", "model": "Bank"},
    "SBIN": {"name": "State Bank of India", "model": "Bank"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank Limited", "model": "Bank"},
    "AXISBANK": {"name": "Axis Bank Limited", "model": "Bank"},
    "INDUSINDBK": {"name": "IndusInd Bank Limited", "model": "Bank"},
    "BANKBARODA": {"name": "Bank of Baroda", "model": "Bank"},
    "CANBK": {"name": "Canara Bank", "model": "Bank"},
    "PNB": {"name": "Punjab National Bank", "model": "Bank"},
    "UNIONBANK": {"name": "Union Bank of India", "model": "Bank"},
    "IDFCFIRSTB": {"name": "IDFC First Bank Limited", "model": "Bank"},
    "FEDERALBNK": {"name": "The Federal Bank Limited", "model": "Bank"},
    "AUBANK": {"name": "AU Small Finance Bank Limited", "model": "Bank"},
    "BANDHANBNK": {"name": "Bandhan Bank Limited", "model": "Bank"},
    "RBLBANK": {"name": "RBL Bank Limited", "model": "Bank"},
    "YESBANK": {"name": "Yes Bank Limited", "model": "Bank"},
    "BAJFINANCE": {"name": "Bajaj Finance Limited", "model": "NBFC"},
    "BAJAJFINSV": {"name": "Bajaj Finserv Limited", "model": "NBFC"},
    "SHRIRAMFIN": {"name": "Shriram Finance Limited", "model": "NBFC"},
    "JIOFIN": {"name": "Jio Financial Services Limited", "model": "NBFC"},
    "CHOLAFIN": {"name": "Cholamandalam Investment and Finance Company Limited", "model": "NBFC"},
    "MUTHOOTFIN": {"name": "Muthoot Finance Limited", "model": "NBFC"},
    "MANAPPURAM": {"name": "Manappuram Finance Limited", "model": "NBFC"},
    "LTF": {"name": "L&T Finance Limited", "model": "NBFC"},
    "PFC": {"name": "Power Finance Corporation Limited", "model": "NBFC"},
    "RECLTD": {"name": "REC Limited", "model": "NBFC"},
    "IRFC": {"name": "Indian Railway Finance Corporation Limited", "model": "NBFC"},
    "ABCAPITAL": {"name": "Aditya Birla Capital Limited", "model": "NBFC"},
    "HDFCLIFE": {"name": "HDFC Life Insurance Company Limited", "model": "Insurer"},
    "SBILIFE": {"name": "SBI Life Insurance Company Limited", "model": "Insurer"},
    "ICICIPRULI": {"name": "ICICI Prudential Life Insurance Company Limited", "model": "Insurer"},
    "MAXFIN": {"name": "Max Financial Services Limited", "model": "Insurer"},
    "ICICIGI": {"name": "ICICI Lombard General Insurance Company Limited", "model": "Insurer"},
    "STARHEALTH": {"name": "Star Health and Allied Insurance Company Limited", "model": "Insurer"},
    "LICI": {"name": "Life Insurance Corporation of India", "model": "Insurer"},
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
    "BANK OF BARODA": "BANKBARODA",
    "CANARA BANK": "CANBK",
    "PUNJAB NATIONAL BANK": "PNB",
    "UNION BANK": "UNIONBANK",
    "UNION BANK OF INDIA": "UNIONBANK",
    "IDFC FIRST BANK": "IDFCFIRSTB",
    "FEDERAL BANK": "FEDERALBNK",
    "AU SMALL FINANCE BANK": "AUBANK",
    "BANDHAN BANK": "BANDHANBNK",
    "RBL BANK": "RBLBANK",
    "YES BANK": "YESBANK",
    "BAJAJ FINANCE": "BAJFINANCE",
    "BAJAJ FINSERV": "BAJAJFINSV",
    "SHRIRAM FINANCE": "SHRIRAMFIN",
    "JIO FINANCIAL": "JIOFIN",
    "CHOLA FINANCE": "CHOLAFIN",
    "CHOLAMANDALAM INVESTMENT": "CHOLAFIN",
    "MUTHOOT FINANCE": "MUTHOOTFIN",
    "MANAPPURAM FINANCE": "MANAPPURAM",
    "LT FINANCE": "LTF",
    "POWER FINANCE CORPORATION": "PFC",
    "REC LIMITED": "RECLTD",
    "INDIAN RAILWAY FINANCE": "IRFC",
    "ADITYA BIRLA CAPITAL": "ABCAPITAL",
    "HDFC LIFE": "HDFCLIFE",
    "SBI LIFE": "SBILIFE",
    "ICICI PRUDENTIAL LIFE": "ICICIPRULI",
    "MAX FINANCIAL": "MAXFIN",
    "ICICI LOMBARD": "ICICIGI",
    "STAR HEALTH": "STARHEALTH",
    "LIFE INSURANCE CORPORATION": "LICI",
    "LIC": "LICI",
}

_PEERS = {
    "Bank": (
        "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
        "BANKBARODA", "CANBK", "PNB", "UNIONBANK", "IDFCFIRSTB", "FEDERALBNK",
        "AUBANK", "BANDHANBNK", "RBLBANK", "YESBANK",
    ),
    "NBFC": (
        "BAJFINANCE", "SHRIRAMFIN", "BAJAJFINSV", "JIOFIN", "CHOLAFIN", "MUTHOOTFIN",
        "MANAPPURAM", "LTF", "PFC", "RECLTD", "IRFC", "ABCAPITAL",
    ),
    "Insurer": ("HDFCLIFE", "SBILIFE", "ICICIPRULI", "MAXFIN", "ICICIGI", "STARHEALTH", "LICI"),
}

_METRIC_PACKS = {
    "Bank": "bank_asset_quality",
    "NBFC": "nbfc_asset_quality",
    "Insurer": "insurance_quality",
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
        metric_pack=_METRIC_PACKS[model],
    )


def supported_companies() -> list[str]:
    return sorted(_COMPANIES)
