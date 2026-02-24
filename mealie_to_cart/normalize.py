from __future__ import annotations

import re
from dataclasses import dataclass

from .models import NormalizedItem


_FRACTION_RE = re.compile(r"^(?:(\d+)\s+)?(\d+)\/(\d+)$")


def parse_quantity_token(tok: str) -> float | None:
    """Parse tokens like '1', '1/2', '2 1/2' (the mixed form handled by caller)."""
    tok = tok.strip()
    if not tok:
        return None

    # simple int/float
    try:
        return float(tok)
    except ValueError:
        pass

    m = _FRACTION_RE.match(tok)
    if m:
        whole, num, den = m.groups()
        val = (int(num) / int(den))
        if whole:
            val += int(whole)
        return float(val)

    # unicode halves/quarters (minimal set)
    unicode_map = {
        "½": 0.5,
        "¼": 0.25,
        "¾": 0.75,
        "⅓": 1 / 3,
        "⅔": 2 / 3,
    }
    if tok in unicode_map:
        return float(unicode_map[tok])

    return None


def _split_or(raw: str) -> tuple[str, str | None]:
    # Split on the first standalone ' or ' (case-insensitive)
    parts = re.split(r"\s+or\s+", raw, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return raw.strip(), None


def _strip_parentheticals(s: str) -> str:
    # Remove balanced parentheticals
    s = re.sub(r"\([^)]*\)", "", s).strip()
    # Clean up orphaned open/close parens that remain
    s = re.sub(r"[()]", "", s).strip()
    return s


def _extract_parenthetical_grams(raw: str) -> float | None:
    # examples: (75 grams) (168 g)
    m = re.search(r"\(([^)]*?)\)", raw)
    if not m:
        return None
    txt = m.group(1).lower()
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(g|gram|grams)\b", txt)
    if not m2:
        return None
    return float(m2.group(1))


_UNIT_ALIASES: dict[str, str] = {
    "cups": "cup",
    "cup": "cup",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "ts": "tsp",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "ml": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
}


def _clean_query(q: str) -> str:
    """Strip noise from a query string to produce a clean Walmart search term."""
    # Strip parentheticals that may have survived
    q = _strip_parentheticals(q)
    # Remove trailing asterisks, ellipsis, and similar
    q = re.sub(r"[*…]+$", "", q).strip()
    # Remove leading filler phrases
    q = re.sub(
        r"^(totally optional[:\s]*|optional[:\s]*|about\s+)",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    # Remove "NOT ..." parenthetical advice
    q = re.sub(r"\bNOT\b[^,;)]*", "", q).strip()
    # Remove trailing filler like ", plus more to swirl on top"
    q = re.sub(r",\s*plus\s+more\b.*$", "", q, flags=re.IGNORECASE).strip()
    # Remove trailing "about N ..." fragments
    q = re.sub(r"\s+about\s+.*$", "", q, flags=re.IGNORECASE).strip()
    # Remove "of choice" — just search the ingredient
    q = re.sub(r"\s+of\s+choice\b", "", q, flags=re.IGNORECASE).strip()
    # Remove "mix-ins like" and similar fluff
    q = re.sub(r"\bmix-?ins?\s+like\s+", "", q, flags=re.IGNORECASE).strip()
    # Remove cooking prep words
    q = re.sub(r"\b(mashed|ripe|melted|chopped|diced|minced|sliced|crushed|fresh|dried)\s+", "", q, flags=re.IGNORECASE).strip()
    # Strip leading quantity + unit even if they got through (e.g. "½ cup")
    q = re.sub(
        r"^[½¼¾⅓⅔\d/]+\s*(cups?|teaspoons?|tablespoons?|tbsp|tsp|oz|ounces?|lbs?|pounds?|grams?|g|kg|ml|l|liters?)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    # Strip leading unit words that leaked through (cup/cups/teaspoon/tbsp etc.)
    q = re.sub(
        r"^(cups?|teaspoons?|tablespoons?|tbsp|tsp|oz|ounces?|lbs?|pounds?|grams?|g|kg|ml|l|liters?)\s+",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip()
    # Remove stray colons, commas at start/end
    q = q.strip(":,;. ")
    # Collapse whitespace
    q = re.sub(r"\s{2,}", " ", q).strip()
    # Cap query length — long queries return garbage on Walmart
    words = q.split()
    if len(words) > 5:
        q = " ".join(words[:5])
    return q


def normalize_line(raw: str) -> NormalizedItem:
    left, right = _split_or(raw)

    grams = _extract_parenthetical_grams(raw)

    qty, unit = _parse_leading_qty_unit(left)

    query = _strip_parentheticals(left)
    if qty is not None and unit is not None:
        # remove the leading qty+unit from query
        query = re.sub(r"^\s*[^A-Za-z]*", "", query)  # clean leading punctuation
        query = re.sub(r"^\s*" + re.escape(_leading_text(left)) + r"\s*", "", query, flags=re.IGNORECASE).strip()

    query = _clean_query(query)
    alt_query = _clean_query(_strip_parentheticals(right)) if right else None
    # Drop alt if it's identical, empty, or just noise after cleaning
    if alt_query and (alt_query.lower() == query.lower() or len(alt_query) < 3):
        alt_query = None

    ounces = None
    if grams is not None:
        ounces = grams / 28.349523125

    return NormalizedItem(
        raw=raw,
        query=query.strip(),
        alt_query=alt_query.strip() if alt_query else None,
        quantity=qty,
        unit=unit,
        grams=grams,
        ounces=ounces,
    )


def _leading_text(left: str) -> str:
    # Helper to compute the exact leading substring representing qty+unit for removal.
    tokens = left.strip().split()
    if not tokens:
        return ""

    # mixed number: "2 1/2 cup"
    if len(tokens) >= 3:
        q1 = parse_quantity_token(tokens[0])
        q2 = parse_quantity_token(tokens[1])
        u = _UNIT_ALIASES.get(tokens[2].lower())
        if q1 is not None and q2 is not None and u:
            return " ".join(tokens[:3])

    if len(tokens) >= 2:
        q = parse_quantity_token(tokens[0])
        u = _UNIT_ALIASES.get(tokens[1].lower())
        if q is not None and u:
            return " ".join(tokens[:2])

    return ""


def _parse_leading_qty_unit(left: str) -> tuple[float | None, str | None]:
    tokens = left.strip().split()
    if not tokens:
        return None, None

    # Handle "2 1/2 cup"
    if len(tokens) >= 3:
        q1 = parse_quantity_token(tokens[0])
        q2 = parse_quantity_token(tokens[1])
        u = _UNIT_ALIASES.get(tokens[2].lower())
        if q1 is not None and q2 is not None and u:
            return float(q1 + q2), u

    # Handle "1/3 cup"
    if len(tokens) >= 2:
        q = parse_quantity_token(tokens[0])
        u = _UNIT_ALIASES.get(tokens[1].lower())
        if q is not None and u:
            return float(q), u

    return None, None
