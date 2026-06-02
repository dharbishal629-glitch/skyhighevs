"""Shared utilities for all quest modules."""

from __future__ import annotations
import base64
import json
import random
import time
import threading
from typing import Optional

import requests

BASE_URL = "https://discord.com/api/v9"

# ── Web-browser headers (used for enroll / heartbeat / hypesquad) ─────────────
_WEB_SUPER = base64.b64encode(json.dumps({
    "os": "Windows",
    "browser": "Chrome",
    "device": "",
    "system_locale": "en-US",
    "has_client_mods": False,
    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "browser_version": "138.0.0.0",
    "os_version": "10",
    "referrer": "",
    "referring_domain": "",
    "referrer_current": "",
    "referring_domain_current": "",
    "release_channel": "stable",
    "client_build_number": 417266,
    "client_event_source": None,
}, separators=(",", ":")).encode()).decode()

WEB_HEADERS_TEMPLATE: dict = {
    "accept":             "*/*",
    "accept-language":    "en-US,en;q=0.9",
    "content-type":       "application/json",
    "origin":             "https://discord.com",
    "referer":            "https://discord.com/channels/@me",
    "sec-ch-ua":          '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest":     "empty",
    "sec-fetch-mode":     "cors",
    "sec-fetch-site":     "same-origin",
    "user-agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "x-debug-options":    "bugReporterEnabled",
    "x-discord-locale":   "en-US",
    "x-discord-timezone": "America/New_York",
    "x-super-properties": _WEB_SUPER,
}

# ── Discord desktop-client headers (used for quest discovery) ─────────────────
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9188 Chrome/132.0.6834.210 "
    "Electron/34.3.2 Safari/537.36"
)

_DESKTOP_SUPER = base64.b64encode(json.dumps({
    "os": "Windows",
    "browser": "Discord Client",
    "release_channel": "stable",
    "client_version": "1.0.9188",
    "os_version": "10.0.22621",
    "os_arch": "x64",
    "app_arch": "x64",
    "system_locale": "en-US",
    "browser_user_agent": _DESKTOP_UA,
    "browser_version": "34.3.2",
    "client_build_number": 417266,
    "native_build_number": 57348,
    "client_event_source": None,
}, separators=(",", ":")).encode()).decode()

DESKTOP_HEADERS_TEMPLATE: dict = {
    "accept":             "*/*",
    "accept-language":    "en-US,en;q=0.9",
    "content-type":       "application/json",
    "origin":             "https://discord.com",
    "referer":            "https://discord.com/channels/@me",
    "user-agent":         _DESKTOP_UA,
    "x-debug-options":    "bugReporterEnabled",
    "x-discord-locale":   "en-US",
    "x-discord-timezone": "America/New_York",
    "x-super-properties": _DESKTOP_SUPER,
}

# Keep old name as alias so other modules don't break
HEADERS_TEMPLATE = WEB_HEADERS_TEMPLATE


def make_session(proxy: Optional[str] = None) -> requests.Session:
    sess = requests.Session()
    sess.verify = False
    if proxy:
        p = proxy.strip()
        if not p.startswith("http"):
            p = f"http://{p}"
        sess.proxies = {"http": p, "https": p}
    return sess


def discord_headers(token: str) -> dict:
    """Web-browser headers — used for enroll / heartbeat / hypesquad."""
    h = WEB_HEADERS_TEMPLATE.copy()
    h["authorization"] = token
    return h


def discord_desktop_headers(token: str) -> dict:
    """Desktop-client headers — used for quest discovery."""
    h = DESKTOP_HEADERS_TEMPLATE.copy()
    h["authorization"] = token
    return h


def extract_token(line: str) -> str:
    """Handle plain token, email:pass:token, or token:email:pass formats."""
    line = line.strip()
    parts = line.split(":")
    if len(parts) >= 3:
        for p in reversed(parts):
            if len(p) > 50 and "." in p:
                return p
        return parts[-1]
    return line


def mask(token: str) -> str:
    if len(token) < 20:
        return token
    return token[:10] + "***"


def pick_proxy(proxies: list[str], idx: int) -> Optional[str]:
    if not proxies:
        return None
    return proxies[idx % len(proxies)]


def run_threaded(
    worker_fn,
    items: list,
    threads: int,
    log_func,
    on_success,
    on_fail,
):
    """Generic thread-pool runner. worker_fn(item, log, on_success, on_fail)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    lock = threading.Lock()

    def _wrap(item):
        worker_fn(item, log_func, on_success, on_fail)

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        futures = [pool.submit(_wrap, item) for item in items]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                with lock:
                    log_func("ERROR", f"Unhandled thread error: {exc}")
