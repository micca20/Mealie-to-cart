# Mealie to Cart

Sync a Mealie shopping list ("Walmart") into your Walmart grocery cart via browser automation.

## How It Works

1. Reads items from your Mealie shopping list named "Walmart"
2. Normalizes each item (parses quantities, units, fractions, "or" alternatives)
3. Searches Walmart via an authenticated browser session (Kasm CDP)
4. Picks the best match using "closest bigger size" logic
5. Adds matched items to your Walmart cart
6. Outputs a run report (console + JSON)

## Prerequisites

- **Mealie** instance with a shopping list named "Walmart"
- **Kasm** browser session logged into Walmart (CDP on port 9222)
- **Infisical** with secrets: `MEALIE_URL`, `MEALIE_API_KEY`, `WALMART_EMAIL`, `WALMART_PASSWORD`, `BROWSERLESS_URL`, `BROWSERLESS_TOKEN`

## Quick Start (Docker / Dockge)

```bash
# Create a .env with your Infisical credentials
cat > .env <<EOF
INFISICAL_CLIENT_ID=your-client-id
INFISICAL_CLIENT_SECRET=your-client-secret
EOF

# Build
docker compose build

# Dry run (match only, no cart changes)
docker compose run --rm mealie-to-cart sync --dry-run --limit 5

# Real run
docker compose run --rm mealie-to-cart sync

# Limit to N items
docker compose run --rm mealie-to-cart sync --limit 10
```

## CLI Commands

```bash
# Config
mealie-to-cart config keys          # List required secrets
mealie-to-cart config check         # Validate Infisical config

# Mealie
mealie-to-cart mealie dump          # Print shopping list items

# Walmart
mealie-to-cart walmart search "honey" --limit 5
mealie-to-cart walmart add "https://walmart.com/ip/..."

# Sync
mealie-to-cart sync --dry-run       # Match only
mealie-to-cart sync                 # Full run
mealie-to-cart sync --limit 5       # Cap at 5 items
```

## Output

- Console summary with status per item (ADDED / SKIPPED / FAILED / NEEDS_REVIEW)
- JSON report at `artifacts/run_report.json`
