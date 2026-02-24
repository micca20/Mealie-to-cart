# Mealie to Cart — Design Doc

## Overview
This project is a standalone Python CLI that:
1) reads a Mealie shopping list named **"Walmart"**,
2) normalizes each list item into a structured request (name + quantity + unit),
3) uses Playwright connected to the existing **Browserless** instance to search Walmart Grocery,
4) selects the best product match, preferring the **next larger size** when the exact size isn’t available,
5) adds items to the Walmart cart, and
6) outputs a run summary.

## Architecture (high level)

- **CLI entrypoint** (`mealie_to_cart/main.py`)
  - `sync` command: end-to-end execution
  - `dry-run` option: runs matching but does not add to cart
  - `--limit N`: optional cap for testing

- **Secrets/config** (`mealie_to_cart/config.py`)
  - Loads required values from Infisical at runtime

- **Mealie client** (`mealie_to_cart/mealie_client.py`)
  - Fetches shopping list + items via Mealie API

- **Normalizer / parser** (`mealie_to_cart/normalize.py`)
  - Converts Mealie items into `NormalizedItem` objects
  - Parses quantities/units when present

- **Walmart browser client** (`mealie_to_cart/walmart.py`)
  - Playwright CDP connection to Browserless
  - Login/session management
  - Search + result extraction
  - Add-to-cart actions

- **Matching engine** (`mealie_to_cart/match.py`)
  - Scores Walmart search results for relevance + size match
  - Implements “closest bigger size” selection rule

- **Logging + report** (`mealie_to_cart/report.py`)
  - Produces a final summary: added / skipped / failed, plus chosen product URLs

## Components

### 1) Config & Secrets
**Source:** Infisical (env=`dev`, path=`/`)

Required keys (already created):
- `MEALIE_URL`
- `MEALIE_API_KEY`
- `WALMART_EMAIL`
- `WALMART_PASSWORD`
- `BROWSERLESS_URL` (e.g. `ws://192.168.1.220:3100`)
- `BROWSERLESS_TOKEN`

Config object (example):
```py
@dataclass
class Config:
    mealie_url: str
    mealie_api_key: str
    walmart_email: str
    walmart_password: str
    browserless_url: str
    browserless_token: str
    mealie_list_name: str = "Walmart"
```

### 2) Mealie integration
We will treat Mealie as the source of truth; we do not try to merge duplicates unless they are exact matches (v1 keeps it simple).

**Plan:**
- Discover the shopping list by name (`"Walmart"`).
- Fetch items for that list.

**Interfaces (proposed):**
```py
class MealieClient:
    def get_shopping_list_by_name(self, name: str) -> ShoppingList: ...
    def get_list_items(self, list_id: str) -> list[MealieListItem]: ...
```

Notes:
- Exact Mealie endpoints vary by version; implementation will use the instance’s `/docs` (OpenAPI) to lock in correct routes.

### 3) Normalization / parsing
Mealie list entries can be messy (free text, notes, “2 lbs chicken breast”). We normalize into:

```py
@dataclass
class NormalizedItem:
    raw: str                 # original text
    name: str                # cleaned search term
    quantity: float | None
    unit: str | None
    size_oz: float | None    # derived when possible (oz)
```

Parsing rules (v1):
- Try to extract a leading quantity and unit (support fractions like `1/3`).
- If the string contains **alternates** like `"X or Y"`:
  - Normalize **primary** = `X`, **fallback** = `Y`.
  - Matching behavior: try primary first; if no reasonable match, try fallback.
- Prefer **parenthetical weights** when present (e.g. `honey (168 grams)`), since they map well to Walmart package sizes.
- Convert common units to oz when possible:
  - lb → 16 oz
  - oz → oz
  - g/kg → convert to oz
  - ml/l → convert to fl oz (note: imperfect; treat as separate dimension)
- If we can’t parse, fall back to searching by `name` only.

### 4) Walmart automation (Playwright + Browserless)
We connect to Browserless over CDP:
- `BROWSERLESS_URL` + token (typically `?token=...` or header-based depending on Browserless setup)

**Session strategy:**
- Maintain a persistent Playwright storage state file (cookies/localStorage) in a local project directory (e.g. `data/walmart_storage_state.json`).
- If session is invalid, perform login and refresh storage state.

**Navigation strategy:**
- Use Walmart search page with a query param (`/search?query=...`).
- For each result card, extract:
  - title
  - price (optional, not used for decisions in v1)
  - size text (e.g., “4 oz”, “12 ct”, “1 lb”, “32 fl oz”)
  - product URL
  - availability flags if visible

**Add to cart:**
- Prefer a stable add button on the product card.
- If the card only opens a product detail page, open it and add there.

### 5) Matching engine
We score search results and pick the best.

**Signals (v1):**
- Text relevance: token overlap / simple fuzzy match between normalized `name` and product title.
- Size match (when requested size parsed):
  - If exact size found → best
  - Otherwise: choose the *smallest size >= requested* ("closest bigger")
  - If all sizes are smaller: choose highest relevance and flag as “undersized”

**Size parsing (Walmart results):**
- Parse common patterns: `"(\d+(?:\.\d+)?)\s*(oz|fl oz|lb|g|kg)"`.
- Convert to comparable numeric domain when possible.
- If a result has no parseable size, it can still win by text relevance but is lower confidence.

### 6) Reporting
At the end of a run, print a compact summary and write JSON to disk:

- `run_report.json` contains:
  - timestamp
  - total items
  - for each item: raw text, normalized fields, chosen product title/url/size, status

Statuses:
- `ADDED`
- `SKIPPED_NO_MATCH`
- `FAILED`
- `NEEDS_REVIEW` (added but low confidence / size mismatch)

## Data Flow

1. `main.py sync`
2. `Config.load()` → Infisical
3. `MealieClient.get_shopping_list_by_name("Walmart")`
4. `MealieClient.get_list_items(list_id)`
5. For each item:
   - `normalize(item)` → `NormalizedItem`
   - `WalmartClient.search(normalized.name)` → result candidates
   - `match.choose_best(normalized, candidates)` → `ChosenProduct | None`
   - If chosen:
     - `WalmartClient.add_to_cart(chosen)`
   - Record outcome
6. Output summary + write report

## API / Interfaces

### CLI
- `python -m mealie_to_cart sync [--dry-run] [--limit N]`

### Infisical helper
We will reuse the existing helper script:
- `python3 skills/infisical-secrets/scripts/infisical.py get --key <KEY> --env dev`

Design choice: for v1 keep it simple (subprocess calls). Later we can lift the logic into a small Python module.

## Key decisions (decision → why)

1. **Browser automation (Playwright via Browserless)** → Walmart has no reliable public grocery API; Browserless already exists in your stack.
2. **List selection by name ("Walmart")** → simple operator experience; no IDs required.
3. **Persist storage state locally** → reduces frequency of MFA/login friction.
4. **Size “closest bigger” rule** → aligns with your preference (3oz → 4oz) and is deterministic.
5. **Standalone Python CLI** → easy to run manually, scriptable, and easy to migrate into a container later.

## Risks / Edge cases
- Walmart UI changes can break selectors; we’ll isolate selectors in one module and keep them easy to update.
- Login may require CAPTCHA or MFA; if it does, we’ll switch to a one-time “interactive login” run that stores cookies.
- Units like “count”, “bunch”, “pack” are hard to compare to oz; those will fall back to text relevance and be flagged low confidence.

## Next implementation checkpoints
- Confirm Mealie shopping list endpoints against **your** Mealie `/docs` and implement `MealieClient`.
- Implement Walmart login + persisted session.
- Implement search result scraping + robust selectors.
- Implement size parsing + chooser.
- Wire end-to-end `sync --dry-run` first, then enable add-to-cart.
