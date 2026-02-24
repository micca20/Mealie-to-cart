# Mealie to Cart — Implementation Plan

> Target: standalone Python CLI, deployed/runnable on Dockge, using Browserless for Playwright.

## Task 0 — Repo skeleton + tooling
**Goal:** Create the minimal project structure and a repeatable way to run it.

**Files:**
- `projects/mealie-to-cart/pyproject.toml`
- `projects/mealie-to-cart/README.md`
- `projects/mealie-to-cart/mealie_to_cart/__init__.py`
- `projects/mealie-to-cart/mealie_to_cart/main.py`

**Steps:**
1. Initialize a Python package `mealie_to_cart`.
2. Add a CLI entrypoint (`python -m mealie_to_cart ...`).
3. Add a basic README with how to run on Dockge (for now: direct python).

**Verification:**
- `cd projects/mealie-to-cart && python -m mealie_to_cart --help`

**Done criteria:**
- CLI starts and prints help.

---

## Task 1 — Infisical config loader
**Goal:** Load required secrets (Mealie + Walmart + Browserless) at runtime.

**Files:**
- `mealie_to_cart/config.py`

**Steps:**
1. Implement `Config.load_from_infisical(env="dev")` that calls `skills/infisical-secrets/scripts/infisical.py get`.
2. Validate required keys exist and are non-empty.

**Verification:**
- `cd projects/mealie-to-cart && python -m mealie_to_cart config check`

**Done criteria:**
- Prints which keys are present (never prints secret values).

---

## Task 2 — Mealie API discovery + client
**Goal:** Confirm exact Mealie endpoints for shopping lists on your instance and implement fetching.

**Files:**
- `mealie_to_cart/mealie_client.py`
- `mealie_to_cart/http.py`

**Steps:**
1. Use `MEALIE_URL/docs` OpenAPI to identify:
   - list shopping lists
   - fetch items for a list
2. Implement a tiny HTTP wrapper using `requests`.
3. Implement:
   - `get_shopping_list_by_name("Walmart")`
   - `get_list_items(list_id)`

**Verification:**
- `python -m mealie_to_cart mealie dump --list Walmart --limit 5`
  - Expected: prints 5 raw item lines.

**Done criteria:**
- We can reliably pull the “Walmart” list items.

---

## Task 3 — Normalization & parsing (fractions, parenthetical grams, “or” fallback)
**Goal:** Convert raw Mealie lines into structured `NormalizedItem`s.

**Files:**
- `mealie_to_cart/normalize.py`
- `mealie_to_cart/models.py`
- `mealie_to_cart/tests/test_normalize.py`

**Steps:**
1. Parse leading quantities including fractions (e.g. `1/3`, `2 1/2`).
2. Parse common units (cup/tbsp/tsp/oz/lb/g/kg/ml/l) with best-effort conversions.
3. Handle parenthetical grams, prefer grams for weight when available.
4. Implement “or” behavior:
   - try left option first
   - if no match later, retry with right option

**Verification:**
- `pytest -q`
- A small test corpus including the screenshot examples.

**Done criteria:**
- Normalizer outputs consistent fields; tests pass.

---

## Task 4 — Browserless Playwright wiring (connect + simple page test)
**Goal:** Confirm we can connect to Browserless from the runtime and interact with a page.

**Files:**
- `mealie_to_cart/browser.py`

**Steps:**
1. Use Playwright to connect over CDP to Browserless.
2. Open a simple page, take a screenshot to `artifacts/`.

**Verification:**
- `python -m mealie_to_cart browserless smoke`
  - Expected: creates `artifacts/smoke.png`.

**Done criteria:**
- CDP connection works reliably.

---

## Task 5 — Walmart login + session persistence
**Goal:** Implement login and persist storage state.

**Files:**
- `mealie_to_cart/walmart.py`
- `data/walmart_storage_state.json` (generated)

**Steps:**
1. Implement `ensure_logged_in()`:
   - attempt to load existing storage state
   - if not logged in, perform login flow
2. Save updated storage state after login.

**Verification:**
- `python -m mealie_to_cart walmart login`
  - Expected: ends on a logged-in page and writes storage state.

**Done criteria:**
- Second run does not require login.

---

## Task 6 — Walmart search + results extraction
**Goal:** Given a query string, return a list of structured candidates.

**Files:**
- `mealie_to_cart/walmart.py`
- `mealie_to_cart/models.py`

**Steps:**
1. Implement `search(query) -> list[WalmartCandidate]`.
2. Extract: title, url, size text (if present).

**Verification:**
- `python -m mealie_to_cart walmart search "honey" --limit 5`
  - Expected: prints 5 candidates with URLs.

**Done criteria:**
- Search returns candidates with stable URLs.

---

## Task 7 — Matching + “closest bigger size”
**Goal:** Choose the best candidate using text relevance + size selection.

**Files:**
- `mealie_to_cart/match.py`
- `mealie_to_cart/tests/test_match.py`

**Steps:**
1. Implement size parsing from candidate size strings.
2. Implement scoring and selection:
   - exact match best
   - else smallest >= requested
   - else highest relevance (flag undersized)

**Verification:**
- `pytest -q`

**Done criteria:**
- Deterministic selection; tests cover core cases.

---

## Task 8 — Add to cart
**Goal:** Add selected product to cart from either search card or PDP.

**Files:**
- `mealie_to_cart/walmart.py`

**Steps:**
1. Implement `add_to_cart(candidate)`.
2. Validate cart count increased (best-effort; UI dependent).

**Verification:**
- `python -m mealie_to_cart walmart add "<product_url>"`
  - Expected: item appears in cart.

**Done criteria:**
- At least one product can be added reliably.

---

## Task 9 — End-to-end sync (dry-run first)
**Goal:** Wire everything together with good reporting.

**Files:**
- `mealie_to_cart/main.py`
- `mealie_to_cart/report.py`

**Steps:**
1. Implement `sync --dry-run`:
   - fetch list items
   - normalize
   - search + choose best
   - do not add
   - output report JSON
2. Implement `sync` (real add-to-cart).

**Verification:**
- `python -m mealie_to_cart sync --dry-run --limit 5`
- `python -m mealie_to_cart sync --limit 5`

**Done criteria:**
- Dry-run produces a meaningful report; real run adds items.

---

## Task 10 — Dockge deployment (compose)
**Goal:** Run the CLI in a container on Dockge.

**Files:**
- `projects/mealie-to-cart/docker/Dockerfile`
- `projects/mealie-to-cart/compose.yaml`

**Steps:**
1. Build a slim container image.
2. Provide compose service with a volume for `data/` and `artifacts/`.
3. Document how to run a manual sync (docker exec / compose run).

**Verification:**
- `docker compose run --rm mealie-to-cart sync --dry-run --limit 5`

**Done criteria:**
- Dockge stack can run manual sync.

---

## Approval
If this plan looks good, reply **“approved”** (or “ship it”). Then I’ll start implementing Task 0 onward.
