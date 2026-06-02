"""
TrialTrigger — one-shot Nitro trial unlock (April 2026 method):
  For each token:
    1. Try each supplied quest ID → enroll in whichever one Discord accepts
    2. POST /api/v9/quests/{quest_id}/heartbeat  → simulate watching the video
    3. POST /api/v9/hypesquad/online             → set HypeSquad house

  Discord does NOT expose a REST endpoint for quest discovery — quest data is
  pushed via the WebSocket gateway only.  The caller must supply the quest IDs
  visible in their Discord Quest Home.  Different accounts may be targeted at
  different quests, so pass ALL IDs you see and this module will pick the right
  one per token automatically.
"""

from __future__ import annotations
import time
import random
from typing import Optional

from ._base import (
    BASE_URL, make_session, discord_headers,
    extract_token, mask, pick_proxy, run_threaded,
)

_HYPE_HOUSES = [1, 2, 3]
_DEFAULT_TARGET_S = 900   # 15 min — typical Discord video quest length


def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return {}


class TrialTrigger:
    def __init__(
        self,
        proxies,
        use_proxies,
        target_seconds_override=None,
        quest_ids=None,
        # legacy compat
        forced_quest_id=None,
    ):
        self.proxies       = proxies if use_proxies else []
        self.use_proxies   = use_proxies
        self.target_s      = int(target_seconds_override) if target_seconds_override else _DEFAULT_TARGET_S

        # Build the list of quest IDs to try
        ids = list(quest_ids or [])
        if forced_quest_id and forced_quest_id not in ids:
            ids.insert(0, forced_quest_id)
        self.quest_ids = [str(q).strip() for q in ids if str(q).strip()]

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self, tokens, threads, log_func, on_success, on_fail):
        if not self.quest_ids:
            log_func("FAIL", "No quest IDs provided — cannot run Trial Trigger")
            for t in tokens:
                on_fail(t)
            return

        items = [(i, t) for i, t in enumerate(tokens)]

        def worker(item, log, ok, fail):
            idx, raw = item
            token = extract_token(raw)
            proxy = pick_proxy(self.proxies, idx)
            m     = mask(token)
            sess  = make_session(proxy)
            hdrs  = discord_headers(token)

            # 1. Find which quest this token can enroll in
            quest_id, stream_key = self._find_enrollable(sess, hdrs, log, m)
            if not quest_id:
                fail(raw)
                return

            # 2. Watch (heartbeats)
            if not self._watch(quest_id, sess, hdrs, stream_key, self.target_s, log, m):
                fail(raw)
                return

            # 3. HypeSquad
            self._hypesquad(sess, hdrs, log, m)
            ok(raw)

        run_threaded(worker, items, threads, log_func, on_success, on_fail)

    # ── Enroll: try every quest ID until one works ────────────────────────────

    def _find_enrollable(self, sess, hdrs, log, m) -> tuple[str, str]:
        """
        Try each quest_id in order.  Returns (quest_id, stream_key) for the
        first one Discord accepts, or ("", "") if all fail.
        """
        log("INFO", f"{m} trying {len(self.quest_ids)} quest ID(s): {', '.join(self.quest_ids)}")

        for qid in self.quest_ids:
            result = self._try_enroll(qid, sess, hdrs, log, m)
            if result is None:
                # Hard failure (invalid token, etc.) — stop immediately
                return "", ""
            if result is False:
                # This quest not eligible for this token — try next
                continue
            # result is the stream_key string (may be "")
            log("SUCCESS", f"{m} enrolled in quest {qid}")
            return qid, result

        log("FAIL", f"{m} no quest ID worked for this token")
        return "", ""

    def _try_enroll(self, quest_id, sess, hdrs, log, m):
        """
        Attempt PUT /users/@me/quests/{quest_id}.
        Returns:
          str   — stream_key (possibly "") on success (200/201/204)
          False — not eligible (404) or bad request — try next quest
          None  — hard failure (401, repeated 429) — abort token
        """
        url = f"{BASE_URL}/users/@me/quests/{quest_id}"
        for attempt in range(3):
            try:
                r = sess.put(url, headers=hdrs, json={}, timeout=20)
            except Exception as e:
                log("WARN", f"{m} enroll {quest_id} attempt {attempt+1}: {e}")
                time.sleep(3)
                continue

            if r.status_code in (200, 201):
                data = _safe_json(r)
                sk   = data.get("stream_key", "") if isinstance(data, dict) else ""
                return sk

            if r.status_code == 204:
                return ""

            if r.status_code == 400:
                body = _safe_json(r)
                msg  = body.get("message", r.text[:100]) if isinstance(body, dict) else r.text[:100]
                if "already" in msg.lower():
                    log("INFO", f"{m} already enrolled in {quest_id}")
                    sk = self._get_stream_key(quest_id, sess, hdrs)
                    return sk
                log("INFO", f"{m} quest {quest_id} → 400: {msg}")
                return False   # not eligible, try next

            if r.status_code == 401:
                log("FAIL", f"{m} invalid token (401)")
                return None   # hard stop

            if r.status_code == 404:
                log("INFO", f"{m} quest {quest_id} → 404 (not targeted at this account)")
                return False   # try next

            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                log("WARN", f"{m} rate-limited {wait}s")
                time.sleep(wait + 1)
                continue

            log("INFO", f"{m} quest {quest_id} → HTTP {r.status_code}: {r.text[:80]}")
            return False   # unexpected — try next

        return False   # gave up after retries

    def _get_stream_key(self, quest_id, sess, hdrs) -> str:
        try:
            r = sess.get(f"{BASE_URL}/users/@me/quests/{quest_id}", headers=hdrs, timeout=15)
            if r.status_code == 200:
                d = _safe_json(r)
                return d.get("stream_key", "") if isinstance(d, dict) else ""
        except Exception:
            pass
        return ""

    # ── Heartbeats ────────────────────────────────────────────────────────────

    def _watch(self, quest_id, sess, hdrs, stream_key, target_s, log, m) -> bool:
        watched = 0
        consec  = 0

        while watched < target_s:
            payload: dict = {"timestamp": int(time.time() * 1000)}
            if stream_key:
                payload["stream_key"] = stream_key

            try:
                r = sess.post(
                    f"{BASE_URL}/quests/{quest_id}/heartbeat",
                    headers=hdrs,
                    json=payload,
                    timeout=20,
                )
            except Exception as e:
                consec += 1
                log("WARN", f"{m} heartbeat error: {e}")
                if consec >= 5:
                    log("FAIL", f"{m} video: too many errors")
                    return False
                time.sleep(5)
                continue

            if r.status_code in (200, 201, 204):
                resp = _safe_json(r)
                if isinstance(resp, dict):
                    nk = resp.get("stream_key", "")
                    if nk and nk != stream_key:
                        stream_key = nk
                watched  = min(watched + 30, target_s)
                pct      = round(watched / target_s * 100)
                log("PROGRESS", f"{m} {watched}/{target_s}s ({pct}%)")
                consec   = 0
                if watched >= target_s:
                    break
                time.sleep(15)

            elif r.status_code == 400:
                body = _safe_json(r)
                msg  = body.get("message", r.text[:80]) if isinstance(body, dict) else r.text[:80]
                log("WARN", f"{m} heartbeat 400: {msg}")
                consec += 1
                if consec >= 3:
                    log("FAIL", f"{m} heartbeat 400 x3 — stopping")
                    return False
                # Refresh stream_key and retry
                nk = self._get_stream_key(quest_id, sess, hdrs)
                if nk and nk != stream_key:
                    stream_key = nk
                time.sleep(10)

            elif r.status_code == 401:
                log("FAIL", f"{m} invalid token during heartbeat")
                return False

            elif r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                log("WARN", f"{m} rate-limited {wait}s")
                time.sleep(wait + 1)

            else:
                consec += 1
                log("WARN", f"{m} heartbeat HTTP {r.status_code}: {r.text[:60]}")
                if consec >= 5:
                    log("FAIL", f"{m} video: too many errors")
                    return False
                time.sleep(5)

        log("SUCCESS", f"{m} video done ({watched}s)")
        return True

    # ── HypeSquad ─────────────────────────────────────────────────────────────

    def _hypesquad(self, sess, hdrs, log, m):
        house = random.choice(_HYPE_HOUSES)
        names = {1: "Bravery", 2: "Brilliance", 3: "Balance"}
        try:
            r = sess.post(
                f"{BASE_URL}/hypesquad/online",
                headers=hdrs,
                json={"house_id": house},
                timeout=15,
            )
            if r.status_code in (200, 201, 204):
                log("SUCCESS", f"{m} HypeSquad → {names[house]}")
            else:
                log("WARN", f"{m} HypeSquad HTTP {r.status_code}: {r.text[:60]}")
        except Exception as e:
            log("WARN", f"{m} HypeSquad: {e}")
