from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, Browser

from .models import WalmartCandidate

# Default CDP endpoint for the Kasm browser
DEFAULT_CDP_URL = "http://192.168.1.220:9222"


@dataclass(frozen=True)
class WalmartConfig:
    email: str
    password: str
    ws_endpoint: str
    cdp_url: str = DEFAULT_CDP_URL
    storage_state_path: str = "data/walmart_storage_state.json"


def _open_page(ws_endpoint: str, *, storage_state_path: str | None = None) -> tuple[object, object, Page]:
    """Open a NEW browser context/page via Browserless CDP (legacy, for headless tasks)."""
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(ws_endpoint)

    kwargs = {"ignore_https_errors": True}
    if storage_state_path and Path(storage_state_path).exists():
        kwargs["storage_state"] = storage_state_path

    context = browser.new_context(**kwargs)
    page = context.new_page()
    return p, browser, page


def _connect_kasm(cdp_url: str = DEFAULT_CDP_URL) -> tuple[object, Browser, Page]:
    """Connect to the existing Kasm browser session (authenticated, visible).

    Returns (playwright_instance, browser, active_page).
    Reuses the first page of the first context (the user's logged-in tab).
    """
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(cdp_url)
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    return p, browser, page


class WalmartSession:
    """Persistent CDP connection for an entire sync run.

    Usage::

        with WalmartSession(cdp_url) as session:
            results = search("honey", session=session)
            add_to_cart(url, session=session)

    The browser stays connected the whole time — no repeated
    connect/disconnect cycles that trigger bot detection.
    """

    def __init__(self, cdp_url: str = DEFAULT_CDP_URL):
        self.cdp_url = cdp_url
        self._pw = None
        self._browser = None
        self.page: Page | None = None

    def __enter__(self) -> "WalmartSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        ctx = self._browser.contexts[0]
        self.page = ctx.pages[0]
        return self

    def __exit__(self, *exc):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
        self._pw = None
        self._browser = None
        self.page = None


def open_home_and_screenshot(*, ws_endpoint: str, out_path: str = "artifacts/walmart_home.png") -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    p, browser, page = _open_page(ws_endpoint)
    try:
        page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out), full_page=True)
        return str(out)
    finally:
        try:
            browser.close()
        finally:
            p.stop()


def ensure_logged_in(cfg: WalmartConfig) -> str:
    """Log into Walmart and persist cookies/storage state.

    Output: path to the saved storage state JSON.

    Assumptions:
    - No MFA/CAPTCHA required (per Mike)
    """
    Path(cfg.storage_state_path).parent.mkdir(parents=True, exist_ok=True)

    p, browser, page = _open_page(cfg.ws_endpoint, storage_state_path=cfg.storage_state_path)
    try:
        # If already logged in, we should see the account link/menu.
        page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1000)

        if _is_logged_in(page):
            page.context.storage_state(path=cfg.storage_state_path)
            return cfg.storage_state_path

        # Navigate to sign-in
        page.goto("https://www.walmart.com/account/login", wait_until="domcontentloaded", timeout=45_000)

        # Fill credentials (do NOT log/print them)
        _fill_login_form(page, email=cfg.email, password=cfg.password)

        # Wait for redirect / logged-in UI
        page.wait_for_timeout(2500)
        page.wait_for_load_state("domcontentloaded", timeout=45_000)

        if not _is_logged_in(page):
            # Save a debug screenshot for selector/captcha issues.
            Path("artifacts").mkdir(exist_ok=True)
            page.screenshot(path="artifacts/walmart_login_failed.png", full_page=True)
            raise RuntimeError(
                "Walmart login did not reach a logged-in state. "
                "Saved artifacts/walmart_login_failed.png"
            )

        # Persist session
        page.context.storage_state(path=cfg.storage_state_path)
        return cfg.storage_state_path

    finally:
        try:
            browser.close()
        finally:
            p.stop()


def search(
    query: str,
    *,
    limit: int = 5,
    cdp_url: str = DEFAULT_CDP_URL,
    session: WalmartSession | None = None,
    _delay_range: tuple[float, float] = (2.0, 5.0),
) -> list[WalmartCandidate]:
    """Search Walmart via the authenticated Kasm browser and return structured candidates.

    If *session* is provided the existing persistent connection is reused
    (no connect/disconnect overhead).  Otherwise falls back to a one-off
    CDP connection for backward compatibility.
    """
    # Human-like pacing
    delay = random.uniform(*_delay_range)
    time.sleep(delay)

    # --- get the page -------------------------------------------------
    own_connection = session is None
    if own_connection:
        p, browser, page = _connect_kasm(cdp_url)
    else:
        p = browser = None
        page = session.page

    try:
        # Navigate to Walmart home for a clean search state
        page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(random.randint(2500, 4000))

        if _is_blocked(page):
            page.wait_for_timeout(random.randint(8000, 15000))
            page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(3000)
            if _is_blocked(page):
                if not _wait_for_captcha_clear(page):
                    raise RuntimeError("Walmart bot block detected — CAPTCHA not solved in time.")

        _search_via_bar(page, query)

        cards = page.query_selector_all("[data-item-id]")
        candidates: list[WalmartCandidate] = []

        for card in cards:
            if len(candidates) >= limit:
                break
            parsed = _parse_product_card(card)
            if parsed is not None:
                candidates.append(parsed)

        return candidates
    finally:
        if own_connection:
            browser.close()
            p.stop()


def _dismiss_overlays(page: Page) -> None:
    """Try to dismiss common Walmart popups/overlays that block interaction."""
    dismiss_selectors = [
        # ATC confirmation dialog close button (the one that was blocking us)
        'button[data-dca-intent="close"][aria-label="Close dialog"]',
        'button[aria-label="Close dialog"]',
        # Generic close / dismiss buttons
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        'button:has-text("Close")',
        'button:has-text("No thanks")',
        'button:has-text("Dismiss")',
        'button:has-text("Not now")',
        '[data-testid="modal-close"]',
        '[data-testid="close-button"]',
        '.close-button',
    ]
    for sel in dismiss_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(force=True)
                page.wait_for_timeout(500)
        except Exception:
            pass


CAPTCHA_POLL_INTERVAL = 10  # seconds between checks
CAPTCHA_TIMEOUT = 300  # 5 minutes max wait


def _wait_for_captcha_clear(page: Page, timeout: int = CAPTCHA_TIMEOUT) -> bool:
    """Poll until the CAPTCHA/bot block is cleared or timeout expires.

    Returns True if cleared, False if timed out.
    """
    elapsed = 0
    print("  ⏳ CAPTCHA detected — waiting for manual solve in Kasm browser...")
    while elapsed < timeout:
        time.sleep(CAPTCHA_POLL_INTERVAL)
        elapsed += CAPTCHA_POLL_INTERVAL
        try:
            # Navigate to homepage instead of reloading the /blocked URL
            page.goto("https://www.walmart.com/", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2000)
        except Exception:
            pass
        if not _is_blocked(page):
            print(f"  ✅ CAPTCHA cleared after ~{elapsed}s")
            return True
        print(f"  ⏳ Still blocked ({elapsed}s / {timeout}s)...")
    print(f"  ❌ CAPTCHA not cleared after {timeout}s — giving up")
    return False


def _is_blocked(page: Page) -> bool:
    """Detect if Walmart has blocked us (CAPTCHA / bot check)."""
    url = page.url or ""
    title = (page.title() or "").lower()
    if "/blocked" in url or "robot or human" in title:
        return True
    return False


def _search_via_bar(page: Page, query: str) -> None:
    """Type a query into Walmart's search bar and press Enter.

    This mimics real user interaction and avoids PerimeterX bot detection
    that triggers on direct page.goto() to search URLs.
    """
    if _is_blocked(page):
        if not _wait_for_captcha_clear(page):
            raise RuntimeError("Walmart bot block detected — CAPTCHA not solved in time.")

    _dismiss_overlays(page)

    search_input = page.wait_for_selector(
        'input[type="search"], input[name="q"]', timeout=15_000
    )
    # Force-click to bypass any remaining overlay
    search_input.click(force=True)
    page.wait_for_timeout(random.randint(200, 500))
    search_input.press("Control+a")
    page.wait_for_timeout(random.randint(100, 300))
    search_input.type(query, delay=random.randint(60, 120))
    page.wait_for_timeout(random.randint(800, 1500))
    search_input.press("Enter")
    page.wait_for_timeout(random.randint(4000, 7000))


def _parse_product_card(card) -> WalmartCandidate | None:
    """Extract structured data from a single Walmart product card DOM element."""
    # ---- URL ----
    link_el = card.query_selector("a[link-identifier]")
    href = link_el.get_attribute("href") if link_el else None
    if not href:
        return None
    url = f"https://www.walmart.com{href}" if href.startswith("/") else href

    # ---- Title + price live inside an <h3> ----
    h3_el = card.query_selector("h3")
    h3_text = h3_el.inner_text() if h3_el else ""

    # Price (e.g. "$3.74")
    price_match = re.search(r"\$[\d.]+", h3_text)
    price = price_match.group(0) if price_match else None

    # Title = h3 text minus badge prefix and trailing price/unit-price
    title = h3_text
    for badge in ("Overall pick ", "Best seller ", "Popular pick ", "Rollback "):
        if title.startswith(badge):
            title = title[len(badge) :]
    if price_match:
        title = title[: price_match.start()].strip()
    # Remove any trailing unit-price fragment (e.g. "31.2 ¢/") or "Was" remnant
    title = re.sub(r"\s*[\d.]+\s*¢.*$", "", title).strip()
    title = re.sub(r"\s+Was\s*$", "", title).strip()

    if not title:
        return None

    # ---- Size / weight (often embedded in the title) ----
    size_match = re.search(
        r"(\d+(?:\.\d+)?\s*(?:fl\s*oz|oz|lb|ct|count|pack|ml|l|g|kg|gal))\b",
        title,
        re.IGNORECASE,
    )
    size_text = size_match.group(1) if size_match else None

    # ---- Image ----
    img_el = card.query_selector('img[data-testid="productTileImage"]')
    img_url = img_el.get_attribute("src") if img_el else None

    # ---- Fulfillment badge ----
    ful_el = card.query_selector('[data-automation-id="fulfillment-badge"]')
    fulfillment = ful_el.inner_text().strip() if ful_el else None

    return WalmartCandidate(
        title=title,
        url=url,
        price=price,
        size_text=size_text,
        img_url=img_url,
        fulfillment=fulfillment,
    )


def add_to_cart(
    url: str,
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    session: WalmartSession | None = None,
) -> bool:
    """Navigate to a product page and click Add to Cart.

    Returns True if the cart count visibly increased, False otherwise.
    """
    own_connection = session is None
    if own_connection:
        p, browser, page = _connect_kasm(cdp_url)
    else:
        p = browser = None
        page = session.page

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(random.randint(2000, 4000))

        if _is_blocked(page):
            if not _wait_for_captcha_clear(page):
                raise RuntimeError("Walmart bot block detected on product page — CAPTCHA not solved in time.")

        _dismiss_overlays(page)

        # Try to get current cart count before adding
        before_count = _get_cart_count(page)

        # Look for "Add to cart" button on the PDP
        add_btn = page.query_selector(
            'button[data-testid="add-to-cart-btn"], '
            'button:has-text("Add to cart"), '
            '[data-automation-id="atc-btn"]'
        )
        if not add_btn:
            # Some pages show an "Add" button on a shelf/card
            add_btn = page.query_selector('button:has-text("Add")')

        if not add_btn:
            Path("artifacts").mkdir(exist_ok=True)
            page.screenshot(path="artifacts/add_to_cart_no_btn.png", full_page=True)
            return False

        add_btn.click(force=True)
        page.wait_for_timeout(3000)

        # Dismiss any confirmation overlay that pops up (prevents blocking next actions)
        _dismiss_overlays(page)

        after_count = _get_cart_count(page)

        # Best-effort validation
        if before_count is not None and after_count is not None:
            return after_count > before_count

        # If we can't read count, check for confirmation UI
        confirmation = page.query_selector(
            '[data-testid="atc-confirmation"], '
            ':has-text("Added to cart"), '
            ':has-text("added to your cart")'
        )
        return confirmation is not None

    finally:
        if own_connection:
            browser.close()
            p.stop()


def _get_cart_count(page: Page) -> int | None:
    """Try to read the cart badge count."""
    badge = page.query_selector(
        '[data-testid="cart-count"], '
        '.cart-count, '
        '[aria-label*="Cart"] span'
    )
    if not badge:
        return None
    text = badge.inner_text().strip()
    try:
        return int(text)
    except ValueError:
        return None


def _fill_login_form(page: Page, *, email: str, password: str) -> None:
    # Walmart login UI changes often; keep selectors broad.
    # Try email first.
    page.fill('input[name="email"], input[type="email"]', email)

    # Some flows have a continue button before password.
    try:
        page.click('button:has-text("Continue"), button:has-text("Sign in"), button[type="submit"]')
        page.wait_for_timeout(1200)
    except Exception:
        pass

    page.fill('input[name="password"], input[type="password"]', password)

    # Submit
    page.click('button:has-text("Sign in"), button:has-text("Sign In"), button[type="submit"]')


def _is_logged_in(page: Page) -> bool:
    # Heuristic: logged-in pages typically expose account link/menu.
    # We avoid brittle selectors; just look for common nav text.
    try:
        content = page.content().lower()
    except Exception:
        return False

    # These are weak but surprisingly effective as a first pass.
    if "sign in" in content and "create account" in content:
        return False

    # Look for "account" in header/nav.
    return "account" in content or "my items" in content or "purchase history" in content
