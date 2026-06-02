"""BadgeBuyer — purchase the Discord quest badge via VC (virtual currency) redemption."""

from __future__ import annotations
import time

from ._base import (
    BASE_URL, make_session, discord_headers,
    extract_token, mask, pick_proxy, run_threaded,
)

# The VC-based quest badge redemption endpoint and SKU
# Discord gives 500 VC for completing a quest; badge costs 500 VC
_REDEEM_URL = f"{BASE_URL}/users/@me/applications/1019338573560713276/entitlements"
_SKU_ID     = "1019338573560713277"   # Quest Nitro badge SKU (update if Discord changes it)


class BadgeBuyer:
    def __init__(self, proxies: list[str], use_proxies: bool):
        self.proxies     = proxies if use_proxies else []
        self.use_proxies = use_proxies

    def run(
        self,
        tokens:  list[str],
        threads: int,
        log_func,
        on_success,
        on_fail,
    ):
        items = [(i, t) for i, t in enumerate(tokens)]

        def worker(item, log, ok, fail):
            idx, raw = item
            token = extract_token(raw)
            proxy = pick_proxy(self.proxies, idx)
            m     = mask(token)

            if self._buy_one(token, proxy, log, m):
                ok(raw)
            else:
                fail(raw)

        run_threaded(worker, items, threads, log_func, on_success, on_fail)

    def _buy_one(self, token: str, proxy, log, m: str) -> bool:
        sess = make_session(proxy)
        hdrs = discord_headers(token)

        # Step 1: check current VC balance / owned entitlements
        try:
            check = sess.get(
                f"{BASE_URL}/users/@me/applications/1019338573560713276/entitlements",
                headers=hdrs,
                timeout=20,
            )
            if check.status_code == 200:
                owned = check.json() if isinstance(check.json(), list) else []
                if any(str(e.get("sku_id")) == _SKU_ID for e in owned):
                    log("INFO", f"{m} badge already owned")
                    return True
        except Exception as e:
            log("WARN", f"{m} entitlement check error: {e}")

        # Step 2: purchase the badge
        payload = {
            "sku_id":            _SKU_ID,
            "payment_source_id": None,
            "currency":          "premium",   # VC / premium currency
        }

        for attempt in range(3):
            try:
                r = sess.post(_REDEEM_URL, headers=hdrs, json=payload, timeout=20)
            except Exception as e:
                log("WARN", f"{m} badge buy network error (attempt {attempt+1}): {e}")
                time.sleep(3)
                continue

            if r.status_code in (200, 201):
                log("SUCCESS", f"{m} quest badge purchased")
                return True
            elif r.status_code == 400:
                body = _safe_json(r)
                msg  = body.get("message", r.text[:120])
                if "insufficient" in msg.lower():
                    log("FAIL", f"{m} insufficient VC to buy badge")
                    return False
                if "already" in msg.lower():
                    log("INFO", f"{m} badge already owned")
                    return True
                log("FAIL", f"{m} badge buy: {msg}")
                return False
            elif r.status_code == 401:
                log("FAIL", f"{m} invalid token")
                return False
            elif r.status_code == 429:
                retry = int(r.headers.get("Retry-After", "5"))
                log("WARN", f"{m} rate-limited — waiting {retry}s")
                time.sleep(retry + 1)
            else:
                log("WARN", f"{m} badge buy HTTP {r.status_code}: {r.text[:80]}")
                time.sleep(3)

        log("FAIL", f"{m} badge buy: too many retries")
        return False


def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {}
