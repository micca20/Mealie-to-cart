# Mealie to Cart — Spec

## Problem
Manually transferring items from a Mealie shopping list to a Walmart grocery cart is tedious and error-prone. We want to automate it.

## Solution
A tool that reads the current Mealie shopping list via its API, intelligently matches each item to a Walmart grocery product using browser automation, and adds them to the Walmart cart — triggered manually.

## Must-haves (v1)

- **Mealie integration**: Pull the active shopping list from Mealie's API (URL + API key stored in Infisical).
- **Smart matching**: Parse ingredient names, quantities, and units from the shopping list. Search Walmart grocery for each item and pick the closest match, preferring the next size up when an exact size isn't available (e.g. 3oz requested → pick 4oz).
- **Walmart browser automation**: Use Playwright via the existing Browserless instance on Dockge (`192.168.1.220:3100`) to log into Walmart, search items, and add to cart.
- **Manual trigger**: Invoked on-demand (CLI/script or via Nova command), not scheduled.
- **Walmart auth**: Handle Walmart login (credentials stored in Infisical). Persist session/cookies where possible to avoid re-login every run.
- **Run summary**: After a run, report what was added, what couldn't be matched, and any errors.

## Non-goals (v1)

- Price comparison or optimization
- Multi-store support
- Automatic/scheduled triggering
- Substitution preferences or brand loyalty
- Quantity aggregation across multiple recipes (use Mealie's list as-is)

## Architecture

- **Runtime**: Python script/service, runs from OpenClaw container or Dockge
- **Browser**: Connects to Browserless CDP endpoint on Dockge (`ws://192.168.1.220:3100`)
- **Secrets**: Mealie API key/URL and Walmart credentials pulled from Infisical at runtime (using existing `infisical.py` helper)
- **Mealie API**: REST API to fetch shopping list items
- **Matching engine**: Parse quantity/unit/item from Mealie entries → search Walmart → score results by relevance and size proximity → pick best match

## Flow

1. Pull shopping list from Mealie API
2. Parse each item (name, quantity, unit)
3. For each item:
   - Search Walmart grocery via browser
   - Score results (name relevance + size match, prefer next-size-up)
   - Add best match to cart
4. Return summary: added / skipped / errored items

## Constraints

- Walmart has no public grocery API — browser automation is the only path
- Walmart's site may change; selectors will need maintenance
- Browserless token required for CDP connection

## Resolved Questions

- **Shopping list**: Use a list named **"Walmart"** in Mealie.
- **Walmart account**: Credentials stored in Infisical; delivery/pickup setup TBD by Mike.
- **Runtime**: Standalone Python (not n8n).

## Status
**Approved** — 2026-02-22
