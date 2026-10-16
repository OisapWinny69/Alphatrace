"""Pure calculations used by the research engine."""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Sequence


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        raise ValueError("Cannot calculate percentage change from zero")
    return (current / previous - 1) * 100


def delta(current: float, previous: float) -> float:
    return current - previous


def cagr(start: float, end: float, years: float) -> float:
    if start <= 0 or end < 0 or years <= 0:
        raise ValueError("CAGR requires positive start and duration")
    return ((end / start) ** (1 / years) - 1) * 100


def z_score(value: float, peers: Sequence[float]) -> float:
    if len(peers) < 2:
        return 0.0
    spread = pstdev(peers)
    return 0.0 if spread == 0 else (value - mean(peers)) / spread


def persistence(values: Sequence[float], threshold: float = 0.0) -> int:
    """Return consecutive values at or above threshold from the newest period."""
    count = 0
    for value in reversed(values):
        if value >= threshold:
            count += 1
        else:
            break
    return count


def evidence_strength(passed_tests: int, independent_tiers: int, calculation_count: int) -> tuple[str, str]:
    score = min(100, passed_tests * 12 + independent_tiers * 12 + calculation_count * 7)
    if score >= 75:
        label = "Strong"
    elif score >= 50:
        label = "Moderate"
    else:
        label = "Weak"
    reasoning = (
        f"Heuristic score {score}/100 from {passed_tests} surviving falsification tests, "
        f"{independent_tiers} independent source tiers, and {calculation_count} reproducible calculations."
    )
    return label, reasoning


def safe_round(value: float, digits: int = 2) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, digits)
