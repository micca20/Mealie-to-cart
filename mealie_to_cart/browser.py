from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright


@dataclass(frozen=True)
class BrowserlessConfig:
    ws_endpoint: str


def browserless_ws_endpoint(*, base_ws_url: str, token: str) -> str:
    """Compose a Browserless CDP websocket endpoint.

    Accepts either:
    - ws://host:port
    - http://host:port

    Returns:
    - ws://host:port?token=...
    """
    base = base_ws_url.strip()
    if base.startswith("http://"):
        base = "ws://" + base.removeprefix("http://")
    if base.startswith("https://"):
        base = "wss://" + base.removeprefix("https://")

    if "?" in base:
        # If caller already provided query params, append.
        if "token=" in base:
            return base
        return base + "&token=" + token

    return base + "?token=" + token


def smoke_test(*, ws_endpoint: str, out_path: str = "artifacts/smoke.png") -> str:
    """Connect to Browserless and write a screenshot of a simple page."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws_endpoint)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto("https://example.com", wait_until="domcontentloaded", timeout=30_000)
        page.screenshot(path=str(out), full_page=True)
        browser.close()

    return str(out)
