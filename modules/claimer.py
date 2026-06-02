"""QuestClaimer — claim completed Discord quest rewards."""

from __future__ import annotations
import time

from ._base import (
    BASE_URL, make_session, discord_headers,
    extract_token, mask, pick_proxy, run_threaded,
)


class QuestClaimer:
    def __init__(
        self,
        proxies:         list[str],
        use_proxies:     bool,
        captcha_api_key: str = "",
    ):
        self.proxies         = proxies if use_proxies else []
        self.use_proxies     = use_proxies
        self.captcha_api_key = captcha_api_key

    def run(
        self,
        tokens:    list[str],
        quest_ids: list[str],
        threads:   int,
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

            all_ok = True
            for qid in quest_ids:
                if not self._claim_one(qid, token, proxy, log, m):
                    all_ok = False

            (ok if all_ok else fail)(raw)

        run_threaded(worker, items, threads, log_func, on_success, on_fail)

    def _claim_one(self, quest_id: str, token: str, proxy, log, m: str) -> bool:
        sess = make_session(proxy)
        hdrs = discord_headers(token)

        for attempt in range(3):
            try:
                r = sess.put(
                    f"{BASE_URL}/users/@me/quests/{quest_id}/redeem",
                    headers=hdrs,
                    json={},
                    timeout=20,
                )
            except Exception as e:
                log("WARN", f"{m} claim network error (attempt {attempt+1}): {e}")
                time.sleep(3)
                continue

            if r.status_code in (200, 201):
                log("SUCCESS", f"{m} claimed quest {quest_id}")
                return True
            elif r.status_code == 204:
                log("SUCCESS", f"{m} claimed quest {quest_id} (204)")
                return True
            elif r.status_code == 400:
                body = _safe_json(r)
                code = body.get("code", "")
                msg  = body.get("message", r.text[:120])
                # Already redeemed
                if code in (50006, 100062) or "already" in msg.lower():
                    log("INFO", f"{m} quest {quest_id} already claimed")
                    return True
                # Captcha required
                if code == 50035 or "captcha" in msg.lower():
                    log("WARN", f"{m} quest {quest_id} requires captcha — skipping (no solver)")
                    return False
                # Quest not complete yet
                if "not complete" in msg.lower() or "progress" in msg.lower():
                    log("FAIL", f"{m} quest {quest_id} not yet complete")
                    return False
                log("FAIL", f"{m} claim quest {quest_id}: {msg}")
                return False
            elif r.status_code == 401:
                log("FAIL", f"{m} invalid token (401)")
                return False
            elif r.status_code == 429:
                retry = int(r.headers.get("Retry-After", "5"))
                log("WARN", f"{m} rate-limited — waiting {retry}s")
                time.sleep(retry + 1)
            else:
                log("WARN", f"{m} claim HTTP {r.status_code}: {r.text[:80]}")
                time.sleep(3)

        log("FAIL", f"{m} claim quest {quest_id}: too many retries")
        return False


def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {}
