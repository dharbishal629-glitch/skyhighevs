"""QuestCompleter — fake-progress Discord quests to completion via video or activity heartbeats."""

from __future__ import annotations
import time
import random

from ._base import (
    BASE_URL, make_session, discord_headers,
    extract_token, mask, pick_proxy, run_threaded,
)


class QuestCompleter:
    def __init__(
        self,
        proxies:          list[str],
        use_proxies:      bool,
        speed_multiplier: int  = 10,
        target_seconds:   int  = 900,
        quest_type:       str  = "video",
    ):
        self.proxies          = proxies if use_proxies else []
        self.use_proxies      = use_proxies
        self.speed_multiplier = max(1, int(speed_multiplier))
        self.target_seconds   = int(target_seconds)
        self.quest_type       = quest_type

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
                try:
                    result = self._complete_one(qid, token, proxy, log, m)
                    if not result:
                        all_ok = False
                except Exception as e:
                    log("FAIL", f"{m} quest {qid}: unexpected error: {e}")
                    all_ok = False

            (ok if all_ok else fail)(raw)

        run_threaded(worker, items, threads, log_func, on_success, on_fail)

    def _complete_one(self, quest_id: str, token: str, proxy, log, m: str) -> bool:
        sess = make_session(proxy)
        hdrs = discord_headers(token)

        # Step 1: get quest info (enrolled status + stream_key)
        r = sess.get(f"{BASE_URL}/users/@me/quests", headers=hdrs, timeout=20)
        if r.status_code != 200:
            log("FAIL", f"{m} could not fetch quests: HTTP {r.status_code}")
            return False

        enrolled_quests = r.json() if isinstance(r.json(), list) else []
        quest_data = next(
            (q for q in enrolled_quests if str(q.get("quest_id", "")) == str(quest_id)),
            None,
        )

        if not quest_data:
            log("FAIL", f"{m} not enrolled in quest {quest_id} — enroll first")
            return False

        stream_key = quest_data.get("stream_key", "")
        config     = quest_data.get("config", {})
        target_s   = self.target_seconds

        # Try to read target from quest config
        if self.quest_type == "video":
            video_cfg = config.get("video", config)
            target_s  = int(video_cfg.get("seconds", video_cfg.get("required_seconds", target_s)))

        log("INFO", f"{m} quest {quest_id} | target: {target_s}s | stream_key: {'yes' if stream_key else 'NO'}")

        if self.quest_type == "video":
            return self._send_video_heartbeats(sess, hdrs, quest_id, stream_key, target_s, log, m)
        else:
            return self._send_activity_heartbeats(sess, hdrs, quest_id, target_s, log, m)

    def _send_video_heartbeats(
        self, sess, hdrs, quest_id, stream_key, target_s, log, m
    ) -> bool:
        """Send video-watch heartbeats until target reached."""
        interval   = 30               # send heartbeat every 30 real seconds
        fake_step  = interval * self.speed_multiplier  # fake seconds per heartbeat
        watched    = 0
        consecutive_fails = 0
        MAX_FAILS  = 5

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
                log("WARN", f"{m} heartbeat network error: {e}")
                time.sleep(5)
                consecutive_fails += 1
                if consecutive_fails >= MAX_FAILS:
                    log("FAIL", f"Video: {MAX_FAILS} consecutive errors | {m}")
                    return False
                continue

            if r.status_code in (200, 201, 204):
                watched = min(watched + fake_step, target_s)
                pct = round(watched / target_s * 100)
                log("PROGRESS", f"{m} | {watched}/{target_s}s ({pct}%)")
                consecutive_fails = 0
                if watched >= target_s:
                    break
                time.sleep(max(1, interval // self.speed_multiplier))
            elif r.status_code == 400:
                body = _safe_json(r)
                msg  = body.get("message", r.text[:120])
                log("WARN", f"Video: Bad Request — {msg} | {m}")
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    log("FAIL", f"Video: Bad Request (3 consecutive) | {m}")
                    return False
                # Back off and retry — stream_key may be stale
                time.sleep(5)
            elif r.status_code == 401:
                log("FAIL", f"{m} invalid token (401)")
                return False
            else:
                log("WARN", f"{m} heartbeat HTTP {r.status_code}: {r.text[:80]}")
                consecutive_fails += 1
                if consecutive_fails >= MAX_FAILS:
                    log("FAIL", f"Video: too many errors | {m}")
                    return False
                time.sleep(5)

        log("SUCCESS", f"{m} quest {quest_id} video complete ({watched}s watched)")
        return True

    def _send_activity_heartbeats(self, sess, hdrs, quest_id, target_s, log, m) -> bool:
        """Activity quest heartbeats (simpler — no stream_key needed)."""
        interval  = 60
        fake_step = interval * self.speed_multiplier
        done      = 0

        while done < target_s:
            try:
                r = sess.post(
                    f"{BASE_URL}/quests/{quest_id}/heartbeat",
                    headers=hdrs,
                    json={"timestamp": int(time.time() * 1000)},
                    timeout=20,
                )
            except Exception as e:
                log("WARN", f"{m} activity heartbeat error: {e}")
                time.sleep(5)
                continue

            if r.status_code in (200, 201, 204):
                done = min(done + fake_step, target_s)
                log("PROGRESS", f"{m} activity | {done}/{target_s}s")
                time.sleep(max(1, interval // self.speed_multiplier))
            elif r.status_code == 401:
                log("FAIL", f"{m} invalid token")
                return False
            else:
                log("WARN", f"{m} activity heartbeat {r.status_code}: {r.text[:60]}")
                time.sleep(5)

        log("SUCCESS", f"{m} quest {quest_id} activity complete")
        return True


def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {}
