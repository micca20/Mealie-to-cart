from __future__ import annotations

import re
from dataclasses import dataclass

from .models import NormalizedItem, WalmartCandidate

_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(fl\s*oz|oz|lb|lbs|g|gram|grams|kg|ml|l|gal|ct|count)\b",
    re.IGNORECASE,
)

_TO_OZ: dict[str, float] = {
    "oz": 1.0,
    "fl oz": 1.0,
    "lb": 16.0,
    "lbs": 16.0,
    "g": 1 / 28.3495,
    "gram": 1 / 28.3495,
    "grams": 1 / 28.3495,
    "kg": 35.274,
    "ml": 1 / 29.5735,
    "l": 33.814,
    "gal": 128.0,
}


@dataclass(frozen=True)
class ChosenProduct:
    candidate: WalmartCandidate
    score: float
    size_oz: float | None
    undersized: bool


def parse_size(text: str | None) -> float | None:
    if not text:
        return None
    m = _SIZE_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower().strip()
    factor = _TO_OZ.get(unit)
    if factor is None:
        return None
    return round(val * factor, 4)


def score_relevance(query: str, title: str) -> float:
    q_tokens = set(re.findall(r"\w+", query.lower()))
    t_tokens = set(re.findall(r"\w+", title.lower()))
    if not q_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def choose_best(
    item: NormalizedItem,
    candidates: list[WalmartCandidate],
) -> ChosenProduct | None:
    if not candidates:
        return None

    requested_oz = item.ounces
    if requested_oz is None and item.grams is not None:
        requested_oz = item.grams / 28.3495

    scored: list[tuple[WalmartCandidate, float, float | None]] = []
    for c in candidates:
        rel = score_relevance(item.query, c.title)
        sz = parse_size(c.size_text) or parse_size(c.title)
        scored.append((c, rel, sz))

    if requested_oz is not None and requested_oz > 0:
        bigger = [(c, r, s) for c, r, s in scored if s is not None and s >= requested_oz]
        if bigger:
            bigger.sort(key=lambda x: (x[2], -x[1]))
            c, r, s = bigger[0]
            return ChosenProduct(candidate=c, score=r, size_oz=s, undersized=False)

        with_size = [(c, r, s) for c, r, s in scored if s is not None]
        if with_size:
            with_size.sort(key=lambda x: (-x[1], -(x[2] or 0)))
            c, r, s = with_size[0]
            return ChosenProduct(candidate=c, score=r, size_oz=s, undersized=True)

    scored.sort(key=lambda x: -x[1])
    c, r, s = scored[0]
    return ChosenProduct(candidate=c, score=r, size_oz=s, undersized=False)
