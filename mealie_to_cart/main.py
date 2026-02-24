from __future__ import annotations

import argparse
import time

from .config import REQUIRED_KEYS, Config
from .mealie_client import MealieClient
from .browser import browserless_ws_endpoint, smoke_test
from .normalize import normalize_line
from .match import choose_best
from .report import ItemReport, build_report
from .walmart import WalmartConfig, WalmartSession, ensure_logged_in, open_home_and_screenshot, search as walmart_search, add_to_cart, DEFAULT_CDP_URL



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mealie-to-cart")
    p.add_argument("--version", action="store_true", help="Print version and exit")

    sub = p.add_subparsers(dest="cmd", required=False)

    p_config = sub.add_parser("config", help="Config commands")
    sub_config = p_config.add_subparsers(dest="config_cmd", required=True)

    sub_config.add_parser("keys", help="List required Infisical keys")

    p_check = sub_config.add_parser("check", help="Validate Infisical config is filled")
    p_check.add_argument("--env", default="dev")

    p_browserless = sub.add_parser("browserless", help="Browserless commands")
    sub_browserless = p_browserless.add_subparsers(dest="browserless_cmd", required=True)

    p_smoke = sub_browserless.add_parser("smoke", help="Connect to Browserless and take a screenshot")
    p_smoke.add_argument("--env", default="dev")
    p_smoke.add_argument("--out", default="artifacts/smoke.png")

    p_walmart = sub.add_parser("walmart", help="Walmart commands")
    sub_walmart = p_walmart.add_subparsers(dest="walmart_cmd", required=True)

    p_home = sub_walmart.add_parser("home", help="Open walmart.com and save a screenshot")
    p_home.add_argument("--env", default="dev")
    p_home.add_argument("--out", default="artifacts/walmart_home.png")

    p_login = sub_walmart.add_parser("login", help="Log into Walmart and persist a cookie/session state")
    p_login.add_argument("--env", default="dev")
    p_login.add_argument("--state", default="data/walmart_storage_state.json")

    p_search = sub_walmart.add_parser("search", help="Search Walmart for a product")
    p_search.add_argument("query", help="Search query (e.g. 'honey')")
    p_search.add_argument("--limit", type=int, default=5, help="Max results")
    p_search.add_argument("--cdp", default=DEFAULT_CDP_URL, help="Kasm browser CDP URL")
    p_search.add_argument("--env", default="dev")

    p_add = sub_walmart.add_parser("add", help="Add a product to cart by URL")
    p_add.add_argument("url", help="Walmart product URL")
    p_add.add_argument("--cdp", default=DEFAULT_CDP_URL, help="Kasm browser CDP URL")

    p_mealie = sub.add_parser("mealie", help="Mealie commands")
    sub_mealie = p_mealie.add_subparsers(dest="mealie_cmd", required=True)

    p_dump = sub_mealie.add_parser("dump", help="Dump raw shopping list items")
    p_dump.add_argument("--env", default="dev")
    p_dump.add_argument("--list", default="Walmart")
    p_dump.add_argument("--limit", type=int, default=5)

    p_sync = sub.add_parser("sync", help="End-to-end sync: Mealie list → Walmart cart")
    p_sync.add_argument("--dry-run", action="store_true", help="Match only, do not add to cart")
    p_sync.add_argument("--limit", type=int, default=0, help="Max items (0=all)")
    p_sync.add_argument("--skip", type=int, default=0, help="Skip first N items (resume from where you left off)")
    p_sync.add_argument("--list", default="Walmart", help="Mealie list name")
    p_sync.add_argument("--cdp", default=DEFAULT_CDP_URL, help="Kasm browser CDP URL")
    p_sync.add_argument("--env", default="dev")
    p_sync.add_argument("--delay", type=float, default=3, help="Extra seconds between items (on top of built-in random delays)")

    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    if args.version:
        print("0.1.0")
        return 0

    if args.cmd is None:
        p.print_help()
        return 0

    if args.cmd == "config":
        if args.config_cmd == "keys":
            for k in REQUIRED_KEYS:
                print(k)
            return 0

        if args.config_cmd == "check":
            # Intentionally do not print secret values
            Config.load_from_infisical(env=args.env)
            print(f"OK: Infisical config present for env={args.env}")
            return 0

    if args.cmd == "browserless":
        cfg = Config.load_from_infisical(env=getattr(args, "env", "dev"))
        ws = browserless_ws_endpoint(base_ws_url=cfg.browserless_url, token=cfg.browserless_token)

        if args.browserless_cmd == "smoke":
            out = smoke_test(ws_endpoint=ws, out_path=args.out)
            print(f"OK: wrote {out}")
            return 0

    if args.cmd == "walmart":
        cfg = Config.load_from_infisical(env=getattr(args, "env", "dev"))
        ws = browserless_ws_endpoint(base_ws_url=cfg.browserless_url, token=cfg.browserless_token)

        if args.walmart_cmd == "home":
            out = open_home_and_screenshot(ws_endpoint=ws, out_path=args.out)
            print(f"OK: wrote {out}")
            return 0

        if args.walmart_cmd == "login":
            state = ensure_logged_in(
                WalmartConfig(
                    email=cfg.walmart_email,
                    password=cfg.walmart_password,
                    ws_endpoint=ws,
                    storage_state_path=args.state,
                )
            )
            print(f"OK: saved session state to {state}")
            return 0

        if args.walmart_cmd == "search":
            candidates = walmart_search(
                args.query,
                limit=args.limit,
                cdp_url=args.cdp,
            )
            if not candidates:
                print("No results found.")
                return 1
            for i, c in enumerate(candidates, 1):
                print(f"{i}. {c.title}")
                print(f"   Price: {c.price or 'N/A'}  Size: {c.size_text or 'N/A'}")
                print(f"   URL: {c.url}")
                print()
            return 0

        if args.walmart_cmd == "add":
            ok = add_to_cart(args.url, cdp_url=args.cdp)
            if ok:
                print("OK: item added to cart.")
                return 0
            else:
                print("WARN: could not confirm item was added. Check cart manually.")
                return 1

    if args.cmd == "mealie":
        cfg = Config.load_from_infisical(env=getattr(args, "env", "dev"))
        mc = MealieClient(mealie_url=cfg.mealie_url, api_key=cfg.mealie_api_key)

        if args.mealie_cmd == "dump":
            lst = mc.get_shopping_list_by_name(args.list)
            items = mc.get_list_items(lst.id)
            for it in items[: args.limit]:
                print(it.display)
            return 0

    if args.cmd == "sync":
        return _run_sync(args)

    raise RuntimeError("unreachable")


def _run_sync(args) -> int:
    cfg = Config.load_from_infisical(env=args.env)
    mc = MealieClient(mealie_url=cfg.mealie_url, api_key=cfg.mealie_api_key)

    lst = mc.get_shopping_list_by_name(args.list)
    raw_items = mc.get_list_items(lst.id)
    if args.skip > 0:
        raw_items = raw_items[args.skip:]
    if args.limit > 0:
        raw_items = raw_items[: args.limit]

    print(f"Fetched {len(raw_items)} items from '{args.list}' list.")

    reports: list[ItemReport] = []
    bot_blocked = False

    with WalmartSession(cdp_url=args.cdp) as ws:
        print("Connected to Kasm browser (persistent session).")

        for idx, raw in enumerate(raw_items):
            normalized = normalize_line(raw.display)
            query = normalized.query
            print(f"\n→ [{idx+1}/{len(raw_items)}] {raw.display}")
            print(f"  query: {query}")

            # Extra pacing between items
            if idx > 0 and args.delay > 0:
                time.sleep(args.delay)

            if bot_blocked:
                print("  SKIP: bot block active")
                reports.append(ItemReport(
                    raw=raw.display, query=query, alt_query=normalized.alt_query,
                    chosen_title=None, chosen_url=None, chosen_size_oz=None,
                    chosen_price=None, undersized=False, status="SKIPPED_NO_MATCH",
                ))
                continue

            try:
                candidates = walmart_search(query, limit=5, session=ws)
            except RuntimeError as exc:
                if "bot block" in str(exc).lower() or "captcha" in str(exc).lower():
                    print(f"  BOT BLOCK: {exc}")
                    print("  Aborting remaining searches.")
                    bot_blocked = True
                    reports.append(ItemReport(
                        raw=raw.display, query=query, alt_query=normalized.alt_query,
                        chosen_title=None, chosen_url=None, chosen_size_oz=None,
                        chosen_price=None, undersized=False, status="FAILED",
                    ))
                    continue
                print(f"  ERROR searching: {exc}")
                candidates = []
            except Exception as exc:
                print(f"  ERROR searching: {exc}")
                candidates = []

            if not candidates and normalized.alt_query:
                print(f"  no results, trying alt: {normalized.alt_query}")
                try:
                    candidates = walmart_search(normalized.alt_query, limit=5, session=ws)
                except Exception as exc:
                    print(f"  ERROR searching alt: {exc}")
                    candidates = []

            if not candidates:
                print("  SKIP: no results")
                reports.append(ItemReport(
                    raw=raw.display, query=query, alt_query=normalized.alt_query,
                    chosen_title=None, chosen_url=None, chosen_size_oz=None,
                    chosen_price=None, undersized=False, status="SKIPPED_NO_MATCH",
                ))
                continue

            chosen = choose_best(normalized, candidates)
            if chosen is None:
                print("  SKIP: no match")
                reports.append(ItemReport(
                    raw=raw.display, query=query, alt_query=normalized.alt_query,
                    chosen_title=None, chosen_url=None, chosen_size_oz=None,
                    chosen_price=None, undersized=False, status="SKIPPED_NO_MATCH",
                ))
                continue

            c = chosen.candidate
            tag = "undersized" if chosen.undersized else "ok"
            print(f"  MATCH ({tag}): {c.title}  {c.price or ''}  size={chosen.size_oz}")

            status = "DRY_RUN"
            if not args.dry_run:
                try:
                    ok = add_to_cart(c.url, session=ws)
                    status = "ADDED" if ok else "FAILED"
                except Exception as exc:
                    print(f"  ERROR adding: {exc}")
                    status = "FAILED"

            if chosen.undersized and status == "ADDED":
                status = "NEEDS_REVIEW"

            print(f"  → {status}")
            reports.append(ItemReport(
                raw=raw.display, query=query, alt_query=normalized.alt_query,
                chosen_title=c.title, chosen_url=c.url,
                chosen_size_oz=chosen.size_oz, chosen_price=c.price,
                undersized=chosen.undersized, status=status,
            ))

    report = build_report(reports, dry_run=args.dry_run)
    print("\n" + report.summary_text())
    path = report.write_json()
    print(f"\nReport written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
