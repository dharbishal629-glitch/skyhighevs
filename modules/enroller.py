"""QuestEnroller — enroll Discord tokens in one or more quest IDs."""

from __future__ import annotations
import time
from typing import Optional

from ._base import (
    BASE_URL, make_session, discord_headers,
    extract_token, mask, pick_proxy, run_threaded,
)


class QuestEnroller:
    def __init__(self, proxies: list[str], use_proxies: bool):
        self.proxies     = proxies if use_proxies else []
        self.use_proxies = use_proxies

    def run(
        self,
        tokens:     list[str],
        quest_ids:  list[str],
        threads:    int,
        log_func,
        on_success,
        on_fail,
    ):
        items = [(i, t) for i, t in enumerate(tokens)]

        def worker(item, log, ok, fail):
            idx, raw = item
            token = extract_token(raw)
            proxy = pick_proxy(self.proxies, idx)
            m = mask(token)

            for qid in quest_ids:
                try:
                    sess = make_session(proxy)
                    hdrs = discord_headers(token)
                    url  = f"{BASE_URL}/users/@me/quests/{qid}"
                    r = sess.put(url, headers=hdrs, json={}, timeout=20)

                    if r.status_code in (200, 201):
                        log("SUCCESS", f"Enrolled {m} in quest {qid}")
                    elif r.status_code == 204:
                        log("SUCCESS", f"Enrolled {m} in quest {qid} (no content)")
                    elif r.status_code == 400:
                        body = _safe_json(r)
                        code = body.get("code", "")
                        msg  = body.get("message", r.text[:120])
                        if code == 50006 or "already" in msg.lower():
                            log("INFO", f"{m} already enrolled in quest {qid}")
                        else:
                            log("FAIL", f"{m} quest {qid}: {msg}")
                    elif r.status_code == 401:
                        log("FAIL", f"{m} invalid token (401)")
                        fail(raw)
                        return
                    else:
                        log("FAIL", f"{m} quest {qid}: HTTP {r.status_code} {r.text[:80]}")
                except Exception as e:
                    log("FAIL", f"{m} quest {qid}: {e}")

            ok(raw)

        run_threaded(worker, items, threads, log_func, on_success, on_fail)


def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {}
