from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormalizedItem:
    raw: str

    # Primary search text (first option).
    query: str

    # Secondary query if the raw line contains an "or" alternative.
    alt_query: str | None = None

    # Parsed quantity and unit **as written** when detected.
    quantity: float | None = None
    unit: str | None = None

    # Parsed weight/volume when confidently detected.
    grams: float | None = None
    ounces: float | None = None


@dataclass(frozen=True)
class WalmartCandidate:
    """A single product result from a Walmart search."""

    title: str
    url: str
    price: str | None = None        # e.g. "$3.47"
    size_text: str | None = None     # raw size string from the card, e.g. "12 oz"
    img_url: str | None = None
    fulfillment: str | None = None   # e.g. "Pickup", "Delivery", "Shipping"
