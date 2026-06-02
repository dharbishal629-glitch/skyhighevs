"""
SkyHighEV — Discord Worker Bot
================================
Admin  : /create-key  /revoke-key  /fetch-tokens  /check-token  /live-check
         /list-workers  /worker-info  /global-stats  /announce  /ping
         /get-credentials  /set-expiry  /broadcast-dm  /reset-stats
         /kick-worker  /uptime
Worker : /leaderboard  /profile  /help  /my-key  /top-today
"""

# ── Python version guard ────────────────────────────────────────────────────
# PIL (Pillow) in this environment is compiled for Python 3.11.
# If someone runs `python bot.py` and lands on 3.12, restart transparently.
import sys as _sys
if _sys.version_info >= (3, 12):
    import os as _os
    _os.execvp("python3.11", ["python3.11"] + _sys.argv)
# ────────────────────────────────────────────────────────────────────────────

import io
import os
import json
import time as _time
import asyncio
import aiohttp
import requests
import pyotp
import discord
import random as _random
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════
#  FILL IN ALL VALUES BELOW BEFORE RUNNING THE BOT
# ══════════════════════════════════════════════════════════════════

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
API_BASE_URL   = os.environ.get("CTRL_API_URL", "https://your-vercel-app.vercel.app")
WORKER_API_KEY = os.environ.get("WORKER_API_KEY", "")
TOTP_SECRET    = os.environ.get("TOTP_SECRET", "")
ADMIN_KEY      = os.environ.get("ADMIN_KEY", "")
ADMIN_IDS      = { 1499372249503895552, 1482575133779427488 }
# Channel where payout request notifications are sent (set to your admin/payout channel ID)
PAYOUT_NOTIFY_CHANNEL_ID = 1491674976787365978   # ← replace 0 with your channel ID
TICKET_CATEGORY_ID       = 1491820563025363045                     # ← set to your ticket category channel ID (0 = no category)

# ══════════════════════════════════════════════════════════════════

API_BASE_URL = API_BASE_URL.rstrip("/")

BOT_START_TIME = _time.time()

# Brand colours
C_BRAND   = 0x7C3AED
C_SUCCESS = 0x10B981
C_ERROR   = 0xEF4444
C_WARN    = 0xF59E0B
C_INFO    = 0x06B6D4
C_GOLD    = 0xF59E0B
C_DARK    = 0x1E1B4B

# ── API Client ─────────────────────────────────────────────────────────────────

def api_headers(admin: bool = False) -> dict:
    totp = pyotp.TOTP(TOTP_SECRET)
    h = {
        "x-api-key":    WORKER_API_KEY,
        "x-totp-code":  totp.now(),
        "Content-Type": "application/json",
    }
    if admin:
        h["x-admin-key"] = ADMIN_KEY
    return h

API_TIMEOUT = 60   # seconds — long enough to survive Render cold starts
API_RETRIES = 2    # total attempts per call

def _api_request(method: str, path: str, admin: bool = False, **kwargs) -> dict:
    url = f"{API_BASE_URL}/api{path}"
    last_err = ""
    for attempt in range(1, API_RETRIES + 1):
        try:
            r = requests.request(
                method, url,
                headers=api_headers(admin=admin),
                timeout=API_TIMEOUT,
                verify=False,
                **kwargs,
            )
            text = r.text.strip()
            if not text:
                last_err = f"API returned empty response (HTTP {r.status_code}) for {method} {path}"
                print(f"[API] {last_err}")
                if attempt < API_RETRIES:
                    continue
                return {"error": last_err}
            try:
                data = r.json()
            except Exception:
                last_err = f"API returned non-JSON (HTTP {r.status_code}): {text[:200]}"
                print(f"[API] {last_err}")
                if attempt < API_RETRIES:
                    continue
                return {"error": last_err}
            if not r.ok and "error" not in data:
                data["error"] = data.get("message", f"HTTP {r.status_code}")
            return data
        except requests.exceptions.Timeout:
            last_err = f"API timed out after {API_TIMEOUT}s (attempt {attempt}/{API_RETRIES})"
            print(f"[API] {last_err}")
        except Exception as e:
            last_err = str(e)
            print(f"[API] Request error (attempt {attempt}/{API_RETRIES}): {e}")
    return {"error": last_err}

def api_post(path: str, body: dict, admin: bool = False) -> dict:
    return _api_request("POST", path, admin=admin, json=body)

def api_get(path: str, params: dict = None, admin: bool = False) -> dict:
    return _api_request("GET", path, admin=admin, params=params or {})

def api_delete(path: str, body: dict = None, admin: bool = False) -> dict:
    return _api_request("DELETE", path, admin=admin, json=body or {})

def api_patch(path: str, body: dict, admin: bool = False) -> dict:
    return _api_request("PATCH", path, admin=admin, json=body)

def api_put(path: str, body: dict, admin: bool = False) -> dict:
    return _api_request("PUT", path, admin=admin, json=body)

# ── Async API helpers (non-blocking — run in thread pool) ─────────────────────

async def aapi_get(path: str, params: dict = None, admin: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: api_get(path, params, admin))

async def aapi_post(path: str, body: dict, admin: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: api_post(path, body, admin))

async def aapi_delete(path: str, body: dict = None, admin: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: api_delete(path, body, admin))

async def aapi_patch(path: str, body: dict, admin: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: api_patch(path, body, admin))

async def aapi_put(path: str, body: dict, admin: bool = False) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: api_put(path, body, admin))

# ── Bot Setup ──────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ── Keep-Alive ─────────────────────────────────────────────────────────────────

@tasks.loop(minutes=14)
async def keep_render_alive():
    try:
        r = requests.get(f"{API_BASE_URL}/api/healthz", timeout=API_TIMEOUT, verify=False)
        print(f"[KEEPALIVE] Render ping — HTTP {r.status_code}")
    except Exception as e:
        print(f"[KEEPALIVE] Ping failed: {e}")

# ── Helpers ────────────────────────────────────────────────────────────────────

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_IDS

def now_ts() -> str:
    return f"<t:{int(datetime.now(timezone.utc).timestamp())}:R>"

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

_FOOTER_TEXT = "SkyHigh Services"
_BRAND_ICON  = "https://cdn.discordapp.com/emojis/1234567890.png"   # placeholder; set to a real URL if you have one

def base_embed(title: str, description: str = "", color: int = C_BRAND) -> discord.Embed:
    e = discord.Embed(title=title, description=description or discord.utils.MISSING, color=color, timestamp=utc_now())
    e.set_footer(text=_FOOTER_TEXT)
    return e

def ok(title: str, desc: str = "") -> discord.Embed:
    return base_embed(f"  {title}", desc, C_SUCCESS)

def err(title: str, desc: str = "") -> discord.Embed:
    return base_embed(f"  {title}", desc, C_ERROR)

def info(title: str, desc: str = "") -> discord.Embed:
    return base_embed(f"ℹ  {title}", desc, C_INFO)

def warn(title: str, desc: str = "") -> discord.Embed:
    return base_embed(f"  {title}", desc, C_WARN)

# ── Components V2 Helpers ─────────────────────────────────────────────────────

CV2_FLAGS = discord.MessageFlags(components_v2=True)

def _td(text: str) -> discord.ui.TextDisplay:
    return discord.ui.TextDisplay(text)

def _sep(large: bool = False) -> discord.ui.Separator:
    sp = discord.SeparatorSpacing.large if large else discord.SeparatorSpacing.small
    return discord.ui.Separator(spacing=sp)

def _cv2_cont(*children, color: int = C_BRAND) -> discord.ui.Container:
    return discord.ui.Container(*children, accent_colour=discord.Colour(color))

class _CV2Layout(discord.ui.LayoutView):
    """Disposable send-only LayoutView wrapping one Container."""
    def __init__(self, container: discord.ui.Container):
        super().__init__(timeout=None)
        self.add_item(container)

def _cv2(color: int, *children) -> "_CV2Layout":
    return _CV2Layout(_cv2_cont(*children, color=color))

def cv2_ok(title: str, desc: str = "", *extras) -> "_CV2Layout":
    kids = [_td(f"## {title}"), _sep()]
    if desc: kids.append(_td(desc))
    kids.extend(extras)
    return _cv2(C_SUCCESS, *kids)

def cv2_err(title: str, desc: str = "", *extras) -> "_CV2Layout":
    kids = [_td(f"## {title}"), _sep()]
    if desc: kids.append(_td(desc))
    kids.extend(extras)
    return _cv2(C_ERROR, *kids)

def cv2_warn(title: str, desc: str = "", *extras) -> "_CV2Layout":
    kids = [_td(f"## {title}"), _sep()]
    if desc: kids.append(_td(desc))
    kids.extend(extras)
    return _cv2(C_WARN, *kids)

def cv2_info(title: str, desc: str = "", *extras) -> "_CV2Layout":
    kids = [_td(f"## {title}"), _sep()]
    if desc: kids.append(_td(desc))
    kids.extend(extras)
    return _cv2(C_INFO, *kids)

def cv2_brand(title: str, desc: str = "", *extras) -> "_CV2Layout":
    kids = [_td(f"## {title}"), _sep()]
    if desc: kids.append(_td(desc))
    kids.extend(extras)
    return _cv2(C_BRAND, *kids)

def fmt_exp(expires: str | None) -> str:
    if not expires:
        return "Never"
    return f"<t:{int(datetime.fromisoformat(expires.replace('Z','+00:00')).timestamp())}:F>"

def fmt_exp_short(expires: str | None) -> str:
    if not expires:
        return "Never"
    return f"<t:{int(datetime.fromisoformat(expires.replace('Z','+00:00')).timestamp())}:d>"

def fmt_join(joined: str | None) -> str:
    if not joined:
        return "Unknown"
    return f"<t:{int(datetime.fromisoformat(joined.replace('Z','+00:00')).timestamp())}:D>"

# ── Admin Guard ────────────────────────────────────────────────────────────────

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_admin(interaction):
            await interaction.response.send_message(
                view=cv2_err("Access Denied", "You do not have permission to use this command."),
                ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

# ── /create-key ───────────────────────────────────────────────────────────────

@bot.tree.command(name="create-key", description="[Admin] Create or renew a worker key")
@app_commands.describe(user="Discord user to give a key", duration="Duration in days (0 = never expires)")
@admin_only()
async def create_key(interaction: discord.Interaction, user: discord.Member, duration: int = 0):
    await interaction.response.defer(ephemeral=True)

    # Check if this user already has an active key
    existing = await aapi_get(f"/workers/profile/{user.id}", admin=True)
    if existing.get("worker") and existing["worker"].get("status") == "VALID":
        worker_key = None
        wlist = await aapi_get("/workers/list", admin=True)
        wdata = next((w for w in wlist.get("workers", []) if w.get("discordId") == str(user.id)), None)
        if wdata:
            worker_key = wdata.get("workerKey")
        exp_str = fmt_exp(existing["worker"].get("expiresAt"))
        kids = [
            _td("## Key Already Active"),
            _sep(),
            _td(f"{user.mention} already has an active worker key.\nRevoke it first using `/revoke-key` before issuing a new one."),
            _td(f"**Status:** VALID  ·  **Expires:** {exp_str}"),
        ]
        if worker_key:
            kids.append(_td(f"**Existing Key:**\n```{worker_key}```"))
        await interaction.followup.send(view=_cv2(C_WARN, *kids), ephemeral=True)
        return

    data = await aapi_post("/workers/create-key", {
        "discordId":       str(user.id),
        "discordUsername": user.name,
        "durationDays":    duration if duration > 0 else None,
    }, admin=True)

    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    worker  = data.get("worker", {})
    exp_str = fmt_exp(worker.get("expiresAt"))

    dm_note = "Key sent to user via DM"
    try:
        dm = base_embed("Your Worker Key", "", C_BRAND)
        dm.description = (
            f"Welcome to SkyHighEV, {user.mention}.\n"
            f"Your personal worker key is ready. Keep it private.\n\n"
            f"```{worker.get('workerKey','N/A')}```"
        )
        dm.add_field(name="Expires", value=exp_str,  inline=True)
        dm.add_field(name="Status",  value="VALID",  inline=True)
        dm.set_footer(text="Do not share this key with anyone  |  SkyHighEV")
        await user.send(embed=dm)
    except discord.Forbidden:
        dm_note = "Could not DM user (DMs closed)"

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Worker Key Issued"),
        _td(f"Key generated for {user.mention}"),
        _sep(),
        _td(f"**Worker Key:**\n```{worker.get('workerKey','N/A')}```"),
        _td(f"**Status:** VALID  ·  **Expires:** {exp_str}  ·  **Discord ID:** `{user.id}`"),
        _td(f"-# {dm_note}  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /revoke-key ───────────────────────────────────────────────────────────────

@bot.tree.command(name="revoke-key", description="[Admin] Revoke/lock a worker key")
@app_commands.describe(user="The Discord user whose key to revoke")
@admin_only()
async def revoke_key(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_delete("/workers/delete-key", {"discordId": str(user.id)}, admin=True)

    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    await interaction.followup.send(view=_cv2(C_WARN,
        _td("## Worker Key Revoked"),
        _sep(),
        _td(f"The key for {user.mention} has been locked and is no longer usable."),
        _td(f"**Discord ID:** `{user.id}`  ·  **Status:** LOCKED"),
    ), ephemeral=True)


# ── /kick-worker ──────────────────────────────────────────────────────────────

@bot.tree.command(name="kick-worker", description="[Admin] Permanently remove a worker from the system")
@app_commands.describe(user="The Discord user to remove entirely")
@admin_only()
async def kick_worker(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    existing = await aapi_get(f"/workers/profile/{user.id}", admin=True)
    if not existing.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Found", f"{user.mention} has no worker profile."), ephemeral=True)
        return

    data = await aapi_delete("/workers/delete-key", {"discordId": str(user.id), "permanent": True}, admin=True)

    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    await interaction.followup.send(view=_cv2(C_ERROR,
        _td("## Worker Removed"),
        _sep(),
        _td(f"{user.mention} has been permanently removed from the worker system."),
        _td(f"**Discord ID:** `{user.id}`  ·  **Status:** REMOVED"),
    ), ephemeral=True)


# ── /set-expiry ───────────────────────────────────────────────────────────────

@bot.tree.command(name="set-expiry", description="[Admin] Update expiry duration on an existing worker key")
@app_commands.describe(user="The Discord user", days="New duration from now in days (0 = never expires)")
@admin_only()
async def set_expiry(interaction: discord.Interaction, user: discord.Member, days: int):
    await interaction.response.defer(ephemeral=True)

    existing = await aapi_get(f"/workers/profile/{user.id}", admin=True)
    if not existing.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Found", f"{user.mention} has no worker profile."), ephemeral=True)
        return

    data = await aapi_patch("/workers/set-expiry", {
        "discordId":    str(user.id),
        "durationDays": days if days > 0 else None,
    }, admin=True)

    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    new_exp = data.get("expiresAt")
    exp_str = fmt_exp(new_exp)
    dur_str = f"{days} days" if days > 0 else "Never"

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Expiry Updated"),
        _sep(),
        _td(f"Worker key expiry for {user.mention} has been updated."),
        _td(f"**New Expiry:** {exp_str}  ·  **Duration:** {dur_str}"),
    ), ephemeral=True)


# ── /reset-stats ──────────────────────────────────────────────────────────────

@bot.tree.command(name="reset-stats", description="[Admin] Reset a worker's daily stats")
@app_commands.describe(user="The Discord user whose daily stats to reset")
@admin_only()
async def reset_stats(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    existing = await aapi_get(f"/workers/profile/{user.id}", admin=True)
    if not existing.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Found", f"{user.mention} has no worker profile."), ephemeral=True)
        return

    data = await aapi_post("/workers/reset-stats", {"discordId": str(user.id)}, admin=True)

    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Daily Stats Reset"),
        _sep(),
        _td(f"Daily stats for {user.mention} have been reset to zero."),
        _td(f"**Discord ID:** `{user.id}`"),
    ), ephemeral=True)


# ── /broadcast-dm ─────────────────────────────────────────────────────────────

@bot.tree.command(name="broadcast-dm", description="[Admin] Send a DM to all registered workers")
@app_commands.describe(subject="Message subject/title", message="Message body to send")
@admin_only()
async def broadcast_dm(interaction: discord.Interaction, subject: str, message: str):
    await interaction.response.defer(ephemeral=True)

    wlist = await aapi_get("/workers/list", admin=True)
    if "error" in wlist:
        await interaction.followup.send(view=cv2_err("API Error", f"```{wlist['error']}```"), ephemeral=True)
        return

    workers = wlist.get("workers", [])
    if not workers:
        await interaction.followup.send(view=cv2_info("No Workers", "No workers are registered."), ephemeral=True)
        return

    sent = 0
    failed = 0
    for w in workers:
        try:
            discord_id = int(w.get("discordId", 0))
            member = bot.get_user(discord_id) or await bot.fetch_user(discord_id)
            dm_embed = base_embed(subject, message, C_BRAND)
            dm_embed.set_footer(text=f"Broadcast from {interaction.user.display_name}  |  SkyHighEV")
            await member.send(embed=dm_embed)
            sent += 1
        except Exception:
            failed += 1

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Broadcast Complete"),
        _sep(),
        _td(f"**Subject:** {subject}"),
        _td(f"**Sent:** {sent}  ·  **Failed:** {failed}  ·  **Total:** {len(workers)}"),
    ), ephemeral=True)


# ── Shared live-check helper ───────────────────────────────────────────────────
#
# Single-call live token validation using GET /users/@me/guilds.
# This is the confirmed-working method from the /live-check command.
#
#   GET /users/@me/guilds
#     200 → VALID   (token alive, account in good standing)
#     403 → LOCKED  (phone-locked / account restricted)
#     401 → INVALID (token revoked or malformed)
#     -1  → ERROR   (network failure — do NOT change status)
#
_GUILDS_URL = "https://discord.com/api/v9/users/@me/guilds"

_HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    ),
    "Content-Type":       "application/json",
    "X-Discord-Locale":   "en-US",
    "X-Super-Properties": (
        "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwi"
        "c3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZX0="
    ),
}

def _get_discord(url: str, token: str, retries: int = 12) -> int:
    """Single GET against Discord API. Returns HTTP status code, or -1 on network failure."""
    hdrs = {**_HDRS, "Authorization": token}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=hdrs, timeout=20, verify=False)
            if resp.status_code == 429:
                try:
                    wait = float(resp.json().get("retry_after", 5.0)) + 1.5
                except Exception:
                    wait = 6.0
                _time.sleep(min(wait, 60.0))
                continue
            if resp.status_code in (500, 502, 503, 504):
                _time.sleep(2.0 * (attempt + 1))
                continue
            return resp.status_code
        except Exception:
            _time.sleep(2.0 * (attempt + 1))
    return -1   # network failure / exhausted retries


def _check_token_sync(token: str) -> str:
    """
    Live token check using GET /users/@me/guilds — the confirmed-working method.

      200 → VALID   (token alive, account in good standing)
      403 → LOCKED  (phone-locked / account restricted)
      401 → INVALID (token revoked or malformed)
      -1  → ERROR   (network failure — do NOT change status)
      *   → ERROR   (unexpected response — do NOT change status)

    Returns: 'VALID', 'LOCKED', 'INVALID', or 'ERROR'
    """
    status = _get_discord(_GUILDS_URL, token)
    if status == 200:
        return "VALID"
    if status == 403:
        return "LOCKED"
    if status == 401:
        return "INVALID"
    return "ERROR"


async def _discord_live_check(token_entries: list, progress: dict | None = None):
    """
    Async wrapper around _check_token_sync.
    Runs checks in a thread pool so `requests` blocking calls don't block the
    event loop, while keeping a semaphore to cap concurrent threads.

    token_entries : list of (label, token_str)
    progress      : optional shared dict {"checked": int} — incremented per result

    Returns: (valid_list, locked_list, invalid_list, error_list)
      valid_list   : list of (label, token_str)
      locked_list  : list of label strings
      invalid_list : list of label strings
      error_list   : list of label strings
    """
    valid_list   = []
    locked_list  = []
    invalid_list = []
    error_list   = []
    _lock        = asyncio.Lock()

    # 3 concurrent threads — avoids hammering Discord from one IP
    semaphore = asyncio.Semaphore(3)

    async def _check_one(label, token):
        async with semaphore:
            # Small async delay between slots to spread requests in time
            await asyncio.sleep(0.5)
            # Run the blocking requests call in a thread
            result = await asyncio.to_thread(_check_token_sync, token)

        async with _lock:
            if result == "VALID":
                valid_list.append((label, token))
            elif result == "LOCKED":
                locked_list.append(label)
            elif result == "INVALID":
                invalid_list.append(label)
            else:
                error_list.append(label)

            if progress is not None:
                progress["checked"] += 1

    await asyncio.gather(*(_check_one(lbl, tok) for lbl, tok in token_entries))

    return valid_list, locked_list, invalid_list, error_list



# ── /fetch-tokens ─────────────────────────────────────────────────────────────

@bot.tree.command(name="fetch-tokens", description="[Admin] Fetch tokens — live-validated via Discord API")
@app_commands.describe(
    worker_key="Filter by specific worker key (optional)",
    discord_user="Filter by Discord user (optional)",
)
@admin_only()
async def fetch_tokens(
    interaction: discord.Interaction,
    worker_key:   str = None,
    discord_user: discord.Member = None,
):
    await interaction.response.defer(ephemeral=True)

    params = {}
    if worker_key:   params["workerKey"] = worker_key
    if discord_user: params["discordId"] = str(discord_user.id)

    data_all = await aapi_get("/tokens/fetch", params=params, admin=True)
    if "error" in data_all:
        await interaction.followup.send(
            view=cv2_err("API Error", f"```{data_all['error']}```"), ephemeral=True)
        return

    all_tokens = data_all.get("tokens", [])
    if not all_tokens:
        await interaction.followup.send(view=cv2_brand("Token Export", "No tokens found matching the given filters."), ephemeral=True)
        return

    total = len(all_tokens)

    # Build entry list for live check
    def fmt_line(label: str) -> str:
        return label   # label is already email:pass:token

    token_entries = []
    for t in all_tokens:
        tok = t.get("token") or ""
        if not tok:
            continue
        label = f"{t.get('email') or ''}:{t.get('accountPass') or ''}:{tok}"
        token_entries.append((label, tok))

    total_entries = len(token_entries)
    progress  = {"checked": 0}
    done_event = asyncio.Event()

    prog_msg = await interaction.followup.send(
        view=_build_progress_cv2(0, total_entries, 0, 0, 0, 0),
        ephemeral=True,
        wait=True,
    )

    async def _ft_updater():
        while not done_event.is_set():
            await asyncio.sleep(4)
            if done_event.is_set():
                break
            try:
                await prog_msg.edit(view=_build_progress_cv2(
                    progress["checked"], total_entries, 0, 0, 0, 0,
                ))
            except Exception:
                pass

    _ft_task = asyncio.create_task(_ft_updater())
    try:
        valid_entries, locked_labels, invalid_labels, _ = await _discord_live_check(
            token_entries, progress=progress
        )
    finally:
        done_event.set()
        _ft_task.cancel()
        try:
            await _ft_task
        except asyncio.CancelledError:
            pass

    valid_list   = [label for label, _ in valid_entries]
    locked_list  = list(locked_labels)
    invalid_list = list(invalid_labels)

    extras = []
    if discord_user:
        extras.append(_td(f"**User Filter:** {discord_user.mention}"))
    if worker_key:
        extras.append(_td(f"**Key Filter:** `{worker_key[:20]}...`"))

    result_view = _cv2(C_BRAND,
        _td("## Token Export \u2014 Live Validated"),
        _sep(),
        _td(f"Live-checked **{len(token_entries):,}** token(s) via Discord API.\nFormat: `email:password:token`"),
        _sep(),
        _td(
            f"**Valid:** {len(valid_list):,}\n"
            f"**Locked:** {len(locked_list):,}\n"
            f"**Invalid:** {len(invalid_list):,}"
        ),
        _sep(),
        *extras,
        _td("-# Live-validated via Discord API  \u00b7  SkyHighEV"),
    )

    if not valid_list and not locked_list and not invalid_list:
        await interaction.followup.send(
            view=cv2_warn("No Results", "No tokens could be validated."), ephemeral=True)
        return

    await interaction.followup.send(view=result_view, ephemeral=True)

    files = []
    if valid_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(valid_list).encode()),   filename="valid_tokens.txt"))
    if locked_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(locked_list).encode()),  filename="phone_locked.txt"))
    if invalid_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(invalid_list).encode()), filename="invalid_tokens.txt"))
    if files:
        await interaction.followup.send(files=files, ephemeral=True)


# ── /check-token ──────────────────────────────────────────────────────────────

@bot.tree.command(name="check-token", description="[Admin] Check status of one or more tokens")
@app_commands.describe(tokens_text="Paste tokens separated by commas or new lines (max 50)")
@admin_only()
async def check_token(interaction: discord.Interaction, tokens_text: str):
    await interaction.response.defer(ephemeral=True)

    raw = [t.strip() for t in tokens_text.replace("\n", ",").split(",") if t.strip()]
    if not raw:
        await interaction.followup.send(view=cv2_err("No Input", "Please paste at least one token."), ephemeral=True)
        return
    if len(raw) > 50:
        await interaction.followup.send(view=cv2_err("Too Many", "Check 50 or fewer tokens at a time."), ephemeral=True)
        return

    data = await aapi_post("/tokens/check", {"tokens": raw}, admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    results = data.get("results", [])
    valid   = [r for r in results if r["status"] == "VALID"]
    locked  = [r for r in results if r["status"] == "LOCKED"]
    invalid = [r for r in results if r["status"] not in ("VALID", "LOCKED")]

    labels = {"VALID": "VALID", "LOCKED": "LOCKED", "INVALID": "INVALID", "NOT_IN_DB": "NOT IN DB"}
    preview = []
    for r in results[:10]:
        label = labels.get(r["status"], r["status"])
        tok   = r["token"]
        short = tok[:24] + "..." if len(tok) > 24 else tok
        preview.append(f"`{short}` — {label}")

    detail_text = "\n".join(preview) if preview else ""
    footer_line = f"-# Showing first 10 of {len(results)}  ·  SkyHighEV" if len(results) > 10 else "-# SkyHighEV"
    kids = [
        _td(f"## Token Check \u2014 {len(results)} result(s)"),
        _sep(),
        _td(
            f"**Valid:** `{len(valid)}`\n"
            f"**Phone Locked:** `{len(locked)}`\n"
            f"**Invalid:** `{len(invalid)}`"
        ),
        _sep(),
    ]
    if detail_text:
        kids.append(_td(detail_text))
        kids.append(_sep())
    kids.append(_td(footer_line))
    await interaction.followup.send(view=_cv2(C_INFO, *kids), ephemeral=True)


# ── /live-check ───────────────────────────────────────────────────────────────

def _build_progress_embed(checked: int, total: int,
                           valid: int, locked: int, invalid: int, errors: int) -> discord.Embed:
    pct   = round(checked / total * 100) if total > 0 else 0
    bar_f = round(pct / 5)                      # filled blocks out of 20
    bar   = "█" * bar_f + "░" * (20 - bar_f)

    e = discord.Embed(
        title="  Live Token Check  —  In Progress",
        color=C_INFO,
        timestamp=utc_now(),
    )
    e.description = (
        f"```\n"
        f"{bar}  {pct}%\n"
        f"{checked:,} / {total:,} tokens checked\n"
        f"```"
    )
    e.add_field(name="  Valid",        value=f"**{valid:,}**",   inline=True)
    e.add_field(name="  Phone Locked", value=f"**{locked:,}**",  inline=True)
    e.add_field(name="  Invalid",      value=f"**{invalid:,}**", inline=True)
    if errors:
        e.add_field(name="  Retrying", value=f"**{errors:,}**", inline=True)
    e.set_footer(text="Updates every 4 seconds  ·  SkyHighEV  ·  Worker System")
    return e


def _build_progress_cv2(checked: int, total: int,
                         valid: int, locked: int, invalid: int, errors: int) -> "_CV2Layout":
    pct   = round(checked / total * 100) if total > 0 else 0
    bar_f = round(pct / 5)
    bar   = "█" * bar_f + "░" * (20 - bar_f)
    stat_lines = (
        f"**Valid:** {valid:,}\n"
        f"**Locked:** {locked:,}\n"
        f"**Invalid:** {invalid:,}"
        + (f"\n**Retrying:** {errors:,}" if errors else "")
    )
    return _cv2(C_INFO,
        _td("##   Live Token Check  \u2014  In Progress"),
        _sep(),
        _td(f"```\n{bar}  {pct}%\n{checked:,} / {total:,} tokens checked\n```"),
        _sep(),
        _td(stat_lines),
        _sep(),
        _td("-# Updates every 4 seconds  \u00b7  SkyHighEV"),
    )


@bot.tree.command(name="live-check", description="[Admin] Check tokens LIVE against Discord API by uploading a .txt file")
@app_commands.describe(file="A .txt file with one token per line (plain token or email:pass:token)")
@admin_only()
async def live_check(interaction: discord.Interaction, file: discord.Attachment):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.NotFound:
        return   # interaction expired before bot could respond — silently ignore
    except Exception:
        return

    # ── Validate file type ──────────────────────────────────────────────────
    if not file.filename.lower().endswith(".txt"):
        await interaction.followup.send(
            view=cv2_err("Invalid File", "Upload a `.txt` file — one token per line."), ephemeral=True)
        return

    # ── Parse file ─────────────────────────────────────────────────────────
    raw_bytes = await file.read()
    raw_text  = raw_bytes.decode("utf-8", errors="ignore")
    raw_lines = [l.strip() for l in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]

    token_entries = []
    for line in raw_lines:
        parts = line.split(":")
        if len(parts) >= 3:
            token_entries.append((line, parts[-1].strip()))   # email:pass:TOKEN
        else:
            token_entries.append((line, parts[0].strip()))    # plain token

    total = len(token_entries)
    if total == 0:
        await interaction.followup.send(
            view=cv2_err("Empty File", "No tokens found in the uploaded file."), ephemeral=True)
        return

    MAX_TOKENS = 5000
    if total > MAX_TOKENS:
        await interaction.followup.send(
            view=cv2_err("Too Many Tokens", f"Found **{total:,}** tokens. Max is **{MAX_TOKENS:,}** per run."), ephemeral=True)
        return

    # ── Send initial progress message ───────────────────────────────────────
    prog_msg = await interaction.followup.send(
        view=_build_progress_cv2(0, total, 0, 0, 0, 0),
        ephemeral=True,
        wait=True,
    )

    # ── Shared progress state ───────────────────────────────────────────────
    progress     = {"checked": 0}
    valid_list   = []
    locked_list  = []
    invalid_list = []
    error_list   = []
    done_event   = asyncio.Event()

    # ── Background progress updater ─────────────────────────────────────────
    async def _progress_updater():
        while not done_event.is_set():
            await asyncio.sleep(4)
            if done_event.is_set():
                break
            try:
                chk = progress["checked"]
                await prog_msg.edit(view=_build_progress_cv2(
                    chk, total,
                    len(valid_list), len(locked_list), len(invalid_list), len(error_list),
                ))
            except Exception:
                pass

    updater_task = asyncio.create_task(_progress_updater())

    # ── Run the live check ──────────────────────────────────────────────────
    try:
        valid_list, locked_list, invalid_list, error_list = await _discord_live_check(
            token_entries, progress=progress
        )
    finally:
        done_event.set()
        updater_task.cancel()
        try:
            await updater_task
        except asyncio.CancelledError:
            pass

    # ── Update progress bar to 100% ─────────────────────────────────────────
    try:
        await prog_msg.edit(view=_build_progress_cv2(
            total, total,
            len(valid_list), len(locked_list), len(invalid_list), len(error_list),
        ))
    except Exception:
        pass

    # ── Build results ───────────────────────────────────────────────────────
    total_checked = len(valid_list) + len(locked_list) + len(invalid_list) + len(error_list)
    pct_valid  = round(len(valid_list)   / total_checked * 100) if total_checked else 0
    pct_locked = round(len(locked_list)  / total_checked * 100) if total_checked else 0
    pct_inv    = round(len(invalid_list) / total_checked * 100) if total_checked else 0
    color      = C_SUCCESS if not error_list else C_WARN

    bar = f"`{'█' * round(pct_valid/5)}{'░'*(20-round(pct_valid/5))}`"
    err_line = ""
    if error_list:
        pct_err  = round(len(error_list) / total_checked * 100) if total_checked else 0
        err_line = f"  ·  **Timed Out:** {len(error_list):,} (`{pct_err}%`)"

    res_kids = [
        _td("##   Live Check Complete"),
        _sep(),
        _td(f"Checked **{total_checked:,}** of **{total:,}** token(s) against Discord's API."),
        _td(f"**Valid:** {len(valid_list):,} (`{pct_valid}%`)  ·  **Locked:** {len(locked_list):,} (`{pct_locked}%`)  ·  **Invalid:** {len(invalid_list):,} (`{pct_inv}%`){err_line}"),
        _td(f"{bar}  **{pct_valid}%** valid\n-# Method: GET /users/@me/guilds  ·  200=VALID · 403=LOCKED · 401=INVALID  ·  SkyHighEV"),
    ]
    res_view = _cv2(color, *res_kids)

    # ── Send CV2 summary ─────────────────────────────────────────────────────
    await interaction.followup.send(view=res_view, ephemeral=True)

    # ── Attach result files (separate message — CV2 doesn't support attachments) ─
    files = []
    if valid_list:
        content = "\n".join(line for line, _ in valid_list)
        files.append(discord.File(fp=io.BytesIO(content.encode()),              filename="valid_tokens.txt"))
    if locked_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(locked_list).encode()), filename="phone_locked.txt"))
    if invalid_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(invalid_list).encode()), filename="invalid_tokens.txt"))
    if error_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(error_list).encode()),  filename="timeout_tokens.txt"))
    if files:
        await interaction.followup.send(files=files, ephemeral=True)


# ── /live-check-all ────────────────────────────────────────────────────────────

@bot.tree.command(
    name="live-check-all",
    description="[Admin] Live-check ALL tokens in the DB via Discord API — no file upload needed",
)
@app_commands.describe(
    status_filter="Which tokens to check: ALL (default), VALID only, LOCKED only, INVALID only",
    worker_key="Optional: filter by a specific worker key",
)
@app_commands.choices(status_filter=[
    app_commands.Choice(name="ALL (every token in DB)",   value="ALL"),
    app_commands.Choice(name="VALID only",                value="VALID"),
    app_commands.Choice(name="LOCKED only",               value="LOCKED"),
    app_commands.Choice(name="INVALID only",              value="INVALID"),
])
@admin_only()
async def live_check_all(
    interaction: discord.Interaction,
    status_filter: str = "ALL",
    worker_key: str = None,
):
    await interaction.response.defer(ephemeral=True)

    # Fetch tokens from DB
    params = {}
    if status_filter != "ALL":
        params["status"] = status_filter
    if worker_key:
        params["workerKey"] = worker_key

    token_data = await aapi_get("/tokens/fetch", params=params, admin=True)
    if "error" in token_data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{token_data['error']}```"), ephemeral=True)
        return

    all_tokens = token_data.get("tokens", [])
    if not all_tokens:
        await interaction.followup.send(
            view=cv2_warn("No Tokens", "No tokens found matching the filter."), ephemeral=True,
        )
        return

    token_entries = []
    for t in all_tokens:
        tok = t.get("token") or ""
        if not tok:
            continue
        label = f"{t.get('email') or ''}:{t.get('accountPass') or ''}:{tok}"
        token_entries.append((label, tok))

    total = len(token_entries)

    # Send a live progress message
    prog_msg = await interaction.followup.send(
        view=_build_progress_cv2(0, total, 0, 0, 0, 0),
        ephemeral=True,
        wait=True,
    )

    progress   = {"checked": 0}
    valid_list = []; locked_list = []; invalid_list = []; error_list = []
    done_event = asyncio.Event()

    async def _progress_updater():
        while not done_event.is_set():
            await asyncio.sleep(4)
            if done_event.is_set():
                break
            try:
                await prog_msg.edit(view=_build_progress_cv2(
                    progress["checked"], total,
                    len(valid_list), len(locked_list), len(invalid_list), len(error_list),
                ))
            except Exception:
                pass

    updater_task = asyncio.create_task(_progress_updater())

    try:
        valid_list, locked_list, invalid_list, error_list = await _discord_live_check(
            token_entries, progress=progress
        )
    finally:
        done_event.set()
        updater_task.cancel()
        try:
            await updater_task
        except asyncio.CancelledError:
            pass

    # Final progress bar at 100%
    try:
        await prog_msg.edit(view=_build_progress_cv2(
            total, total,
            len(valid_list), len(locked_list), len(invalid_list), len(error_list),
        ))
    except Exception:
        pass

    total_checked = len(valid_list) + len(locked_list) + len(invalid_list) + len(error_list)
    pct_valid  = round(len(valid_list)   / total_checked * 100) if total_checked else 0
    pct_locked = round(len(locked_list)  / total_checked * 100) if total_checked else 0
    pct_inv    = round(len(invalid_list) / total_checked * 100) if total_checked else 0
    color_r    = C_SUCCESS if not error_list else C_WARN

    filter_note = f"Filter: **{status_filter}**" + (f"  ·  Key: `{worker_key[:20]}...`" if worker_key else "")
    bar_r = f"`{'█' * round(pct_valid/5)}{'░'*(20-round(pct_valid/5))}`"
    err_line_r = ""
    if error_list:
        pct_err    = round(len(error_list) / total_checked * 100) if total_checked else 0
        err_line_r = f"  ·  **Timed Out:** {len(error_list):,} (`{pct_err}%`)"

    err_stats = f"\n**Timed Out:** {len(error_list):,} (`{pct_err}%`)" if error_list else ""
    res_view = _cv2(color_r,
        _td("##   Live Check All \u2014 Complete"),
        _sep(),
        _td(f"Checked **{total_checked:,}** of **{total:,}** DB token(s) against Discord's API.\n{filter_note}"),
        _sep(),
        _td(
            f"**Valid:** {len(valid_list):,} (`{pct_valid}%`)\n"
            f"**Locked:** {len(locked_list):,} (`{pct_locked}%`)\n"
            f"**Invalid:** {len(invalid_list):,} (`{pct_inv}%`)"
            + err_stats
        ),
        _sep(),
        _td(f"{bar_r}  **{pct_valid}%** valid\n-# Method: GET /users/@me/guilds  \u00b7  200=VALID \u00b7 403=LOCKED \u00b7 401=INVALID  \u00b7  SkyHighEV"),
    )

    await interaction.followup.send(view=res_view, ephemeral=True)

    files = []
    if valid_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(lbl for lbl, _ in valid_list).encode()), filename="valid_tokens.txt"))
    if locked_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(locked_list).encode()),  filename="phone_locked.txt"))
    if invalid_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(invalid_list).encode()), filename="invalid_tokens.txt"))
    if error_list:
        files.append(discord.File(fp=io.BytesIO("\n".join(error_list).encode()),   filename="timeout_tokens.txt"))
    if files:
        await interaction.followup.send(files=files, ephemeral=True)


# ── /nitro-check ──────────────────────────────────────────────────────────────
#
# Categorises tokens by Discord Nitro / trial / boost status using:
#   GET /users/@me/billing/user-offer            → trial-offer detection
#   GET /users/@me                               → premium_type (current Nitro)
#   GET /users/@me/guilds/premium/subscription-slots  → boost slots
#
# Categories (mutually exclusive; first match wins, in priority order):
#   INVALID            → token returns 401
#   NITRO_BOOST        → currently has Nitro AND uses ≥1 boost slot
#   NITRO_ONLY         → currently has Nitro, no boosts in use
#   1M_TRIAL           → trial offer available, ~1 month duration
#   2W_TRIAL           → trial offer available, ~2 week duration
#   NO_TRIAL           → token alive, no nitro, no trial offer
#   ERROR              → network/timeout (do NOT change status)

_NITRO_OFFER_URL    = "https://discord.com/api/v9/users/@me/billing/user-offer"
_NITRO_ME_URL       = "https://discord.com/api/v9/users/@me"
_NITRO_BOOSTS_URL   = "https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots"
_NITRO_DISCOUNT_URL = "https://discord.com/api/v9/users/@me/billing/subscriptions/preview"

# Trial IDs from the laptop trial-checker (verified working POST endpoint)
_TRIAL_ID_2W = "983601860436819969"
_TRIAL_ID_1M = "520373071933079552"

# Discount detection (40% off Nitro promo)
_DISCOUNT_ID         = "1215366184820539392"
_DISCOUNT_PLAN_ID    = "511651880837840896"

_TRIAL_HDRS_TEMPLATE = {
    'accept':            '*/*',
    'accept-language':   'en-GB,en-US;q=0.9,en;q=0.8',
    'authorization':     '',
    'content-type':      'application/json',
    'origin':            'https://discord.com',
    'priority':          'u=1, i',
    'referer':           'https://discord.com/channels/@me',
    'sec-ch-ua':         '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile':  '?0',
    'sec-ch-ua-platform':'"Windows"',
    'sec-fetch-dest':    'empty',
    'sec-fetch-mode':    'cors',
    'sec-fetch-site':    'same-origin',
    'user-agent':        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'x-debug-options':   'bugReporterEnabled',
    'x-discord-locale':  'en-US',
    'x-discord-timezone':'Asia/Calcutta',
    'x-super-properties':'eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLUdCIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEzOC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTM4LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjQxNzI2NiwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbCwiY2xpZW50X2xhdW5jaF9pZCI6Ijg4ZDM3ZTA5LWNhNTEtNDNlYi05NDRmLTcwMmI5OGNmNDNiOSIsImNsaWVudF9hcHBfc3RhdGUiOiJ1bmZvY3VzZWQifQ==',
}


def _make_trial_session():
    """Create a tls_client session that mimics Chrome for Discord billing endpoints."""
    try:
        import tls_client
        return tls_client.Session(
            client_identifier="chrome124",
            random_tls_extension_order=True,
        )
    except Exception:
        return None


def _check_nitro_sync(token: str) -> str:
    """
    Single-token Nitro/trial/discount classification using the FIXED POST flow
    (matches the laptop trial-checker). Returns category string.

    Categories: INVALID, DISCOUNT, NITRO_BOOST, NITRO_ONLY,
                1M_TRIAL, 2W_TRIAL, NO_TRIAL, ERROR
    """
    session = _make_trial_session()
    if session is None:
        return "ERROR"

    headers = _TRIAL_HDRS_TEMPLATE.copy()
    headers['authorization'] = token

    discount_found = False
    # ── 1) Discount-token detection (POST /billing/subscriptions/preview) ──
    try:
        d_payload = {
            "items":             [{"quantity": 1, "plan_id": _DISCOUNT_PLAN_ID}],
            "payment_source_id": None,
            "apply_entitlements": False,
            "currency":          "usd",
            "renewal":           True,
        }
        rd = session.post(_NITRO_DISCOUNT_URL, headers=headers, json=d_payload)
        if rd.status_code == 200:
            try:
                d_data = rd.json()
                for item in d_data.get('invoice_items', []) or []:
                    for disc in item.get('discounts', []) or []:
                        if (disc.get('type') == 1 and
                            disc.get('percentage_amount') == 40 and
                            disc.get('discount_id') == _DISCOUNT_ID):
                            discount_found = True
                            break
                    if discount_found:
                        break
            except Exception:
                pass
    except Exception:
        pass

    # ── 2) Trial check (POST /billing/user-offer with empty body) ──
    trial_label: str | None = None
    invalid     = False
    try:
        ro = session.post(_NITRO_OFFER_URL, headers=headers, json={})
        sc = ro.status_code
        if sc == 401:
            invalid = True
        elif sc == 429:
            try:
                _time.sleep(min(float(ro.json().get("retry_after", 5.0)) + 1.5, 30))
            except Exception:
                _time.sleep(6.0)
            ro = session.post(_NITRO_OFFER_URL, headers=headers, json={})
            sc = ro.status_code
            if sc == 401:
                invalid = True

        if invalid:
            try: session.close()
            except Exception: pass
            return "INVALID"

        if sc == 200:
            try:
                data = ro.json() if ro.text else {}
            except Exception:
                data = {}
            offer = data.get('user_trial_offer') if isinstance(data, dict) else None
            if isinstance(offer, dict) and offer.get('trial_id'):
                tid = str(offer.get('trial_id'))
                if tid == _TRIAL_ID_2W:
                    trial_label = "2W_TRIAL"
                elif tid == _TRIAL_ID_1M:
                    trial_label = "1M_TRIAL"
                else:
                    # Unknown trial_id — treat as 1-month (most common)
                    trial_label = "1M_TRIAL"
            # 200 with no offer → NO_TRIAL (handled below)
        elif sc in (404, 405):
            # NOT a network error — Discord just says "no offer"
            trial_label = None
        else:
            # Genuine HTTP failure (5xx, etc.) — fall through to NO_TRIAL
            # rather than dumping into ERROR (per user fix).
            trial_label = None
    except Exception:
        # Network exception — single retry
        try:
            ro = session.post(_NITRO_OFFER_URL, headers=headers, json={})
            if ro.status_code == 401:
                try: session.close()
                except Exception: pass
                return "INVALID"
            if ro.status_code == 200:
                try:
                    data = ro.json() if ro.text else {}
                    offer = data.get('user_trial_offer') if isinstance(data, dict) else None
                    if isinstance(offer, dict) and offer.get('trial_id'):
                        tid = str(offer.get('trial_id'))
                        trial_label = "2W_TRIAL" if tid == _TRIAL_ID_2W else (
                                      "1M_TRIAL" if tid == _TRIAL_ID_1M else "1M_TRIAL")
                except Exception:
                    pass
        except Exception:
            try: session.close()
            except Exception: pass
            # Discount still wins if found
            return "DISCOUNT" if discount_found else "ERROR"

    # ── 3) /users/@me → premium_type (Nitro detection) ──
    premium_type = 0
    me_failed = False
    try:
        rm = session.get(_NITRO_ME_URL, headers=headers)
        if rm.status_code == 200:
            try:
                premium_type = int((rm.json() or {}).get("premium_type", 0) or 0)
            except Exception:
                premium_type = 0
        elif rm.status_code == 401:
            try: session.close()
            except Exception: pass
            return "INVALID"
        else:
            me_failed = True
    except Exception:
        me_failed = True

    has_nitro = premium_type in (1, 2, 3)

    if has_nitro:
        has_boosts = False
        try:
            rb = session.get(_NITRO_BOOSTS_URL, headers=headers)
            if rb.status_code == 200:
                slots = rb.json()
                if isinstance(slots, list):
                    has_boosts = any(
                        bool(s.get("premium_guild_subscription"))
                        for s in slots if isinstance(s, dict)
                    )
        except Exception:
            pass
        try: session.close()
        except Exception: pass
        return "NITRO_BOOST" if has_boosts else "NITRO_ONLY"

    try: session.close()
    except Exception: pass

    # Priority: trial > discount > no_trial
    if trial_label:
        return trial_label
    if discount_found:
        return "DISCOUNT"
    return "NO_TRIAL"


async def _discord_nitro_check(token_entries: list, progress: dict | None = None):
    """
    Async wrapper for nitro classification.
    Returns dict of category → list[label].
    """
    buckets = {
        "1M_TRIAL":    [],
        "2W_TRIAL":    [],
        "NO_TRIAL":    [],
        "DISCOUNT":    [],
        "NITRO_ONLY":  [],
        "NITRO_BOOST": [],
        "INVALID":     [],
        "ERROR":       [],
    }
    _lock     = asyncio.Lock()
    semaphore = asyncio.Semaphore(3)

    async def _check_one(label, token):
        async with semaphore:
            await asyncio.sleep(0.5)
            cat = await asyncio.to_thread(_check_nitro_sync, token)
        async with _lock:
            buckets.get(cat, buckets["ERROR"]).append(label)
            if progress is not None:
                progress["checked"] += 1

    await asyncio.gather(*(_check_one(lbl, tok) for lbl, tok in token_entries))
    return buckets


def _build_nitro_progress_cv2(checked: int, total: int, b: dict) -> "_CV2Layout":
    pct   = round(checked / total * 100) if total > 0 else 0
    bar_f = round(pct / 5)
    bar   = "\u2588" * bar_f + "\u2591" * (20 - bar_f)
    stat_lines = (
        f"** 1-Month Trial:** {len(b['1M_TRIAL']):,}\n"
        f"** 2-Week Trial:**  {len(b['2W_TRIAL']):,}\n"
        f"** No Trial:**      {len(b['NO_TRIAL']):,}\n"
        f"** Discount 40%:**  {len(b.get('DISCOUNT', [])):,}\n"
        f"** Nitro Only:**    {len(b['NITRO_ONLY']):,}\n"
        f"** Nitro+Boost:**   {len(b['NITRO_BOOST']):,}\n"
        f"** Invalid:**       {len(b['INVALID']):,}"
        + (f"\n** Retrying:** {len(b['ERROR']):,}" if b['ERROR'] else "")
    )
    return _cv2(C_INFO,
        _td("##   Nitro / Trial Check  \u2014  In Progress"),
        _sep(),
        _td(f"```\n{bar}  {pct}%\n{checked:,} / {total:,} tokens checked\n```"),
        _sep(),
        _td(stat_lines),
        _sep(),
        _td("-# user-offer + premium_type + boost-slots  ·  Updates every 4s  ·  SkyHighEV"),
    )


@bot.tree.command(name="nitro-check", description="[Admin] Check tokens for Nitro trial offers, active Nitro, and boosts")
@app_commands.describe(file="A .txt file with one token per line (plain token or email:pass:token)")
@admin_only()
async def nitro_check(interaction: discord.Interaction, file: discord.Attachment):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.NotFound:
        return
    except Exception:
        return

    if not file.filename.lower().endswith(".txt"):
        await interaction.followup.send(
            view=cv2_err("Invalid File", "Upload a `.txt` file — one token per line."), ephemeral=True)
        return

    raw_bytes = await file.read()
    raw_text  = raw_bytes.decode("utf-8", errors="ignore")
    raw_lines = [l.strip() for l in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]

    token_entries = []
    for line in raw_lines:
        parts = line.split(":")
        if len(parts) >= 3:
            token_entries.append((line, parts[-1].strip()))   # email:pass:TOKEN
        else:
            token_entries.append((line, parts[0].strip()))    # plain token

    total = len(token_entries)
    if total == 0:
        await interaction.followup.send(
            view=cv2_err("Empty File", "No tokens found in the uploaded file."), ephemeral=True)
        return

    MAX_TOKENS = 2000
    if total > MAX_TOKENS:
        await interaction.followup.send(
            view=cv2_err("Too Many Tokens",
                         f"Found **{total:,}** tokens. Max is **{MAX_TOKENS:,}** per run "
                         f"(nitro check makes 3 API calls per token)."),
            ephemeral=True)
        return

    # Initial progress message
    init_buckets = {k: [] for k in
                    ("1M_TRIAL", "2W_TRIAL", "NO_TRIAL", "DISCOUNT", "NITRO_ONLY", "NITRO_BOOST", "INVALID", "ERROR")}
    prog_msg = await interaction.followup.send(
        view=_build_nitro_progress_cv2(0, total, init_buckets),
        ephemeral=True,
        wait=True,
    )

    progress   = {"checked": 0}
    buckets    = init_buckets
    done_event = asyncio.Event()

    async def _progress_updater():
        while not done_event.is_set():
            await asyncio.sleep(4)
            if done_event.is_set():
                break
            try:
                await prog_msg.edit(view=_build_nitro_progress_cv2(
                    progress["checked"], total, buckets,
                ))
            except Exception:
                pass

    updater_task = asyncio.create_task(_progress_updater())
    try:
        buckets = await _discord_nitro_check(token_entries, progress=progress)
    finally:
        done_event.set()
        updater_task.cancel()
        try:
            await updater_task
        except asyncio.CancelledError:
            pass

    try:
        await prog_msg.edit(view=_build_nitro_progress_cv2(total, total, buckets))
    except Exception:
        pass

    # ── Build summary ───────────────────────────────────────────────────────
    n_1m   = len(buckets["1M_TRIAL"])
    n_2w   = len(buckets["2W_TRIAL"])
    n_no   = len(buckets["NO_TRIAL"])
    n_disc = len(buckets.get("DISCOUNT", []))
    n_nit  = len(buckets["NITRO_ONLY"])
    n_boost= len(buckets["NITRO_BOOST"])
    n_inv  = len(buckets["INVALID"])
    n_err  = len(buckets["ERROR"])
    n_done = n_1m + n_2w + n_no + n_disc + n_nit + n_boost + n_inv + n_err

    n_trials = n_1m + n_2w
    pct_trials = round(n_trials / n_done * 100) if n_done else 0
    bar_f = round(pct_trials / 5)
    bar   = "\u2588" * bar_f + "\u2591" * (20 - bar_f)

    err_line = f"  ·  **Timed Out:** {n_err:,}" if n_err else ""
    color    = C_SUCCESS if n_trials > 0 else (C_WARN if n_inv else C_INFO)

    res_view = _cv2(color,
        _td("##   Nitro / Trial Check Complete"),
        _sep(),
        _td(f"Checked **{n_done:,}** of **{total:,}** token(s) against Discord billing API."),
        _sep(),
        _td(
            f"** 1-Month Trial:** `{n_1m:,}`  ·  ** 2-Week Trial:** `{n_2w:,}`  ·  ** No Trial:** `{n_no:,}`\n"
            f"** Discount 40%:** `{n_disc:,}`  ·  ** Nitro Only:** `{n_nit:,}`  ·  ** Nitro + Boost:** `{n_boost:,}`  ·  ** Invalid:** `{n_inv:,}`{err_line}"
        ),
        _sep(),
        _td(f"{bar}  **{pct_trials}%** of checked tokens have a trial offer\n"
            f"-# Endpoints: /billing/user-offer + /users/@me + /guilds/premium/subscription-slots  ·  SkyHighEV"),
    )

    await interaction.followup.send(view=res_view, ephemeral=True)

    # ── Result files ────────────────────────────────────────────────────────
    files = []
    def _mkfile(lst, name):
        if lst:
            files.append(discord.File(
                fp=io.BytesIO("\n".join(lst).encode()),
                filename=name,
            ))

    _mkfile(buckets["1M_TRIAL"],         "1m_trials.txt")
    _mkfile(buckets["2W_TRIAL"],         "2w_trials.txt")
    _mkfile(buckets["NO_TRIAL"],         "no_trials.txt")
    _mkfile(buckets.get("DISCOUNT", []), "discount_tokens.txt")
    _mkfile(buckets["NITRO_ONLY"],       "nitro_actived_only.txt")
    _mkfile(buckets["NITRO_BOOST"],      "nitro-and-sv-boosted.txt")
    _mkfile(buckets["INVALID"],          "invalid.txt")
    _mkfile(buckets["ERROR"],            "timeout_tokens.txt")

    if files:
        await interaction.followup.send(files=files, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
# /quest-* — Discord Quest AIO (avoid trial trigger)
# Ports the laptop "Discord Quest AIO Tool" to the bot:
#   /quest-enroll    — enroll tokens into one or more quests
#   /quest-complete  — fake-progress quests to completion
#   /quest-claim     — claim quest rewards (needs OnyxSolver captcha key)
#   /quest-badge     — buy the quest badge with VC for each token
# ══════════════════════════════════════════════════════════════════════════════

import re as _re

QUEST_CAPTCHA_API_KEY = ""   # Set via /quest-claim's `captcha_key` arg, or hard-code here

def _parse_token_file(raw_text: str) -> list[str]:
    """Return non-empty, non-comment lines."""
    out = []
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _parse_proxies_file(raw_text: str) -> list[str]:
    return _parse_token_file(raw_text)


def _split_quest_ids(raw: str) -> list[str]:
    if not raw:
        return []
    parts = _re.split(r"[,\s]+", raw.strip())
    return [p for p in parts if p]


class _QuestRunResult:
    __slots__ = ("success", "failed", "logs")
    def __init__(self):
        self.success: list[str] = []
        self.failed:  list[str] = []
        self.logs:    list[str] = []


async def _run_quest_module(
    interaction: discord.Interaction,
    title: str,
    tokens: list[str],
    proxies: list[str],
    use_proxies: bool,
    module_runner,                   # callable(log_func, on_success, on_fail) -> None  (sync, blocking)
    threads: int,
):
    """Stream progress to Discord and post success/failed token files at the end."""
    result   = _QuestRunResult()
    lock     = threading.Lock()
    progress = {"done": 0, "total": len(tokens)}

    def _log(level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {message}"
        with lock:
            result.logs.append(line)
            # Cap to last 400 lines so memory stays bounded on huge runs
            if len(result.logs) > 400:
                del result.logs[: len(result.logs) - 400]

    def _on_success(token_data: str):
        with lock:
            result.success.append(token_data)
            progress["done"] += 1

    def _on_fail(token_data: str):
        with lock:
            result.failed.append(token_data)
            progress["done"] += 1

    def _build_progress_view(done_label: str | None = None):
        d = progress["done"]
        t = max(progress["total"], 1)
        pct = round(d / t * 100)
        bar_f = round(pct / 5)
        bar = "\u2588" * bar_f + "\u2591" * (20 - bar_f)
        last_lines = "\n".join(result.logs[-12:]) or "(starting…)"
        head = f"## {title}" if not done_label else f"## {title} — {done_label}"
        return _cv2(
            C_INFO if not done_label else C_SUCCESS,
            _td(head),
            _sep(),
            _td(f"```\n{bar}  {pct}%\n{d:,} / {t:,} processed\n```"),
            _sep(),
            _td(f"** Success:** `{len(result.success):,}`  ·  ** Failed:** `{len(result.failed):,}`  ·  ** Threads:** `{threads}`  ·  ** Proxies:** `{'yes' if use_proxies else 'no'}`"),
            _sep(),
            _td(f"```\n{last_lines[-1700:]}\n```"),
            _sep(),
            _td("-# SkyHighEV  ·  Discord Quest AIO"),
        )

    # Initial message
    prog_msg = await interaction.followup.send(view=_build_progress_view(), ephemeral=True, wait=True)

    done_event = asyncio.Event()

    async def _updater():
        while not done_event.is_set():
            await asyncio.sleep(4)
            if done_event.is_set():
                break
            try:
                await prog_msg.edit(view=_build_progress_view())
            except Exception:
                pass

    updater_task = asyncio.create_task(_updater())
    try:
        await asyncio.to_thread(module_runner, _log, _on_success, _on_fail)
    except Exception as e:
        _log("FAIL", f"Fatal: {type(e).__name__}: {e}")
    finally:
        done_event.set()
        updater_task.cancel()
        try:
            await updater_task
        except asyncio.CancelledError:
            pass

    # Final view + files
    try:
        await prog_msg.edit(view=_build_progress_view(done_label="Complete"))
    except Exception:
        pass

    files = []
    if result.success:
        files.append(discord.File(
            fp=io.BytesIO("\n".join(result.success).encode()),
            filename=f"{title.lower().replace(' ', '_')}_success.txt",
        ))
    if result.failed:
        files.append(discord.File(
            fp=io.BytesIO("\n".join(result.failed).encode()),
            filename=f"{title.lower().replace(' ', '_')}_failed.txt",
        ))
    if result.logs:
        files.append(discord.File(
            fp=io.BytesIO("\n".join(result.logs).encode()),
            filename=f"{title.lower().replace(' ', '_')}_log.txt",
        ))
    if files:
        await interaction.followup.send(files=files, ephemeral=True)


async def _quest_load_inputs(
    interaction: discord.Interaction,
    tokens_file: discord.Attachment,
    proxies_file: discord.Attachment | None,
):
    """Read token+proxy attachments. Returns (tokens, proxies) or (None, None) and sends an error."""
    if not tokens_file.filename.lower().endswith(".txt"):
        await interaction.followup.send(view=cv2_err("Invalid File", "`tokens` must be a `.txt` file."), ephemeral=True)
        return None, None
    raw_tok = (await tokens_file.read()).decode("utf-8", errors="ignore")
    tokens = _parse_token_file(raw_tok)
    if not tokens:
        await interaction.followup.send(view=cv2_err("Empty File", "No tokens in file."), ephemeral=True)
        return None, None

    proxies: list[str] = []
    if proxies_file:
        if not proxies_file.filename.lower().endswith(".txt"):
            await interaction.followup.send(view=cv2_err("Invalid File", "`proxies` must be a `.txt` file."), ephemeral=True)
            return None, None
        raw_prx = (await proxies_file.read()).decode("utf-8", errors="ignore")
        proxies = _parse_proxies_file(raw_prx)
    return tokens, proxies


import threading  # already used in modules; ensure top-level import is present

# ── /quest-enroll ──────────────────────────────────────────────────────────────

@bot.tree.command(name="quest-enroll", description="[Admin] Enroll tokens in one or more Discord quests")
@app_commands.describe(
    tokens="A .txt file with one token per line (plain or email:pass:token)",
    quest_ids="Quest ID(s), comma-separated",
    threads="Concurrent threads (1-100). Default: 5",
    proxies="Optional .txt file with proxies (user:pass@host:port or host:port)",
)
@admin_only()
async def quest_enroll(
    interaction: discord.Interaction,
    tokens: discord.Attachment,
    quest_ids: str,
    threads: app_commands.Range[int, 1, 100] = 5,
    proxies: discord.Attachment | None = None,
):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        return

    qids = _split_quest_ids(quest_ids)
    if not qids:
        await interaction.followup.send(view=cv2_err("Missing Quest IDs", "Provide at least one quest ID."), ephemeral=True)
        return

    toks, prxs = await _quest_load_inputs(interaction, tokens, proxies)
    if toks is None:
        return

    use_proxies = bool(prxs)

    from modules.enroller import QuestEnroller
    enroller = QuestEnroller(proxies=prxs, use_proxies=use_proxies)

    def runner(log, on_success, on_fail):
        enroller.run(toks, qids, int(threads), log_func=log, on_success=on_success, on_fail=on_fail)

    await _run_quest_module(interaction, "Quest Enroll", toks, prxs, use_proxies, runner, int(threads))


# ── /quest-complete ────────────────────────────────────────────────────────────

@bot.tree.command(name="quest-complete", description="[Admin] Auto-progress quests to completion (video/activity)")
@app_commands.describe(
    tokens="A .txt file with one token per line",
    quest_ids="Quest ID(s), comma-separated",
    quest_type="video or activity (default: video)",
    target_seconds="How many seconds the quest needs (default: 900)",
    speed_multiplier="Speed multiplier 1-50 (default: 10 — laptop default)",
    threads="Concurrent threads 1-100 (default: 5)",
    proxies="Optional .txt file with proxies",
)
@app_commands.choices(quest_type=[
    app_commands.Choice(name="video",    value="video"),
    app_commands.Choice(name="activity", value="activity"),
])
@admin_only()
async def quest_complete(
    interaction: discord.Interaction,
    tokens: discord.Attachment,
    quest_ids: str,
    quest_type: app_commands.Choice[str] | None = None,
    target_seconds: app_commands.Range[int, 60, 7200] = 900,
    speed_multiplier: app_commands.Range[int, 1, 50] = 10,
    threads: app_commands.Range[int, 1, 100] = 5,
    proxies: discord.Attachment | None = None,
):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        return

    qids = _split_quest_ids(quest_ids)
    if not qids:
        await interaction.followup.send(view=cv2_err("Missing Quest IDs", "Provide at least one quest ID."), ephemeral=True)
        return

    toks, prxs = await _quest_load_inputs(interaction, tokens, proxies)
    if toks is None:
        return

    qtype = (quest_type.value if quest_type else "video")
    use_proxies = bool(prxs)

    from modules.completer import QuestCompleter
    completer = QuestCompleter(
        proxies=prxs,
        use_proxies=use_proxies,
        speed_multiplier=int(speed_multiplier),
        target_seconds=int(target_seconds),
        quest_type=qtype,
    )

    def runner(log, on_success, on_fail):
        completer.run(toks, qids, int(threads), log_func=log, on_success=on_success, on_fail=on_fail)

    await _run_quest_module(interaction, "Quest Complete", toks, prxs, use_proxies, runner, int(threads))


# ── /quest-claim ───────────────────────────────────────────────────────────────

@bot.tree.command(name="quest-claim", description="[Admin] Claim quest rewards (no captcha solver needed in most cases)")
@app_commands.describe(
    tokens="A .txt file with one token per line",
    quest_ids="Quest ID(s), comma-separated",
    captcha_key="(Optional) OnyxSolver clientKey — only used if Discord ever asks for captcha",
    threads="Concurrent threads 1-100 (default: 5)",
    proxies="Optional .txt file with proxies",
)
@admin_only()
async def quest_claim(
    interaction: discord.Interaction,
    tokens: discord.Attachment,
    quest_ids: str,
    captcha_key: str | None = None,
    threads: app_commands.Range[int, 1, 100] = 5,
    proxies: discord.Attachment | None = None,
):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        return

    qids = _split_quest_ids(quest_ids)
    if not qids:
        await interaction.followup.send(view=cv2_err("Missing Quest IDs", "Provide at least one quest ID."), ephemeral=True)
        return

    # Captcha is optional — claims that ever require one will be skipped, but most don't.
    key = (captcha_key or QUEST_CAPTCHA_API_KEY or os.environ.get("ONYX_API_KEY", "")).strip()

    toks, prxs = await _quest_load_inputs(interaction, tokens, proxies)
    if toks is None:
        return

    use_proxies = bool(prxs)

    try:
        from modules.claimer import QuestClaimer
    except ModuleNotFoundError as e:
        await interaction.followup.send(
            view=cv2_err("Missing Dependency", f"`{e.name}` is not installed. Run `pip install curl_cffi`."),
            ephemeral=True)
        return

    claimer = QuestClaimer(proxies=prxs, use_proxies=use_proxies, captcha_api_key=key)

    def runner(log, on_success, on_fail):
        claimer.run(toks, qids, int(threads), log_func=log, on_success=on_success, on_fail=on_fail)

    await _run_quest_module(interaction, "Quest Claim", toks, prxs, use_proxies, runner, int(threads))


# ── /quest-badge ───────────────────────────────────────────────────────────────

@bot.tree.command(name="quest-badge", description="[Admin] Buy the quest badge (VC redeem) for each token")
@app_commands.describe(
    tokens="A .txt file with one token per line",
    threads="Concurrent threads 1-100 (default: 5)",
    proxies="Optional .txt file with proxies",
)
@admin_only()
async def quest_badge(
    interaction: discord.Interaction,
    tokens: discord.Attachment,
    threads: app_commands.Range[int, 1, 100] = 5,
    proxies: discord.Attachment | None = None,
):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        return

    toks, prxs = await _quest_load_inputs(interaction, tokens, proxies)
    if toks is None:
        return

    use_proxies = bool(prxs)

    from modules.badge_buyer import BadgeBuyer
    buyer = BadgeBuyer(proxies=prxs, use_proxies=use_proxies)

    def runner(log, on_success, on_fail):
        buyer.run(toks, int(threads), log_func=log, on_success=on_success, on_fail=on_fail)

    await _run_quest_module(interaction, "Quest Badge", toks, prxs, use_proxies, runner, int(threads))


# ── /trial-trigger ────────────────────────────────────────────────────────────
# New Nitro-trial unlock flow (April 2026):
#   per token:  enroll live video quest → watch video → set HypeSquad
#   (no orb/badge claim — not needed under the new method)

@bot.tree.command(name="trial-trigger", description="[Admin] One-shot trial unlock: try quest IDs per token → watch → HypeSquad")
@app_commands.describe(
    tokens="A .txt file with one token per line (or email:pass:token format)",
    quest_ids="Quest ID(s) visible in your Discord Quest Home, comma-separated (e.g. 123,456,789). Each token tries all until one enrolls.",
    threads="Concurrent threads 1-100 (default: 5)",
    target_seconds="Override watch-time in seconds (default: 900)",
    proxies="Optional .txt file with proxies",
)
@admin_only()
async def trial_trigger_cmd(
    interaction: discord.Interaction,
    tokens: discord.Attachment,
    quest_ids: str,
    threads: app_commands.Range[int, 1, 100] = 5,
    target_seconds: app_commands.Range[int, 60, 7200] | None = None,
    proxies: discord.Attachment | None = None,
):
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        return

    qids = [q.strip() for q in quest_ids.replace(" ", "").split(",") if q.strip()]
    if not qids:
        await interaction.followup.send(
            view=cv2_err("Missing Quest IDs",
                "Open Discord Quest Home, copy the quest ID(s) you see, and paste them here comma-separated."),
            ephemeral=True,
        )
        return

    toks, prxs = await _quest_load_inputs(interaction, tokens, proxies)
    if toks is None:
        return

    use_proxies = bool(prxs)

    from modules.trial_trigger import TrialTrigger
    trigger = TrialTrigger(
        proxies=prxs,
        use_proxies=use_proxies,
        target_seconds_override=int(target_seconds) if target_seconds else None,
        quest_ids=qids,
    )

    def runner(log, on_success, on_fail):
        trigger.run(toks, int(threads), log_func=log, on_success=on_success, on_fail=on_fail)

    await _run_quest_module(interaction, "Trial Trigger", toks, prxs, use_proxies, runner, int(threads))


# ── /list-workers ─────────────────────────────────────────────────────────────

@bot.tree.command(name="list-workers", description="[Admin] List all registered workers and their status")
@admin_only()
async def list_workers(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/workers/list", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    workers = data.get("workers", [])
    if not workers:
        await interaction.followup.send(view=cv2_info("No Workers", "No workers have been registered yet."), ephemeral=True)
        return

    status_label = {"VALID": "[ON]", "LOCKED": "[OFF]", "EXPIRED": "[EXP]"}
    lines = []
    for i, w in enumerate(workers[:25], 1):
        label   = status_label.get(w.get("status", ""), "[?]")
        name    = w.get("discordUsername", "unknown")
        gen     = w.get("tokensGenerated", 0)
        rate    = w.get("unlockRate", 0)
        exp_str = fmt_exp_short(w.get("expiresAt"))
        lines.append(f"`{i:02}.` {label} **{name}** — {gen:,} gen  {rate}%  exp {exp_str}")

    footer = f"-# Showing 25 of {len(workers)} workers  \u00b7  SkyHighEV" if len(workers) > 25 else f"-# {len(workers)} worker(s)  \u00b7  SkyHighEV"
    await interaction.followup.send(view=_cv2(C_BRAND,
        _td(f"## Worker Registry  \u2014  {len(workers)} Workers"),
        _sep(),
        _td("\n".join(lines)),
        _sep(),
        _td(footer),
    ), ephemeral=True)


# ── /worker-info ──────────────────────────────────────────────────────────────

@bot.tree.command(name="worker-info", description="[Admin] Detailed stats and live token status for a specific worker")
@app_commands.describe(user="The Discord user to look up")
@admin_only()
async def worker_info(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get(f"/workers/profile/{user.id}", admin=True)
    if "error" in data or not data.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Found", f"{user.mention} has no worker profile."), ephemeral=True)
        return

    worker  = data["worker"]
    daily   = data.get("dailyStats", {})
    alltime = data.get("allTimeStats", {})

    # Fetch tokens from DB to get token strings for live validation
    token_data = await aapi_get("/tokens/fetch", params={"discordId": str(user.id)}, admin=True)
    all_tokens = token_data.get("tokens", []) if "error" not in token_data else []

    status_label = {"VALID": "VALID", "LOCKED": "LOCKED", "EXPIRED": "EXPIRED"}
    exp_str  = fmt_exp(worker.get("expiresAt"))
    join_str = fmt_join(worker.get("memberSince"))

    entries = []
    for t in all_tokens:
        tok = t.get("token") or ""
        if tok:
            label = f"{t.get('email') or ''}:{t.get('accountPass') or ''}:{tok}"
            entries.append((label, tok))

    wi_total   = len(entries)
    wi_progress = {"checked": 0}
    wi_done    = asyncio.Event()

    prog_msg = await interaction.followup.send(
        view=_build_progress_cv2(0, wi_total or 1, 0, 0, 0, 0),
        ephemeral=True,
        wait=True,
    )

    async def _wi_updater():
        while not wi_done.is_set():
            await asyncio.sleep(4)
            if wi_done.is_set():
                break
            try:
                await prog_msg.edit(view=_build_progress_cv2(
                    wi_progress["checked"], wi_total or 1, 0, 0, 0, 0,
                ))
            except Exception:
                pass

    _wi_task = asyncio.create_task(_wi_updater())
    try:
        if entries:
            valid_e, locked_l, invalid_l, _ = await _discord_live_check(entries, progress=wi_progress)
            lv_valid   = len(valid_e)
            lv_locked  = len(locked_l)
            lv_invalid = len(invalid_l)
            lv_total   = lv_valid + lv_locked + lv_invalid
            lv_rate    = round((lv_valid / lv_total) * 100) if lv_total > 0 else 0
        else:
            lv_valid = lv_locked = lv_invalid = lv_total = lv_rate = 0
    finally:
        wi_done.set()
        _wi_task.cancel()
        try:
            await _wi_task
        except asyncio.CancelledError:
            pass

    wlist = await aapi_get("/workers/list", admin=True)
    wdata = next((w for w in wlist.get("workers", []) if w.get("discordId") == str(user.id)), None)

    token_block = ""
    if lv_total > 0:
        token_block = (
            f"\n**Valid:** `{lv_valid:,}`  ·  **Locked:** `{lv_locked:,}`  ·  **Invalid:** `{lv_invalid:,}`\n"
            f"**Valid Rate:** `{lv_rate}%`  ·  **Total:** `{lv_total:,}`"
        )
    else:
        token_block = "\nNo tokens in DB yet."

    key_block = f"\n**Worker Key:**\n```{wdata.get('workerKey','N/A')}```" if wdata else ""

    result_view = _cv2(C_BRAND,
        _td(f"## Worker Profile  \u2014  {worker['discordUsername']}"),
        _sep(),
        _td(
            f"**Status:** `{status_label.get(worker['status'], 'UNKNOWN')}`\n"
            f"**Key Expires:** {exp_str}\n"
            f"**Member Since:** {join_str}"
        ),
        _sep(),
        _td(
            f"**Generated Today:** `{daily.get('generated', 0):,}`\n"
            f"**Generated All-Time:** `{alltime.get('generated', 0):,}`"
            + token_block + key_block
        ),
        _sep(),
        _td("-# Live-validated via Discord API  \u00b7  SkyHighEV"),
    )

    try:
        await prog_msg.edit(view=result_view)
    except Exception:
        await interaction.followup.send(view=result_view, ephemeral=True)


# ── /global-stats ─────────────────────────────────────────────────────────────

@bot.tree.command(name="global-stats", description="[Admin] Full system overview — workers and tokens")
@admin_only()
async def global_stats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/dashboard/stats", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", f"```{data['error']}```"), ephemeral=True)
        return

    tw  = data.get('totalWorkers',    0)
    aw  = data.get('activeWorkers',   0)
    lw  = data.get('lockedWorkers',   0)
    tt  = data.get('totalTokens',     0)
    vt  = data.get('validTokens',     0)
    lkt = data.get('lockedTokens',    0)
    it  = data.get('invalidTokens',   0)
    tday= data.get('tokensToday',     0)
    vday= data.get('validToday',      0)
    lday= data.get('lockedToday',     0)
    iday= data.get('invalidToday',    0)
    rday= data.get('unlockRateToday', 0)
    rall= data.get('unlockRateAllTime',0)

    await interaction.followup.send(view=_cv2(C_BRAND,
        _td("##   Global System Overview"),
        _sep(),
        _td(
            f"**Workers Total:** `{tw:,}`\n"
            f"**Active:** `{aw:,}`\n"
            f"**Locked:** `{lw:,}`"
        ),
        _sep(),
        _td(
            f"**\u2014 All-Time Tokens \u2014**\n"
            f"**Valid:** `{vt:,}`\n"
            f"**Locked:** `{lkt:,}`\n"
            f"**Invalid:** `{it:,}`\n"
            f"**Total:** `{tt:,}`\n"
            f"**Unlock Rate:** `{rall}%`"
        ),
        _sep(),
        _td(
            f"**\u2014 Today \u2014**\n"
            f"**Generated:** `{tday:,}`\n"
            f"**Valid:** `{vday:,}`\n"
            f"**Locked:** `{lday:,}`\n"
            f"**Invalid:** `{iday:,}`\n"
            f"**Rate Today:** `{rday}%`"
        ),
        _sep(),
        _td(f"-# {_FOOTER_TEXT}"),
    ), ephemeral=True)


# ── /announce ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="announce", description="[Admin] Send an announcement embed to a channel")
@app_commands.describe(
    channel="Target channel",
    title="Announcement title",
    message="Announcement body",
    ping_everyone="Ping @everyone? (default: False)",
)
@admin_only()
async def announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    message: str,
    ping_everyone: bool = False,
):
    await interaction.response.defer(ephemeral=True)

    ann_view = _cv2(C_BRAND,
        _td(f"## {title}"),
        _sep(),
        _td(message),
        _td(f"-# Announcement by {interaction.user.display_name}  ·  SkyHighEV"),
    )
    content = "@everyone" if ping_everyone else None
    try:
        await channel.send(content=content, view=ann_view)
        await interaction.followup.send(
            view=cv2_ok("Announcement Sent", f"Posted in {channel.mention}"), ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            view=cv2_err("No Permission", f"Cannot send messages in {channel.mention}"), ephemeral=True)


# ── /ping ─────────────────────────────────────────────────────────────────────

@bot.tree.command(name="ping", description="[Admin] Check if the API server is online")
@admin_only()
async def ping_api(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    import time
    start = time.time()
    try:
        r = requests.get(f"{API_BASE_URL}/api/healthz", timeout=10, verify=False)
        latency = round((time.time() - start) * 1000)
        if r.status_code == 200:
            v = _cv2(C_SUCCESS,
                _td("##   API Online"),
                _sep(),
                _td(f"**Latency:** `{latency}ms`  ·  **Endpoint:** `{API_BASE_URL}`  ·  **Discord Latency:** `{round(bot.latency * 1000)}ms`"),
            )
        else:
            v = _cv2(C_WARN,
                _td("##   API Responded with Error"),
                _sep(),
                _td(f"**HTTP Status:** `{r.status_code}`  ·  **Latency:** `{latency}ms`"),
            )
    except requests.exceptions.Timeout:
        v = cv2_err("API Timed Out", f"No response from `{API_BASE_URL}` within 10 seconds.")
    except Exception as ex:
        v = cv2_err("API Unreachable", f"```{ex}```")

    await interaction.followup.send(view=v, ephemeral=True)


# ── /uptime ───────────────────────────────────────────────────────────────────

@bot.tree.command(name="uptime", description="[Admin] Show bot uptime and connection info")
@admin_only()
async def uptime(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    elapsed = int(_time.time() - BOT_START_TIME)
    hours, rem  = divmod(elapsed, 3600)
    minutes, secs = divmod(rem, 60)
    uptime_str = f"{hours}h {minutes}m {secs}s"

    await interaction.followup.send(view=_cv2(C_BRAND,
        _td("## Bot Status"),
        _sep(),
        _td(
            f"**Uptime:** `{uptime_str}`  \u00b7  **Discord Latency:** `{round(bot.latency * 1000)}ms`  \u00b7  **Guilds:** `{len(bot.guilds)}`\n"
            f"**API Server:** `{API_BASE_URL}`\n"
            f"**Start Time:** <t:{int(BOT_START_TIME)}:F>"
        ),
        _sep(),
        _td("-# SkyHighEV"),
    ), ephemeral=True)


# ── /get-credentials ──────────────────────────────────────────────────────────

@bot.tree.command(name="get-credentials", description="[Admin] Retrieve dashboard login credentials")
@admin_only()
async def get_credentials(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    await interaction.followup.send(view=_cv2(C_WARN,
        _td("## Dashboard Credentials"),
        _sep(),
        _td("Use these to log into the control panel. Do not share outside trusted admins."),
        _sep(),
        _td(
            f"**API Server URL:**\n```{API_BASE_URL}```\n"
            f"**Worker API Key:**\n```{WORKER_API_KEY}```\n"
            f"**Admin Key:**\n```{ADMIN_KEY}```\n"
            f"**TOTP Secret:**\n```{TOTP_SECRET}```"
        ),
        _sep(),
        _td("-# SkyHighEV"),
    ), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  NEW ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

# ── /expiring-soon ────────────────────────────────────────────────────────────

@bot.tree.command(name="expiring-soon", description="[Admin] List workers whose keys expire within N days")
@app_commands.describe(days="Number of days to look ahead (default 7)")
@admin_only()
async def expiring_soon(interaction: discord.Interaction, days: int = 7):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/workers/list", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    workers = data.get("workers", [])
    now = utc_now()
    expiring = []
    for w in workers:
        exp_str = w.get("expiresAt") or w.get("keyExpiry") or w.get("expiry")
        if not exp_str:
            continue
        try:
            exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            delta  = (exp_dt - now).total_seconds() / 86400
            if 0 <= delta <= days:
                expiring.append((delta, w, exp_dt))
        except Exception:
            continue

    if not expiring:
        await interaction.followup.send(
            view=cv2_info("Expiring Soon", f"No workers expiring within {days} day(s)."), ephemeral=True,
        )
        return

    expiring.sort(key=lambda x: x[0])
    lines = []
    for delta, w, exp_dt in expiring[:20]:
        name   = w.get("discordUsername", "Unknown")
        exp_ts = exp_dt.strftime("%Y-%m-%d")
        d_str  = f"{delta:.1f}d"
        lines.append(f"  {name:<22}  expires {exp_ts}  ({d_str})")

    table = f"```\n{'WORKER':<22}  EXPIRY DATE  REMAINING\n{'─'*50}\n" + "\n".join(lines) + "\n```"
    await interaction.followup.send(view=_cv2(C_WARN,
        _td(f"## Expiring Within {days} Day(s)"),
        _sep(),
        _td(table),
        _td(f"-# Showing {len(expiring)} worker(s)  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /search-worker ────────────────────────────────────────────────────────────

@bot.tree.command(name="search-worker", description="[Admin] Find workers by partial username")
@app_commands.describe(query="Partial username to search for")
@admin_only()
async def search_worker(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/workers/list", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    workers  = data.get("workers", [])
    q_lower  = query.lower()
    matches  = [w for w in workers if q_lower in w.get("discordUsername", "").lower()]

    if not matches:
        await interaction.followup.send(
            view=cv2_info("Search Results", f"No workers found matching `{query}`."), ephemeral=True,
        )
        return

    lines = []
    for w in matches[:15]:
        name   = w.get("discordUsername", "Unknown")
        status = w.get("keyStatus", w.get("status", "unknown")).upper()
        did    = w.get("discordId", "N/A")
        lines.append(f"  {name:<22}  {status:<8}  ID: {did}")

    table = f"```\n{'WORKER':<22}  STATUS    DISCORD ID\n{'─'*52}\n" + "\n".join(lines) + "\n```"
    await interaction.followup.send(view=_cv2(C_BRAND,
        _td(f"## Search: \"{query}\""),
        _sep(),
        _td(table),
        _td(f"-# Showing {len(matches)} match(es)  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /token-count ──────────────────────────────────────────────────────────────

@bot.tree.command(name="token-count", description="[Admin] Quick token count by status for the whole system")
@admin_only()
async def token_count(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/stats", admin=True)
    if "error" in data:
        data = await aapi_get("/global-stats", admin=True)
    if "error" in data:
        data = await aapi_get("/tokens/count", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    valid   = data.get("validTokens",   data.get("valid",   data.get("totalValid",   "N/A")))
    locked  = data.get("lockedTokens",  data.get("locked",  data.get("totalLocked",  "N/A")))
    invalid = data.get("invalidTokens", data.get("invalid", data.get("totalInvalid", "N/A")))
    total   = data.get("totalTokens",   data.get("total",   "N/A"))
    total_line = f"  ·  **TOTAL:** `{total}`" if total != "N/A" else ""

    await interaction.followup.send(view=_cv2(C_INFO,
        _td("## Token Count"),
        _sep(),
        _td(f"**VALID:** `{valid}`  ·  **LOCKED:** `{locked}`  ·  **INVALID:** `{invalid}`{total_line}"),
    ), ephemeral=True)


# ── /diag-tokens ──────────────────────────────────────────────────────────────
# Investigates the "tool says X, bot says Y" mismatch by showing what's actually
# in the DB for a worker — including ORPHANED tokens (workerKey matches but
# worker_id is NULL, which the old fetch query couldn't see).

@bot.tree.command(name="diag-tokens", description="[Admin] Diagnose token-count mismatches for a worker (linked vs orphaned)")
@app_commands.describe(user="The Discord user to diagnose")
@admin_only()
async def diag_tokens_cmd(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    data = await aapi_get(f"/tokens/diag/{user.id}", admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    w        = data.get("worker", {})
    linked   = data.get("linked",   {"total": 0, "valid": 0, "locked": 0, "invalid": 0})
    orphaned = data.get("orphaned", {"total": 0, "valid": 0, "locked": 0, "invalid": 0})
    combined = data.get("combined", {"total": 0, "valid": 0, "locked": 0, "invalid": 0})
    today    = data.get("todayDailyStats")

    orphan_warn = ""
    if orphaned["total"] > 0:
        orphan_warn = (
            f"\n\n** {orphaned['total']:,} ORPHANED token(s) found!**\n"
            f"These tokens were saved with the right `workerKey` but `worker_id` is NULL "
            f"(worker was missing at the moment the API saved them). They're invisible to "
            f"`/my-value` until you run `/rescue-tokens` on this user."
        )

    today_line = "_no daily stat row for today yet_"
    if today:
        today_line = (
            f"Generated: `{today.get('tokensGenerated', 0):,}`  ·  "
            f"Valid: `{today.get('tokensValid', 0):,}`  ·  "
            f"Locked: `{today.get('tokensLocked', 0):,}`  ·  "
            f"Invalid: `{today.get('tokensInvalid', 0):,}`"
        )

    color = C_WARN if orphaned["total"] > 0 else C_INFO
    await interaction.followup.send(view=_cv2(color,
        _td(f"##   Token Diagnostic  ·  {w.get('discordUsername', user.name)}"),
        _td(f"-# Discord ID: `{w.get('discordId', user.id)}`  ·  Worker ID: `{w.get('id', '?')}`  ·  Key: `{(w.get('workerKey') or '')[:18]}…`"),
        _sep(),
        _td(
            "**Linked tokens** (worker_id set — visible to bot)\n"
            f"Total: `{linked['total']:,}`  ·  V: `{linked['valid']:,}`  ·  L: `{linked['locked']:,}`  ·  I: `{linked['invalid']:,}`"
        ),
        _sep(),
        _td(
            "**Orphaned tokens** (workerKey matches but worker_id NULL — INVISIBLE to /my-value)\n"
            f"Total: `{orphaned['total']:,}`  ·  V: `{orphaned['valid']:,}`  ·  L: `{orphaned['locked']:,}`  ·  I: `{orphaned['invalid']:,}`"
            + orphan_warn
        ),
        _sep(),
        _td(
            "**Combined (true total this user submitted)**\n"
            f"Total: `{combined['total']:,}`  ·  V: `{combined['valid']:,}`  ·  L: `{combined['locked']:,}`  ·  I: `{combined['invalid']:,}`"
        ),
        _sep(),
        _td(f"**Today's daily-stats row**\n{today_line}"),
        _td("-# Run `/rescue-tokens` to re-link orphans  ·  SkyHighEV Diagnostics"),
    ), ephemeral=True)


# ── /rescue-tokens ────────────────────────────────────────────────────────────

@bot.tree.command(name="rescue-tokens", description="[Admin] Re-link orphaned tokens (workerKey matches but worker_id NULL) for a user")
@app_commands.describe(user="The Discord user whose orphaned tokens should be re-linked")
@admin_only()
async def rescue_tokens_cmd(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    data = await aapi_post(f"/tokens/rescue/{user.id}", {}, admin=True)
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    n = int(data.get("rescued", 0))
    if n == 0:
        await interaction.followup.send(view=cv2_info(
            "Nothing to Rescue", f"No orphaned tokens found for **{user.name}**."), ephemeral=True)
        return
    await interaction.followup.send(view=cv2_ok(
        "Tokens Rescued",
        f"Re-linked **{n:,}** orphaned token(s) for **{user.name}**.\n"
        f"-# They will now show up in `/my-value` and the dashboard  ·  SkyHighEV"
    ), ephemeral=True)


# ── /verify-key ───────────────────────────────────────────────────────────────

@bot.tree.command(name="verify-key", description="[Admin] Check if a specific worker key is valid and who owns it")
@app_commands.describe(key="The full worker key to verify")
@admin_only()
async def verify_key(interaction: discord.Interaction, key: str):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get(f"/keys/verify?key={key}", admin=True)
    if "error" in data:
        data = await aapi_get(f"/workers/verify-key?key={key}", admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Key Lookup Failed", data["error"]), ephemeral=True,
        )
        return

    owner  = data.get("discordUsername", data.get("owner",  "Unknown"))
    status = data.get("keyStatus",       data.get("status", "unknown")).upper()
    exp    = data.get("expiresAt",        data.get("expiry", "N/A"))
    did    = data.get("discordId",        "N/A")
    color  = C_SUCCESS if status == "ACTIVE" else (C_ERROR if status in ("REVOKED", "LOCKED") else C_WARN)
    exp_line = f"  ·  **Expires:** `{exp}`" if exp != "N/A" else ""

    await interaction.followup.send(view=_cv2(color,
        _td("## Key Verification"),
        _sep(),
        _td(f"**Key:**\n```{key[:40]}```"),
        _td(f"**Owner:** `{owner}`  ·  **Status:** `{status}`  ·  **Discord ID:** `{did}`{exp_line}"),
    ), ephemeral=True)


# ── /reset-user-tokens ────────────────────────────────────────────────────────

@bot.tree.command(name="reset-user-tokens", description="[Admin] Delete ALL stored tokens for a specific worker")
@app_commands.describe(user="The worker whose tokens you want to wipe")
@admin_only()
async def reset_user_tokens(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_delete(f"/tokens/user/{user.id}", admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Reset Failed", data["error"]), ephemeral=True,
        )
        return

    deleted = data.get("deleted", data.get("count", "?"))
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## User Tokens Cleared"),
        _sep(),
        _td(f"All stored tokens for **{user.display_name}** have been deleted.\nRecords removed: **{deleted}**"),
        _td(f"-# Actioned by {interaction.user.display_name}  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /clear-tokens ─────────────────────────────────────────────────────────────

@bot.tree.command(name="clear-tokens", description="[Admin] Delete all tokens of a given status from the system")
@app_commands.describe(status="Which group to delete: invalid / locked / all")
@app_commands.choices(status=[
    app_commands.Choice(name="invalid", value="invalid"),
    app_commands.Choice(name="locked",  value="locked"),
    app_commands.Choice(name="all",     value="all"),
])
@admin_only()
async def clear_tokens(interaction: discord.Interaction, status: str):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_delete(f"/tokens?status={status}", admin=True)
    if "error" in data:
        data = await aapi_delete(f"/tokens/bulk?status={status}", admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Clear Failed", data["error"]), ephemeral=True,
        )
        return

    deleted = data.get("deleted", data.get("count", "?"))
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Tokens Cleared"),
        _sep(),
        _td(f"Deleted **{deleted}** token(s) with status **{status.upper()}**."),
        _td(f"-# Actioned by {interaction.user.display_name}  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /pause-worker ─────────────────────────────────────────────────────────────

@bot.tree.command(name="pause-worker", description="[Admin] Temporarily pause a worker (revokes key without removing them)")
@app_commands.describe(user="The worker to pause")
@admin_only()
async def pause_worker(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_post(f"/workers/{user.id}/pause", {}, admin=True)
    if "error" in data:
        data = await aapi_post("/workers/pause", {"discordId": str(user.id)}, admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Pause Failed", data["error"]), ephemeral=True,
        )
        return

    await interaction.followup.send(view=_cv2(C_WARN,
        _td("## Worker Paused"),
        _sep(),
        _td(f"**{user.display_name}** has been paused. Their key is locked until manually reactivated."),
        _td(f"-# Actioned by {interaction.user.display_name}  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /session-log ──────────────────────────────────────────────────────────────

@bot.tree.command(name="session-log", description="[Admin] View recent generation sessions for a worker")
@app_commands.describe(user="The worker to look up")
@admin_only()
async def session_log(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get(f"/workers/{user.id}/sessions", admin=True)
    if "error" in data:
        data = await aapi_get(f"/sessions?discordId={user.id}", admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Session Log Failed", data["error"]), ephemeral=True,
        )
        return

    sessions = data.get("sessions", data.get("data", []))
    if not sessions:
        await interaction.followup.send(
            view=cv2_info("Session Log", f"No sessions found for **{user.display_name}**."), ephemeral=True,
        )
        return

    lines = []
    for s in sessions[:10]:
        ts      = s.get("startedAt", s.get("createdAt", "?"))[:16].replace("T", " ")
        gen     = s.get("generated", s.get("total", 0))
        valid   = s.get("valid", 0)
        dur_raw = s.get("duration", s.get("durationSeconds", 0))
        dur_min = int(dur_raw // 60) if isinstance(dur_raw, (int, float)) else "?"
        lines.append(f"  {ts}   gen {gen:>5,}   valid {valid:>4,}   {dur_min}m")

    table = f"```\n{'DATE/TIME':<17}  {'GEN':>8}  {'VALID':>7}  DUR\n{'─'*48}\n" + "\n".join(lines) + "\n```"
    await interaction.followup.send(view=_cv2(C_BRAND,
        _td(f"## Session Log — {user.display_name}"),
        _sep(),
        _td(table),
        _td(f"-# Last {len(sessions[:10])} session(s)  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /add-note ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="add-note", description="[Admin] Attach a note to a worker's account")
@app_commands.describe(user="The worker to annotate", note="The note to store")
@admin_only()
async def add_note(interaction: discord.Interaction, user: discord.Member, note: str):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_post(f"/workers/{user.id}/note", {"note": note}, admin=True)
    if "error" in data:
        data = await aapi_post("/workers/note", {"discordId": str(user.id), "note": note}, admin=True)

    if "error" in data:
        await interaction.followup.send(
            view=cv2_err("Note Failed", data["error"]), ephemeral=True,
        )
        return

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Note Added"),
        _sep(),
        _td(f"Saved note for **{user.display_name}**:\n> {note}"),
        _td(f"-# Added by {interaction.user.display_name}  ·  SkyHighEV"),
    ), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

# ── Leaderboard image builder ─────────────────────────────────────────────────

_FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
_FONT_MONO      = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
_FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_SANS      = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# ── leaderboard image palette ──────────────────────────────────────────────────
_LB_BG         = (8,    6,   20)
_LB_TITLE_BG   = (14,  10,   42)
_LB_HEADER     = (22,  16,   52)
_LB_ROW_EVEN   = (15,  11,   36)
_LB_ROW_ODD    = (11,   8,   27)
_LB_ROW_TOP1   = (40,  28,   72)   # gold-tinted highlight
_LB_ROW_TOP2   = (24,  18,   56)   # silver-tinted highlight
_LB_ROW_TOP3   = (18,  13,   46)   # bronze-tinted highlight
_LB_ACCENT     = (139, 92,  246)   # vivid purple
_LB_ACCENT_DIM = (80,  50,  180)
_LB_ACCENT2    = (99,  102, 241)   # indigo
_LB_TEXT       = (248, 245, 255)
_LB_TEXT_DIM   = (148, 136, 200)
_LB_GOLD       = (251, 191,  36)
_LB_GOLD_DIM   = (120,  88,   8)
_LB_SILVER     = (203, 213, 225)
_LB_SILVER_DIM = ( 80,  90, 110)
_LB_BRONZE     = (234, 138,  52)
_LB_BRONZE_DIM = (100,  55,  12)
_LB_GREEN      = ( 16, 200, 140)
_LB_GREEN_DIM  = (  8,  80,  55)
_LB_AMBER      = (245, 158,  11)
_LB_RED        = (239,  68,  68)
_LB_FOOTER_BG  = (  6,   4,  14)
_LB_SEP        = ( 30,  22,  68)
_LB_BAR_BG     = ( 28,  22,  58)


def _lb_col_text(draw, text, x, w, align, y, row_h, font, fill):
    cy = y + row_h // 2
    if align == "l":
        draw.text((x, cy),          text, font=font, fill=fill, anchor="lm")
    elif align == "r":
        draw.text((x + w, cy),      text, font=font, fill=fill, anchor="rm")
    else:
        draw.text((x + w // 2, cy), text, font=font, fill=fill, anchor="mm")


def _draw_badge(draw, cx, cy, radius, fill, glow_fill, text, font, text_fill):
    """Draw a glowing circle badge with centered text."""
    # outer glow ring
    draw.ellipse([(cx - radius - 4, cy - radius - 4),
                  (cx + radius + 4, cy + radius + 4)], fill=glow_fill)
    # main circle
    draw.ellipse([(cx - radius, cy - radius),
                  (cx + radius, cy + radius)], fill=fill)
    draw.text((cx, cy), text, font=font, fill=text_fill, anchor="mm")


def _draw_rate_bar(draw, x, y, w, h, pct, bar_bg, bar_fill):
    """Draw a mini horizontal progress bar (pill-shaped, Pillow-version-safe)."""
    r = h // 2
    # background pill
    draw.rectangle([(x + r, y), (x + w - r, y + h)], fill=bar_bg)
    draw.ellipse([(x, y), (x + h, y + h)], fill=bar_bg)
    draw.ellipse([(x + w - h, y), (x + w, y + h)], fill=bar_bg)
    # filled portion
    fill_w = max(int(w * pct / 100), h)
    draw.rectangle([(x + r, y), (x + fill_w - r, y + h)], fill=bar_fill)
    draw.ellipse([(x, y), (x + h, y + h)], fill=bar_fill)
    if fill_w > h:
        draw.ellipse([(x + fill_w - h, y), (x + fill_w, y + h)], fill=bar_fill)


def build_leaderboard_image(board: list, title: str, subtitle: str, gen_key: str, valid_key: str) -> discord.File:
    """Render a redesigned leaderboard image and return it as a discord.File."""
    PAD     = 30
    ROW_H   = 62
    HDR_H   = 44
    TITLE_H = 90
    FOOT_H  = 34
    IMG_W   = 960

    entries = board[:10]
    n       = len(entries)
    IMG_H   = TITLE_H + HDR_H + n * ROW_H + HDR_H + FOOT_H + 8

    img  = Image.new("RGB", (IMG_W, IMG_H), _LB_BG)
    draw = ImageDraw.Draw(img)

    f_title  = ImageFont.truetype(_FONT_SANS_BOLD, 30)
    f_sub    = ImageFont.truetype(_FONT_SANS,      13)
    f_brand  = ImageFont.truetype(_FONT_SANS_BOLD, 15)
    f_hdr    = ImageFont.truetype(_FONT_MONO_BOLD, 13)
    f_row    = ImageFont.truetype(_FONT_MONO,      15)
    f_rank   = ImageFont.truetype(_FONT_MONO_BOLD, 14)
    f_footer = ImageFont.truetype(_FONT_SANS,      11)

    RIGHT    = IMG_W - PAD      # 930
    BADGE_CX = PAD + 24         # 54

    # ── column layout (x_left, width, align) ─────────────────────
    C_NAME = (PAD + 62, 310, "l")    # name column
    C_GEN  = (420, 160, "r")         # generated
    C_VAL  = (592, 148, "r")         # valid
    C_RATE = (754, RIGHT - 754, "r") # rate + bar

    # ── title bar (simulated gradient via stacked rects) ──────────
    for step in range(TITLE_H):
        t    = step / TITLE_H
        r    = int(_LB_TITLE_BG[0] + (_LB_BG[0] - _LB_TITLE_BG[0]) * t * 0.5)
        g_c  = int(_LB_TITLE_BG[1] + (_LB_BG[1] - _LB_TITLE_BG[1]) * t * 0.5)
        b    = int(_LB_TITLE_BG[2] + (_LB_BG[2] - _LB_TITLE_BG[2]) * t * 0.5)
        draw.line([(0, step), (IMG_W, step)], fill=(r, g_c, b))

    # left accent strip (double: dim then bright)
    draw.rectangle([(0, 0), (8, TITLE_H)], fill=_LB_ACCENT_DIM)
    draw.rectangle([(0, 0), (4, TITLE_H)], fill=_LB_ACCENT)
    # bottom glowing accent line
    draw.rectangle([(0, TITLE_H - 3), (IMG_W, TITLE_H)],     fill=_LB_ACCENT)
    draw.rectangle([(0, TITLE_H - 6), (IMG_W, TITLE_H - 3)], fill=_LB_ACCENT_DIM)

    draw.text((PAD + 18, 18), title,    font=f_title, fill=_LB_TEXT)
    draw.text((PAD + 18, 60), subtitle, font=f_sub,   fill=_LB_TEXT_DIM)
    draw.text((RIGHT,    52), "SkyHighEV", font=f_brand, fill=_LB_ACCENT, anchor="rm")

    # ── header row ────────────────────────────────────────────────
    y_hdr = TITLE_H
    draw.rectangle([(0, y_hdr), (IMG_W, y_hdr + HDR_H)], fill=_LB_HEADER)
    draw.rectangle([(0, y_hdr + HDR_H - 1), (IMG_W, y_hdr + HDR_H)], fill=_LB_ACCENT_DIM)

    _lb_col_text(draw, "#",          BADGE_CX - 24, 48,     "c", y_hdr, HDR_H, f_hdr, _LB_ACCENT)
    _lb_col_text(draw, "WORKER",     C_NAME[0], C_NAME[1],  C_NAME[2], y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)
    _lb_col_text(draw, "GENERATED",  C_GEN[0],  C_GEN[1],  C_GEN[2],  y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)
    _lb_col_text(draw, "VALID",      C_VAL[0],  C_VAL[1],  C_VAL[2],  y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)
    _lb_col_text(draw, "RATE",       C_RATE[0], C_RATE[1], C_RATE[2], y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)

    # ── row backgrounds & colors for top 3 ───────────────────────
    row_bgs   = {1: _LB_ROW_TOP1, 2: _LB_ROW_TOP2, 3: _LB_ROW_TOP3}
    badge_fg  = {1: _LB_GOLD,   2: _LB_SILVER,  3: _LB_BRONZE}
    badge_glo = {1: _LB_GOLD_DIM, 2: _LB_SILVER_DIM, 3: _LB_BRONZE_DIM}
    badge_txt = {1: (60, 35, 0), 2: (40, 40, 55), 3: (60, 28, 5)}
    name_col  = {1: _LB_GOLD,   2: _LB_SILVER,  3: _LB_BRONZE}
    side_col  = {1: _LB_GOLD,   2: _LB_SILVER,  3: _LB_BRONZE}

    def rate_color(r):
        if r >= 20: return (20, 230, 150)
        if r >= 10: return _LB_GREEN
        if r >= 5:  return _LB_AMBER
        return _LB_RED

    y_data = TITLE_H + HDR_H
    for i, entry in enumerate(entries):
        rank  = entry["rank"]
        name  = entry["discordUsername"]
        gen   = entry.get(gen_key,   entry.get("totalGenerated", 0))
        valid = entry.get(valid_key, entry.get("totalValid",     0))
        rate  = entry.get("unlockRate", 0)

        ry     = y_data + i * ROW_H
        row_bg = row_bgs.get(rank, _LB_ROW_EVEN if i % 2 == 0 else _LB_ROW_ODD)
        draw.rectangle([(0, ry), (IMG_W, ry + ROW_H)], fill=row_bg)

        # left rank-colour accent stripe for top 3
        if rank <= 3:
            draw.rectangle([(0, ry), (5, ry + ROW_H)], fill=side_col[rank])

        cy = ry + ROW_H // 2

        # rank badge
        if rank <= 3:
            _draw_badge(draw, BADGE_CX, cy, 20,
                        badge_fg[rank], badge_glo[rank],
                        str(rank), f_rank, badge_txt[rank])
        else:
            draw.text((BADGE_CX, cy), str(rank),
                      font=f_rank, fill=_LB_TEXT_DIM, anchor="mm")

        # name
        disp      = name[:30] + ("…" if len(name) > 30 else "")
        name_fill = name_col.get(rank, _LB_TEXT)
        _lb_col_text(draw, disp, C_NAME[0], C_NAME[1], C_NAME[2], ry, ROW_H, f_row, name_fill)

        # generated
        _lb_col_text(draw, f"{gen:,}", C_GEN[0], C_GEN[1], C_GEN[2], ry, ROW_H, f_row, _LB_TEXT)

        # valid
        _lb_col_text(draw, f"{valid:,}", C_VAL[0], C_VAL[1], C_VAL[2], ry, ROW_H, f_row, _LB_GREEN)

        # rate: mini bar + percentage
        rc = rate_color(rate)
        bar_x = C_RATE[0] + 6
        bar_w = 90
        bar_y = cy - 4
        bar_h = 8
        _draw_rate_bar(draw, bar_x, bar_y, bar_w, bar_h, min(rate, 100), _LB_BAR_BG, rc)
        draw.text((bar_x + bar_w + 10, cy),
                  f"{rate}%", font=f_row, fill=rc, anchor="lm")

        # row separator
        if i < n - 1:
            draw.rectangle(
                [(PAD + 62, ry + ROW_H - 1), (IMG_W - PAD, ry + ROW_H)],
                fill=_LB_SEP,
            )

    # ── totals row ───────────────────────────────────────────────
    y_tot = TITLE_H + HDR_H + n * ROW_H
    draw.rectangle([(0, y_tot), (IMG_W, y_tot + HDR_H)], fill=_LB_HEADER)
    draw.rectangle([(0, y_tot), (IMG_W, y_tot + 2)],     fill=_LB_ACCENT_DIM)

    t_gen  = sum(e.get(gen_key,   e.get("totalGenerated", 0)) for e in entries)
    t_val  = sum(e.get(valid_key, e.get("totalValid",     0)) for e in entries)
    t_rate = round((t_val / t_gen * 100) if t_gen > 0 else 0)

    draw.text((BADGE_CX, y_tot + HDR_H // 2), "Σ",
              font=f_rank, fill=_LB_ACCENT, anchor="mm")
    _lb_col_text(draw, f"TOP {n} TOTAL", C_NAME[0], C_NAME[1], C_NAME[2], y_tot, HDR_H, f_hdr, _LB_TEXT_DIM)
    _lb_col_text(draw, f"{t_gen:,}",     C_GEN[0],  C_GEN[1],  C_GEN[2],  y_tot, HDR_H, f_hdr, _LB_TEXT)
    _lb_col_text(draw, f"{t_val:,}",     C_VAL[0],  C_VAL[1],  C_VAL[2],  y_tot, HDR_H, f_hdr, _LB_GREEN)
    # rate bar in totals row too
    rc = rate_color(t_rate)
    tot_cy   = y_tot + HDR_H // 2
    tot_bar_x = C_RATE[0] + 6
    _draw_rate_bar(draw, tot_bar_x, tot_cy - 4, 90, 8, min(t_rate, 100), _LB_BAR_BG, rc)
    draw.text((tot_bar_x + 100, tot_cy), f"{t_rate}%", font=f_hdr, fill=rc, anchor="lm")

    # ── footer ───────────────────────────────────────────────────
    y_foot = y_tot + HDR_H + 2
    draw.rectangle([(0, y_foot), (IMG_W, IMG_H)], fill=_LB_FOOTER_BG)
    draw.rectangle([(0, y_foot), (IMG_W, y_foot + 1)], fill=_LB_ACCENT_DIM)
    ts = utc_now().strftime("%d %b %Y  %H:%M UTC")
    draw.text((PAD, y_foot + FOOT_H // 2),
              f"SkyHighEV Worker Bot  ·  {ts}  ·  Ranked by total generated",
              font=f_footer, fill=_LB_TEXT_DIM, anchor="lm")

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return discord.File(buf, filename="leaderboard.png")


# ── coin leaderboard image ─────────────────────────────────────────────────────

def build_coin_lb_image(entries: list) -> discord.File:
    """
    entries: list of dicts with keys: rank, name, balance
    Renders a stylized top-10 coin leaderboard image.
    """
    PAD     = 30
    ROW_H   = 58
    HDR_H   = 40
    TITLE_H = 86
    FOOT_H  = 32
    IMG_W   = 720

    n     = len(entries)
    IMG_H = TITLE_H + HDR_H + n * ROW_H + FOOT_H + 6

    img  = Image.new("RGB", (IMG_W, IMG_H), _LB_BG)
    draw = ImageDraw.Draw(img)

    f_title  = ImageFont.truetype(_FONT_SANS_BOLD, 28)
    f_sub    = ImageFont.truetype(_FONT_SANS,      12)
    f_brand  = ImageFont.truetype(_FONT_SANS_BOLD, 14)
    f_hdr    = ImageFont.truetype(_FONT_MONO_BOLD, 12)
    f_row    = ImageFont.truetype(_FONT_MONO,      15)
    f_rank   = ImageFont.truetype(_FONT_MONO_BOLD, 14)
    f_footer = ImageFont.truetype(_FONT_SANS,      11)

    RIGHT    = IMG_W - PAD
    BADGE_CX = PAD + 22

    C_COL_NAME = (PAD + 56, 320, "l")
    C_COL_BAL  = (PAD + 380, RIGHT - PAD - 380, "r")

    # gradient title bar
    for step in range(TITLE_H):
        t   = step / TITLE_H
        r_v = int(_LB_TITLE_BG[0] + (_LB_BG[0] - _LB_TITLE_BG[0]) * t * 0.55)
        g_v = int(_LB_TITLE_BG[1] + (_LB_BG[1] - _LB_TITLE_BG[1]) * t * 0.55)
        b_v = int(_LB_TITLE_BG[2] + (_LB_BG[2] - _LB_TITLE_BG[2]) * t * 0.55)
        draw.line([(0, step), (IMG_W, step)], fill=(r_v, g_v, b_v))

    draw.rectangle([(0, 0), (6, TITLE_H)], fill=_LB_ACCENT_DIM)
    draw.rectangle([(0, 0), (3, TITLE_H)], fill=_LB_GOLD)
    draw.rectangle([(0, TITLE_H - 3), (IMG_W, TITLE_H)],     fill=_LB_GOLD)
    draw.rectangle([(0, TITLE_H - 6), (IMG_W, TITLE_H - 3)], fill=_LB_GOLD_DIM)

    draw.text((PAD + 16, 16), "\U0001f4b0 Coin Leaderboard", font=f_title, fill=_LB_TEXT)
    draw.text((PAD + 16, 58), "Top 10 richest coin holders",  font=f_sub,   fill=_LB_TEXT_DIM)
    draw.text((RIGHT, 52), "SkyHighEV", font=f_brand, fill=_LB_GOLD, anchor="rm")

    # header row
    y_hdr = TITLE_H
    draw.rectangle([(0, y_hdr), (IMG_W, y_hdr + HDR_H)], fill=_LB_HEADER)
    draw.rectangle([(0, y_hdr + HDR_H - 1), (IMG_W, y_hdr + HDR_H)], fill=_LB_GOLD_DIM)
    _lb_col_text(draw, "#",       BADGE_CX - 22, 44, "c",
                 y_hdr, HDR_H, f_hdr, _LB_GOLD)
    _lb_col_text(draw, "PLAYER",  C_COL_NAME[0], C_COL_NAME[1], C_COL_NAME[2],
                 y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)
    _lb_col_text(draw, "BALANCE \U0001fa99", C_COL_BAL[0], C_COL_BAL[1], C_COL_BAL[2],
                 y_hdr, HDR_H, f_hdr, _LB_TEXT_DIM)

    row_bgs   = {1: _LB_ROW_TOP1, 2: _LB_ROW_TOP2, 3: _LB_ROW_TOP3}
    badge_fg  = {1: _LB_GOLD,   2: _LB_SILVER,  3: _LB_BRONZE}
    badge_glo = {1: _LB_GOLD_DIM, 2: _LB_SILVER_DIM, 3: _LB_BRONZE_DIM}
    badge_txt = {1: (60, 35, 0),  2: (40, 40, 55),    3: (60, 28, 5)}
    name_col  = {1: _LB_GOLD,    2: _LB_SILVER,       3: _LB_BRONZE}
    bal_col   = {1: _LB_GOLD,    2: _LB_SILVER,       3: _LB_BRONZE}

    y_data = TITLE_H + HDR_H
    for i, e in enumerate(entries):
        rank = e["rank"]
        name = e["name"][:28] + ("…" if len(e["name"]) > 28 else "")
        bal  = e["balance"]

        ry     = y_data + i * ROW_H
        row_bg = row_bgs.get(rank, _LB_ROW_EVEN if i % 2 == 0 else _LB_ROW_ODD)
        draw.rectangle([(0, ry), (IMG_W, ry + ROW_H)], fill=row_bg)

        if rank <= 3:
            draw.rectangle([(0, ry), (4, ry + ROW_H)], fill=badge_fg[rank])

        cy = ry + ROW_H // 2

        if rank <= 3:
            _draw_badge(draw, BADGE_CX, cy, 18,
                        badge_fg[rank], badge_glo[rank],
                        str(rank), f_rank, badge_txt[rank])
        else:
            draw.text((BADGE_CX, cy), str(rank), font=f_rank,
                      fill=_LB_TEXT_DIM, anchor="mm")

        _lb_col_text(draw, name, C_COL_NAME[0], C_COL_NAME[1], C_COL_NAME[2],
                     ry, ROW_H, f_row, name_col.get(rank, _LB_TEXT))
        _lb_col_text(draw, f"{bal:,}", C_COL_BAL[0], C_COL_BAL[1], C_COL_BAL[2],
                     ry, ROW_H, f_row, bal_col.get(rank, _LB_GREEN))

        if i < n - 1:
            draw.rectangle([(PAD + 56, ry + ROW_H - 1), (IMG_W - PAD, ry + ROW_H)],
                           fill=_LB_SEP)

    # footer
    y_foot = y_data + n * ROW_H
    draw.rectangle([(0, y_foot), (IMG_W, IMG_H)], fill=_LB_FOOTER_BG)
    draw.rectangle([(0, y_foot), (IMG_W, y_foot + 1)], fill=_LB_GOLD_DIM)
    ts = utc_now().strftime("%d %b %Y  %H:%M UTC")
    draw.text((PAD, y_foot + FOOT_H // 2),
              f"SkyHighEV Economy  ·  {ts}  ·  Ranked by coin balance",
              font=f_footer, fill=_LB_TEXT_DIM, anchor="lm")

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return discord.File(buf, filename="coin_leaderboard.png")


# ── /leaderboard ──────────────────────────────────────────────────────────────

@bot.tree.command(name="leaderboard", description="[Admin] View the top workers ranked by total generation")
@admin_only()
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()

    data = await aapi_get("/workers/leaderboard")
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]))
        return

    board = data.get("leaderboard", [])
    if not board:
        await interaction.followup.send(view=cv2_info("Leaderboard", "No workers have generated tokens yet. Be the first."))
        return

    col_w = max((len(e2["discordUsername"]) for e2 in board[:10]), default=8)
    col_w = max(col_w, 8)
    hdr  = f"{'RNK':<4}  {'WORKER':<{col_w}}  {'GEN':>7}  {'VALID':>6}  {'RATE':>5}"
    sep  = f"{'─'*4}  {'─'*col_w}  {'─'*7}  {'─'*6}  {'─'*5}"
    rows = [hdr, sep]
    for e2 in board[:10]:
        rows.append(f"{e2['rank']:02d}.  {e2['discordUsername'][:col_w]:<{col_w}}  {e2['totalGenerated']:>7,}  {e2['totalValid']:>6,}  {e2['unlockRate']:>4}%")
    rows += [sep, f"{'TOT':<4}  {'(top 10)':<{col_w}}  {sum(e2['totalGenerated'] for e2 in board[:10]):>7,}  {sum(e2['totalValid'] for e2 in board[:10]):>6,}"]
    table = f"```\n{chr(10).join(rows)}\n```"

    lb_view = _cv2(C_GOLD,
        _td(f"##   Worker Leaderboard"),
        _sep(),
        _td(f"Top **{min(len(board), 10)}** workers ranked by all-time tokens generated"),
        _td(table),
        _td(f"-# {_FOOTER_TEXT}"),
    )

    try:
        img_file = build_leaderboard_image(
            board,
            title="WORKER LEADERBOARD",
            subtitle="Ranked by total tokens generated  ·  All-Time",
            gen_key="totalGenerated",
            valid_key="totalValid",
        )
        await interaction.followup.send(view=lb_view, file=img_file)
    except Exception:
        await interaction.followup.send(view=lb_view)


# ── /top-today ────────────────────────────────────────────────────────────────

@bot.tree.command(name="top-today", description="[Admin] See who generated the most tokens today")
@admin_only()
async def top_today(interaction: discord.Interaction):
    await interaction.response.defer()

    data = await aapi_get("/workers/leaderboard?period=today")
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]))
        return

    board = data.get("leaderboard", [])
    if not board:
        await interaction.followup.send(view=cv2_info("Today's Leaders", "No activity recorded today yet."))
        return

    col_w = max((len(e2["discordUsername"]) for e2 in board[:10]), default=8)
    col_w = max(col_w, 8)
    hdr  = f"{'RNK':<4}  {'WORKER':<{col_w}}  {'GEN':>7}  {'VALID':>6}  {'RATE':>5}"
    sep2  = f"{'─'*4}  {'─'*col_w}  {'─'*7}  {'─'*6}  {'─'*5}"
    rows = [hdr, sep2]
    for e2 in board[:10]:
        gen2  = e2.get("todayGenerated", e2.get("totalGenerated", 0))
        valid2 = e2.get("todayValid",     e2.get("totalValid", 0))
        rows.append(f"{e2['rank']:02d}.  {e2['discordUsername'][:col_w]:<{col_w}}  {gen2:>7,}  {valid2:>6,}  {e2.get('unlockRate',0):>4}%")
    rows.append("Resets daily at midnight UTC")
    table = f"```\n{chr(10).join(rows)}\n```"

    td_view = _cv2(C_INFO,
        _td("##   Today's Top Workers"),
        _sep(),
        _td(f"Top **{min(len(board), 10)}** workers by tokens generated today — resets at midnight UTC"),
        _td(table),
        _td(f"-# {_FOOTER_TEXT}"),
    )

    try:
        img_file = build_leaderboard_image(
            board,
            title="TODAY'S TOP WORKERS",
            subtitle="Resets daily at midnight UTC",
            gen_key="todayGenerated",
            valid_key="todayValid",
        )
        await interaction.followup.send(view=td_view, file=img_file)
    except Exception:
        await interaction.followup.send(view=td_view)


# ── /my-rank ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="my-rank", description="[Admin] See your current rank on the worker leaderboard")
@admin_only()
async def my_rank(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get("/workers/leaderboard")
    if "error" in data:
        await interaction.followup.send(view=cv2_err("API Error", data["error"]), ephemeral=True)
        return

    board = data.get("leaderboard", [])
    if not board:
        await interaction.followup.send(
            view=cv2_info("Leaderboard Empty", "No workers have generated tokens yet."), ephemeral=True)
        return

    my_id  = str(interaction.user.id)
    entry  = next((w for w in board if str(w.get("discordId", "")) == my_id), None)

    if not entry:
        await interaction.followup.send(
            view=cv2_info("Not Ranked", "You don't appear on the leaderboard yet. Generate some tokens first."), ephemeral=True)
        return

    rank  = entry["rank"]
    total = len(board)
    gen   = entry.get("totalGenerated", 0)
    valid = entry.get("totalValid", 0)
    rate  = entry.get("unlockRate", 0)

    medal = {1: "", 2: "", 3: ""}.get(rank, f"#{rank}")
    color = C_GOLD if rank <= 3 else C_BRAND

    move_up = ""
    if rank > 1:
        above = board[rank - 2]
        gap   = above.get("totalGenerated", 0) - gen
        move_up = f"\n**To move up:** Generate **{gap:,}** more to pass **{above['discordUsername']}**"

    await interaction.followup.send(view=_cv2(color,
        _td(f"## {medal}  Your Leaderboard Rank"),
        _sep(),
        _td(
            f"**{interaction.user.display_name}**\n"
            f"**Rank:** `{rank}` of `{total}` workers  ·  "
            f"**⚙ Generated:** `{gen:,}` tokens  ·  "
            f"**Valid:** `{valid:,}` ({rate}% rate)"
            + move_up
        ),
        _td(f"-# {_FOOTER_TEXT}"),
    ), ephemeral=True)


# ── /profile ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="profile", description="View your worker profile and live token status")
async def profile(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in data or not data.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You do not have a worker key. Contact an admin."), ephemeral=True)
        return

    worker  = data["worker"]
    daily   = data.get("dailyStats", {})
    alltime = data.get("allTimeStats", {})

    status_label = {"VALID": "VALID", "LOCKED": "LOCKED", "EXPIRED": "EXPIRED"}
    exp_str  = fmt_exp(worker.get("expiresAt"))
    join_str = fmt_join(worker.get("memberSince"))
    susp = _is_suspended(str(interaction.user.id))
    status_display = status_label.get(worker["status"], "UNKNOWN")
    if susp:
        status_display += "   Suspended"

    # Fetch tokens from DB to get token strings for live validation
    token_data = await aapi_get("/tokens/fetch", params={"discordId": str(interaction.user.id)}, admin=True)
    all_tokens = token_data.get("tokens", []) if "error" not in token_data else []

    # Build live-check entries
    entries = []
    for t in all_tokens:
        tok = t.get("token") or ""
        if tok:
            label = f"{t.get('email') or ''}:{t.get('accountPass') or ''}:{tok}"
            entries.append((label, tok))

    pf_total    = len(entries)
    pf_progress = {"checked": 0}
    pf_done     = asyncio.Event()

    prog_msg = await interaction.followup.send(
        view=_build_progress_cv2(0, pf_total or 1, 0, 0, 0, 0),
        ephemeral=True,
        wait=True,
    )

    async def _pf_updater():
        while not pf_done.is_set():
            await asyncio.sleep(4)
            if pf_done.is_set():
                break
            try:
                await prog_msg.edit(view=_build_progress_cv2(
                    pf_progress["checked"], pf_total or 1, 0, 0, 0, 0,
                ))
            except Exception:
                pass

    _pf_task = asyncio.create_task(_pf_updater())
    try:
        if entries:
            valid_e, locked_l, invalid_l, _ = await _discord_live_check(entries, progress=pf_progress)
            lv_valid   = len(valid_e)
            lv_locked  = len(locked_l)
            lv_invalid = len(invalid_l)
            lv_total   = lv_valid + lv_locked + lv_invalid
            lv_rate    = round((lv_valid / lv_total) * 100) if lv_total > 0 else 0
        else:
            lv_valid = lv_locked = lv_invalid = lv_total = lv_rate = 0
    finally:
        pf_done.set()
        _pf_task.cancel()
        try:
            await _pf_task
        except asyncio.CancelledError:
            pass

    token_block = ""
    if lv_total > 0:
        token_block = (
            f"\n**— Live Token Status —**\n"
            f"**Valid:** `{lv_valid:,}`  ·  **Locked:** `{lv_locked:,}`  ·  **Invalid:** `{lv_invalid:,}`\n"
            f"**Valid Rate:** `{lv_rate}%`  ·  **Total:** `{lv_total:,}`"
        )
    else:
        token_block = "\nNo tokens in DB yet."

    susp_block = f"\n **Suspended:** {susp.get('reason','—')}" if susp else ""

    result_view = _cv2(C_BRAND,
        _td(f"## Worker Profile  ·  {worker['discordUsername']}"),
        _sep(),
        _td(
            f"**Key Status:** `{status_display}`  ·  "
            f"**Expires:** {exp_str}  ·  **Member Since:** {join_str}"
        ),
        _td(
            f"**— Generation Stats —**\n"
            f"**Today:** `{daily.get('generated', 0):,}`  ·  **All-Time:** `{alltime.get('generated', 0):,}`"
            + token_block + susp_block
        ),
        _td("-# Live-validated via Discord API  ·  SkyHighEV  ·  Worker System"),
    )

    try:
        await prog_msg.edit(view=result_view)
    except Exception:
        await interaction.followup.send(view=result_view, ephemeral=True)


# ── /my-key ───────────────────────────────────────────────────────────────────

@bot.tree.command(name="my-key", description="Show your own worker key (private)")
async def my_key(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in data or not data.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You do not have a worker key. Contact an admin."), ephemeral=True)
        return

    worker  = data["worker"]
    exp_str = fmt_exp(worker.get("expiresAt"))

    wlist = await aapi_get("/workers/list", admin=True)
    wdata = next((w for w in wlist.get("workers", []) if w.get("discordId") == str(interaction.user.id)), None)

    key_value = wdata.get("workerKey", "N/A") if wdata else "Could not retrieve key"
    await interaction.followup.send(view=_cv2(C_BRAND,
        _td("## Your Worker Key"),
        _sep(),
        _td("Keep this key private. Do not share it with anyone."),
        _td(
            f"**Key:**\n```{key_value}```\n"
            f"**Status:** `{worker.get('status', 'UNKNOWN')}`  ·  **Expires:** {exp_str}"
        ),
        _td("-# SkyHighEV"),
    ), ephemeral=True)


# ── /help ─────────────────────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available bot commands")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    kids = [
        _td("## Command Reference"),
        _sep(),
        _td(
            "**Worker Commands**\n"
            "`/profile` — View your stats and key status\n"
            "`/my-key` — Show your worker key privately\n"
            "`/my-value` — Live-check your tokens and see estimated earnings\n"
            "`/token-price` — View the current price per valid token\n"
            "`/set-payout` — Save your payout method (PayPal, crypto, etc.)\n"
            "`/request-payout` — Submit a payout request for your valid tokens\n"
            "`/leaderboard` — See top workers ranked by total generation\n"
            "`/top-today` — See who generated the most today\n"
            "`/help` — This command"
        ),
        _sep(),
        _td(
            "** Economy — Earning Coins**\n"
            "`/balance` — Check your coin balance (or someone else's)\n"
            "`/daily` — Claim your daily reward (500–2,500 , streak bonuses!)\n"
            "`/work` — Do a job and earn coins (1-hour cooldown)\n"
            "`/coin-leaderboard` — See the richest coin holders\n"
            "`/withdraw-coins` — Cash out your coins for real money\n"
            "`/set-payout` — Set your payout method first"
        ),
        _sep(),
        _td(
            "** Economy — Games**\n"
            "`/mines` — Mines grid game: reveal tiles, cash out anytime or boom!\n"
            "`/blackjack` — Blackjack vs the dealer (Hit / Stand / Double)\n"
            "`/slots` — Spin the slot machine for up to 10x!\n"
            "`/coinflip` — Heads or Tails — double or nothing\n"
            "`/dice` — Guess High (4–6) or Low (1–3) for 2x payout\n"
            "`/tictactoe` — Challenge a user to Tic-Tac-Toe (optional wager)"
        ),
        _sep(),
        _td(
            "** Economy — Robbery**\n"
            "`/rob` — Try to steal coins from another user (35% success, 1-hr cooldown)\n"
            "`/robprotection` — Buy 7-day protection for 7,500  — thieves get fined!"
        ),
    ]

    if is_admin(interaction):
        kids += [
            _sep(),
            _td(
                "**Admin — Worker Management**\n"
                "`/create-key` — Issue a worker key (blocks if already active)\n"
                "`/revoke-key` — Lock a worker key\n"
                "`/kick-worker` — Permanently remove a worker\n"
                "`/set-expiry` — Update expiry on a worker key\n"
                "`/reset-stats` — Reset a worker's daily stats\n"
                "`/pause-worker` — Temporarily lock a worker's key\n"
                "`/list-workers` — See all registered workers\n"
                "`/worker-info` — Detailed stats for a specific worker\n"
                "`/search-worker` — Find workers by partial username\n"
                "`/expiring-soon` — Workers expiring within N days\n"
                "`/session-log` — View recent sessions for a worker\n"
                "`/add-note` — Attach a note to a worker's account"
            ),
            _sep(),
            _td(
                "**Admin — Tokens and Stats**\n"
                "`/fetch-tokens` — Export tokens as 3 sorted files\n"
                "`/check-token` — Check status of up to 50 tokens (DB lookup)\n"
                "`/live-check` — Check tokens LIVE via Discord API (upload .txt file)\n"
                "`/token-count` — Quick system-wide token count by status\n"
                "`/reset-user-tokens` — Wipe all tokens for a specific worker\n"
                "`/clear-tokens` — Delete all tokens of a given status\n"
                "`/verify-key` — Look up who owns a key and its status\n"
                "`/global-stats` — Full system stats overview"
            ),
            _sep(),
            _td(
                "**Admin — Payouts**\n"
                "`/set-token-price` — Set the $ price per valid token\n"
                "`/token-price` — View the current token price\n"
                "`/payouts` — View all pending payout requests\n"
                "`/mark-paid` — Mark a payout request as paid"
            ),
            _sep(),
            _td(
                "**Admin — Economy**\n"
                "`/give-coins` — Give coins to a user\n"
                "`/take-coins` — Take coins from a user\n"
                "`/set-coin-rate` — Set coin-to-dollar conversion rate\n"
                "`/set-coin-price` — Set price by coin amount & USD (e.g. 10k coins = $0.10)\n"
                "`/coin-withdrawals` — View pending coin withdrawal requests\n"
                "`/approve-withdrawal` — Mark a coin withdrawal as paid"
            ),
            _sep(),
            _td(
                "**Admin — Tools**\n"
                "`/announce` — Post an announcement to a channel\n"
                "`/broadcast-dm` — DM all registered workers\n"
                "`/ping` — Check if the API server is online\n"
                "`/uptime` — Show bot uptime and connection info\n"
                "`/get-credentials` — Get dashboard login details"
            ),
        ]

    kids.append(_td("-# SkyHighEV"))
    await interaction.followup.send(view=_cv2(C_BRAND, *kids), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAYOUT SYSTEM  —  local JSON storage (no API dependency)
# ══════════════════════════════════════════════════════════════════════════════

# ── Payout UI Views ────────────────────────────────────────────────────────────

class PayoutConfirmLayout(discord.ui.LayoutView):
    """Ephemeral confirm/cancel step shown to the worker after validation."""

    def __init__(self, req_data: dict, notify_channel_id: int, user_avatar_url: str):
        super().__init__(timeout=300)
        self.req_data          = req_data
        self.notify_channel_id = notify_channel_id
        self.user_avatar_url   = user_avatar_url
        self.done              = False
        self._build()

    def _build(self):
        self.clear_items()
        req = self.req_data
        self.add_item(_cv2_cont(
            _td("## Confirm Your Payout Request"),
            _sep(),
            _td(
                f"All tokens validated \u2014 **zero errors**.\n"
                f"Review the breakdown below and confirm to submit."
            ),
            _sep(),
            _td(
                f"**Valid:** `{req['validCount']:,}`\n"
                f"**Locked:** `{req.get('lockedCount', 0):,}`\n"
                f"**Invalid:** `{req.get('invalidCount', 0):,}`\n"
                f"**Price/Token:** `${req['pricePerToken']:.4f}`\n"
                f"**Total Payout:** `${req['amountUsd']:.2f}`\n"
                f"**Payout Method:**\n```{req['payoutMethod']}```"
            ),
            _sep(),
            _td("-# You have 5 minutes to confirm  \u00b7  SkyHighEV"),
            color=C_INFO,
        ))
        confirm_btn = discord.ui.Button(label="Confirm Payout", style=discord.ButtonStyle.success, emoji="")
        confirm_btn.callback = self._confirm
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, emoji="")
        cancel_btn.callback = self._cancel
        self.add_item(discord.ui.ActionRow(confirm_btn, cancel_btn))

    async def _confirm(self, interaction: discord.Interaction):
        if self.done:
            await interaction.response.defer()
            return
        self.done = True
        self.stop()

        db     = _load_payout_db()
        req_id = db.get("nextId", 1)
        req    = {**self.req_data, "id": req_id, "status": "PENDING"}
        db.setdefault("payoutRequests", []).append(req)
        db["nextId"] = req_id + 1
        _save_payout_db(db)

        await interaction.response.edit_message(
            content=None, embeds=[], attachments=[],
            view=_cv2(C_SUCCESS,
                _td("##   Payout Request Submitted"),
                _sep(),
                _td(
                    f"**Valid Tokens:** `{req['validCount']:,}`\n"
                    f"**Price/Token:** `${req['pricePerToken']:.4f}`\n"
                    f"**Total Amount:** `${req['amountUsd']:.2f}`\n"
                    f"**Payout Method:**\n```{req['payoutMethod']}```\n"
                    f"**Request ID:** `#{req_id}`"
                ),
                _sep(),
                _td("-# An admin will review and process your payout  \u00b7  SkyHighEV"),
            ),
        )

        if self.notify_channel_id:
            ch = bot.get_channel(self.notify_channel_id)
            if ch:
                await ch.send(view=_cv2(C_WARN,
                    _td("##   New Payout Request"),
                    _sep(),
                    _td(f"<@{req['discordId']}> has submitted a payout request."),
                    _sep(),
                    _td(
                        f"**Worker:** {req['discordUsername']} (`{req['discordId']}`)\n"
                        f"**Valid:** `{req['validCount']:,}`\n"
                        f"**Locked:** `{req.get('lockedCount', 0):,}`\n"
                        f"**Invalid:** `{req.get('invalidCount', 0):,}`\n"
                        f"**Amount:** `${req['amountUsd']:.2f}`\n"
                        f"**Rate:** `${req['pricePerToken']:.4f}`/token\n"
                        f"**Payout Method:**\n```{req['payoutMethod']}```\n"
                        f"**Request ID:** `#{req_id}`"
                    ),
                    _sep(),
                    _td(f"-# Use /mark-paid {req_id} to mark as paid  \u00b7  SkyHighEV"),
                ))

    async def _cancel(self, interaction: discord.Interaction):
        if self.done:
            await interaction.response.defer()
            return
        self.done = True
        self.stop()
        await interaction.response.edit_message(
            content=None, embeds=[], attachments=[],
            view=cv2_warn("Cancelled", "Your payout request has been cancelled."),
        )


async def _do_payout_request(interaction: discord.Interaction):
    """Shared handler for the payout request button."""
    await interaction.response.defer(ephemeral=True)

    wdata = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in wdata or not wdata.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You don't have a worker profile."), ephemeral=True)
        return

    susp = _is_suspended(str(interaction.user.id))
    if susp:
        susp_until = ""
        if susp.get("until"):
            susp_until = f"\n**Lifts At:** <t:{int(datetime.fromisoformat(susp['until']).timestamp())}:F>"
        await interaction.followup.send(
            view=cv2_err("Suspended",
                         f"You are suspended from payouts.\n**Reason:** {susp.get('reason','—')}" + susp_until), ephemeral=True)
        return

    db            = _load_payout_db()
    payout_method = db.get("payoutMethods", {}).get(str(interaction.user.id))
    if not payout_method:
        await interaction.followup.send(
            view=cv2_err("No Payout Method",
                         "Set your payout method first with `/set-payout` before requesting."), ephemeral=True)
        return

    price = db.get("tokenPrice", 0)
    if price == 0:
        await interaction.followup.send(
            view=cv2_err("Price Not Set", "An admin hasn't set the token price yet. Check back later."), ephemeral=True)
        return

    existing = [r for r in db.get("payoutRequests", [])
                if r["discordId"] == str(interaction.user.id) and r["status"] == "PENDING"]
    if existing:
        await interaction.followup.send(
            view=cv2_err("Already Pending",
                         f"You already have a pending payout request (ID: `#{existing[0]['id']}`). "
                         "Wait for an admin to process it first."), ephemeral=True)
        return

    token_data = await aapi_get("/tokens/fetch", params={"discordId": str(interaction.user.id)}, admin=True)
    all_tokens = token_data.get("tokens", []) if "error" not in token_data else []
    if not all_tokens:
        await interaction.followup.send(
            view=cv2_err("No Tokens", "You have no tokens in the database yet."), ephemeral=True)
        return

    await interaction.followup.send(view=cv2_info(
        "Validating Tokens",
        f"Live-validating **{len(all_tokens):,}** token(s) against Discord API\u2026\n"
        f"Any errors will be retried until the result is clean. This may take a few minutes.",
    ), ephemeral=True)

    def fmt_line(t):
        return f"{t.get('email') or ''}:{t.get('accountPass') or ''}:{t.get('token') or ''}"

    entries = [(fmt_line(t), t.get("token") or "") for t in all_tokens]
    valid_list, locked_list, invalid_list, error_list = await _discord_live_check(entries)

    if error_list:
        await interaction.followup.send(
            view=cv2_err(
                "Validation Incomplete",
                f"**{len(error_list)}** token(s) still couldn't be reached after multiple retries "
                f"due to network issues with Discord's API.\n\n"
                f"Please wait a minute and try again \u2014 your payout was **not** submitted.",
            ), ephemeral=True)
        return

    valid_count = len(valid_list)
    if valid_count == 0:
        await interaction.followup.send(
            view=cv2_err("No Valid Tokens",
                         "None of your tokens are live-valid. Phone Locked and Invalid tokens cannot be paid out."), ephemeral=True)
        return

    valid_token_strs = [tok for _, tok in valid_list]
    pdb_check        = _load_payout_db()
    fraud_warnings   = _check_payout_fraud(str(interaction.user.id), valid_token_strs, pdb_check)
    if fraud_warnings:
        await interaction.followup.send(view=cv2_err(
            "Fraud Alert \u2014 Payout Blocked",
            "\n".join(fraud_warnings) +
            "\n\nYour payout has been **blocked automatically**. "
            "An admin has been notified. Contact support if you believe this is an error.",
        ), ephemeral=True)
        if PAYOUT_NOTIFY_CHANNEL_ID:
            alert_ch = bot.get_channel(PAYOUT_NOTIFY_CHANNEL_ID)
            if alert_ch:
                await alert_ch.send(view=_cv2(C_ERROR,
                    _td("##   Fraud Alert \u2014 Payout Blocked"),
                    _sep(),
                    _td(
                        f"**Worker:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"**Warnings:**\n" + "\n".join(fraud_warnings)
                    ),
                    _sep(),
                    _td("-# SkyHighEV"),
                ))
        return

    amount  = round(valid_count * price, 4)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    req_data = {
        "discordId":       str(interaction.user.id),
        "discordUsername": interaction.user.name,
        "validCount":      valid_count,
        "lockedCount":     len(locked_list),
        "invalidCount":    len(invalid_list),
        "pricePerToken":   price,
        "amountUsd":       amount,
        "payoutMethod":    payout_method,
        "createdAt":       created,
        "paidAt":          None,
        "tokens":          valid_token_strs,
    }

    confirm_layout = PayoutConfirmLayout(req_data, PAYOUT_NOTIFY_CHANNEL_ID, interaction.user.display_avatar.url)
    await interaction.followup.send(view=confirm_layout, ephemeral=True)


class CoinPayoutModal(discord.ui.Modal, title="Coins Payout"):
    """Modal for requesting a direct coin-based payout from the panel."""
    amount = discord.ui.TextInput(
        label="Amount of coins to withdraw",
        placeholder="e.g. 10000  (minimum 5,000)",
        required=True,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = (self.amount.value or "").strip().replace(",", "").replace("_", "").replace(" ", "")
        try:
            amt = int(raw)
        except ValueError:
            await interaction.followup.send(view=cv2_err(
                "Invalid Amount", "Please enter a whole number (e.g. `10000`)."), ephemeral=True)
            return
        if amt <= 0:
            await interaction.followup.send(view=cv2_err(
                "Invalid Amount", "Amount must be greater than zero."), ephemeral=True)
            return
        await _do_coin_payout(interaction, amt)


async def _do_coin_payout_button(interaction: discord.Interaction):
    """Open the coins-payout modal when the panel button is clicked."""
    await interaction.response.send_modal(CoinPayoutModal())


class PayoutPanelView(discord.ui.View):
    """Persistent public panel — workers click this to trigger payout flow."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Request Payout",
        style=discord.ButtonStyle.success,
        emoji="\U0001f4b8",
        custom_id="payout_panel:request",
    )
    async def request_payout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_payout_request(interaction)

    @discord.ui.button(
        label="Coins Payout",
        style=discord.ButtonStyle.primary,
        emoji="\U0001fa99",  # 🪙
        custom_id="payout_panel:coins",
    )
    async def coins_payout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CoinPayoutModal())

PAYOUT_FILE = "payout_data.json"

def _load_payout_db() -> dict:
    if os.path.exists(PAYOUT_FILE):
        try:
            with open(PAYOUT_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tokenPrice": 0, "payoutMethods": {}, "payoutRequests": [], "nextId": 1}

def _save_payout_db(db: dict):
    with open(PAYOUT_FILE, "w") as f:
        json.dump(db, f, indent=2)

# ── /set-token-price ──────────────────────────────────────────────────────────

@bot.tree.command(name="set-token-price", description="[Admin] Set the price per valid token in USD")
@app_commands.describe(price="Price in USD per valid token (e.g. 0.05)")
@admin_only()
async def set_token_price(interaction: discord.Interaction, price: float):
    await interaction.response.defer(ephemeral=True)
    if price < 0:
        await interaction.followup.send(view=cv2_err("Invalid", "Price must be 0 or greater."), ephemeral=True)
        return
    db = _load_payout_db()
    db["tokenPrice"] = price
    _save_payout_db(db)
    await interaction.followup.send(view=cv2_ok(
        "Token Price Updated",
        f"New price: **${price:.4f}** per valid token.\n"
        f"-# Workers will see this rate on /my-value and /request-payout  ·  SkyHighEV",
    ), ephemeral=True)


# ── /token-price ──────────────────────────────────────────────────────────────

@bot.tree.command(name="token-price", description="Show the current price per valid token")
async def token_price(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    db = _load_payout_db()
    price = db.get("tokenPrice", 0)
    if price == 0:
        desc = "No price has been set yet. Ask an admin to set one with `/set-token-price`."
    else:
        desc = f"**${price:.4f}** per valid token"
    await interaction.followup.send(view=_cv2(C_BRAND,
        _td("## Token Price"),
        _sep(),
        _td(desc),
        _td("-# Use /my-value to see your estimated earnings  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /my-value ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="my-value", description="See your token breakdown and estimated earnings")
async def my_value(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    wdata = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in wdata or not wdata.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You do not have a worker profile."), ephemeral=True)
        return

    pdb   = _load_payout_db()
    price = pdb.get("tokenPrice", 0)

    token_data = await aapi_get("/tokens/fetch", params={"discordId": str(interaction.user.id)}, admin=True)
    all_tokens = token_data.get("tokens", []) if "error" not in token_data else []

    if not all_tokens:
        await interaction.followup.send(
            view=cv2_err("No Tokens", "You have no tokens in the database yet."), ephemeral=True)
        return

    db_valid   = sum(1 for t in all_tokens if t.get("status") == "VALID")
    db_locked  = sum(1 for t in all_tokens if t.get("status") == "LOCKED")
    db_invalid = sum(1 for t in all_tokens if t.get("status") == "INVALID")
    db_total   = len(all_tokens)
    rate       = round((db_valid / db_total) * 100) if db_total > 0 else 0
    estimated  = db_valid * price

    if price > 0:
        value_line = (
            f"\n** Price/Token:** `${price:.4f}`  ·  **Estimated Value:** `${estimated:.2f}`\n"
            f"-# Based on {db_valid:,} valid token(s) at ${price:.4f} each"
        )
    else:
        value_line = "\n-# Price per token has not been set yet. Ask an admin to set it with /set-token-price"

    await interaction.followup.send(view=_cv2(C_BRAND,
        _td(f"## Your Token Value  ·  {interaction.user.display_name}"),
        _sep(),
        _td(
            f"**Valid:** `{db_valid:,}`  ·  **Locked:** `{db_locked:,}`  ·  **Invalid:** `{db_invalid:,}`\n"
            f"**Valid Rate:** `{rate}%`"
            + value_line
        ),
        _td("-# Status saved at account creation  ·  Use /request-payout to cash out  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /setup-payout-panel ───────────────────────────────────────────────────────

@bot.tree.command(name="setup-payout-panel", description="[Admin] Post the payout request panel embed in this channel")
@admin_only()
async def setup_payout_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    class _PayoutPanelLayout(discord.ui.LayoutView):
        def __init__(self):
            super().__init__(timeout=None)
            self.add_item(_cv2_cont(
                _td("##   Request Your Payout"),
                _sep(),
                _td(
                    "Choose how you want to cash out:\n\n"
                    "**\U0001f4b8 Request Payout** — token-based payout (live-validated against Discord)\n"
                    "**\U0001fa99 Coins Payout** — direct withdrawal of your coin balance"
                ),
                _sep(),
                _td(
                    "**Before you click:**\n"
                    "\u203a You must be a registered worker\n"
                    "\u203a Set your payout method with `/set-payout` first\n"
                    "\u203a You can only have one pending request at a time per type"
                ),
                _sep(),
                _td("-# SkyHighEV Worker Payout System"),
                color=C_BRAND,
            ))
            req_btn = discord.ui.Button(
                label="Request Payout",
                style=discord.ButtonStyle.success,
                emoji="\U0001f4b8",
                custom_id="payout_panel:request",
            )
            req_btn.callback = _do_payout_request

            coins_btn = discord.ui.Button(
                label="Coins Payout",
                style=discord.ButtonStyle.primary,
                emoji="\U0001fa99",
                custom_id="payout_panel:coins",
            )
            coins_btn.callback = _do_coin_payout_button
            self.add_item(discord.ui.ActionRow(req_btn, coins_btn))

    await interaction.channel.send(view=_PayoutPanelLayout())
    await interaction.followup.send(
        view=cv2_ok("Panel Posted", "Payout panel sent to this channel."), ephemeral=True)


# ── /set-payout ───────────────────────────────────────────────────────────────

@bot.tree.command(name="set-payout", description="Save your preferred payout method (PayPal, crypto, etc.)")
@app_commands.describe(method="Your payout details, e.g. 'PayPal: you@email.com' or 'BTC: 1A2b3...'")
async def set_payout(interaction: discord.Interaction, method: str):
    await interaction.response.defer(ephemeral=True)

    wdata = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in wdata or not wdata.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You do not have a worker profile."), ephemeral=True)
        return

    db = _load_payout_db()
    db.setdefault("payoutMethods", {})[str(interaction.user.id)] = method.strip()
    _save_payout_db(db)

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Payout Method Saved"),
        _sep(),
        _td(f"**Method:**\n```{method.strip()}```"),
        _td("-# Use /request-payout to submit a payout request  ·  SkyHighEV"),
    ), ephemeral=True)


# ── /request-payout ───────────────────────────────────────────────────────────

@bot.tree.command(name="request-payout", description="Request a payout for your valid tokens")
async def request_payout(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    wdata = await aapi_get(f"/workers/profile/{interaction.user.id}")
    if "error" in wdata or not wdata.get("worker"):
        await interaction.followup.send(
            view=cv2_err("Not Registered", "You do not have a worker profile."), ephemeral=True)
        return

    susp = _is_suspended(str(interaction.user.id))
    if susp:
        susp_until = ""
        if susp.get("until"):
            susp_until = f"\n**Lifts At:** <t:{int(datetime.fromisoformat(susp['until']).timestamp())}:F>"
        await interaction.followup.send(
            view=cv2_err("  Suspended",
                         f"You are suspended from payouts.\n**Reason:** {susp.get('reason','—')}" + susp_until), ephemeral=True)
        return

    db            = _load_payout_db()
    payout_method = db.get("payoutMethods", {}).get(str(interaction.user.id))
    if not payout_method:
        await interaction.followup.send(
            view=cv2_err("No Payout Method",
                         "Set your payout method first with `/set-payout` before requesting."), ephemeral=True)
        return

    price = db.get("tokenPrice", 0)
    if price == 0:
        await interaction.followup.send(
            view=cv2_err("Price Not Set", "An admin hasn't set the token price yet. Check back later."), ephemeral=True)
        return

    # Block duplicate pending requests
    existing = [r for r in db.get("payoutRequests", [])
                if r["discordId"] == str(interaction.user.id) and r["status"] == "PENDING"]
    if existing:
        await interaction.followup.send(
            view=cv2_err("Already Pending",
                         f"You already have a pending payout request (ID: `{existing[0]['id']}`). "
                         "Wait for an admin to process it first."), ephemeral=True)
        return

    token_data = await aapi_get("/tokens/fetch", params={"discordId": str(interaction.user.id)}, admin=True)
    all_tokens = token_data.get("tokens", []) if "error" not in token_data else []
    if not all_tokens:
        await interaction.followup.send(
            view=cv2_err("No Tokens", "You have no tokens in the database yet."), ephemeral=True)
        return

    valid_count  = sum(1 for t in all_tokens if t.get("status") == "VALID")
    locked_count = sum(1 for t in all_tokens if t.get("status") == "LOCKED")
    inv_count    = sum(1 for t in all_tokens if t.get("status") == "INVALID")

    if valid_count == 0:
        await interaction.followup.send(
            view=cv2_err("No Valid Tokens",
                         "You have no VALID tokens in the database. Only VALID tokens can be paid out."), ephemeral=True)
        return

    amount    = round(valid_count * price, 4)
    req_id    = db.get("nextId", 1)
    created   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    req = {
        "id":              req_id,
        "discordId":       str(interaction.user.id),
        "discordUsername": interaction.user.name,
        "validCount":      valid_count,
        "pricePerToken":   price,
        "amountUsd":       amount,
        "payoutMethod":    payout_method,
        "status":          "PENDING",
        "createdAt":       created,
        "paidAt":          None,
    }
    db.setdefault("payoutRequests", []).append(req)
    db["nextId"] = req_id + 1
    _save_payout_db(db)

    # ── Confirm to the worker ──
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##   Payout Request Submitted"),
        _sep(),
        _td(
            f"**Valid Tokens:** `{valid_count:,}`  ·  "
            f"** Price/Token:** `${price:.4f}`  ·  "
            f"**Total Amount:** `${amount:.2f}`\n"
            f"**Payout Method:**\n```{payout_method}```\n"
            f"**Request ID:** `#{req_id}`"
        ),
        _td("-# An admin will review and process your payout manually  ·  SkyHighEV"),
    ), ephemeral=True)

    # ── Notify admin channel ──
    if PAYOUT_NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(PAYOUT_NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(view=_cv2(C_WARN,
                _td("##   New Payout Request"),
                _sep(),
                _td(f"{interaction.user.mention} has submitted a payout request."),
                _td(
                    f"**Worker:** {interaction.user.name} (`{interaction.user.id}`)\n"
                    f"**Valid:** `{valid_count:,}`  ·  **Amount:** `${amount:.2f}`  ·  "
                    f"**Rate:** `${price:.4f}`/token\n"
                    f"**Payout Method:**\n```{payout_method}```\n"
                    f"**Request ID:** `#{req_id}`"
                ),
                _td(f"-# Use /mark-paid {req_id} to mark as paid  ·  SkyHighEV"),
            ))


# ── /payouts ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="payouts", description="[Admin] View all pending payout requests")
@admin_only()
async def payouts(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    db       = _load_payout_db()
    all_reqs = db.get("payoutRequests", [])
    pending  = [r for r in all_reqs if r["status"] == "PENDING"]
    paid     = [r for r in all_reqs if r["status"] == "PAID"]

    if not all_reqs:
        await interaction.followup.send(
            view=cv2_info("Payout Requests", "No payout requests yet."), ephemeral=True)
        return

    kids = [_td("## Payout Requests"), _sep()]

    if pending:
        lines = []
        for r in pending[:10]:
            lines.append(
                f"**{r['discordUsername']}** — "
                f"**{r['validCount']:,}** tokens — "
                f"**${r['amountUsd']:.2f}** — "
                f"ID: `#{r['id']}` — {r['createdAt'][:10]}\n"
                f"╰ `{r.get('payoutMethod','—')}`"
            )
        kids.append(_td(f"** Pending ({len(pending)})**\n" + "\n".join(lines)))

    if paid:
        paid_lines = []
        for r in paid[-5:]:
            paid_lines.append(
                f"**{r['discordUsername']}** — "
                f"${r['amountUsd']:.2f} — "
                f"ID: `#{r['id']}`"
            )
        kids.append(_td(f"** Recently Paid ({len(paid)})**\n" + "\n".join(paid_lines)))

    kids.append(_td("-# Use /mark-paid <id> to mark a request as paid  ·  SkyHighEV"))
    await interaction.followup.send(view=_cv2(C_BRAND, *kids), ephemeral=True)


# ── /payout-history ───────────────────────────────────────────────────────────

@bot.tree.command(name="payout-history", description="[Admin] View full payout history for a worker or all workers")
@app_commands.describe(worker="Discord user to filter by (leave empty = all workers)")
@admin_only()
async def payout_history(interaction: discord.Interaction, worker: discord.Member = None):
    await interaction.response.defer(ephemeral=True)

    db       = _load_payout_db()
    all_reqs = db.get("payoutRequests", [])

    if worker:
        reqs  = [r for r in all_reqs if r.get("discordId") == str(worker.id)]
        title = f"Payout History  —  {worker.display_name}"
        icon  = worker.display_avatar.url
    else:
        reqs  = list(all_reqs)
        title = "Payout History  —  All Workers"
        icon  = None

    if not reqs:
        msg = "No payout requests found for this worker." if worker else "No payout requests on record yet."
        await interaction.followup.send(view=cv2_info(title, msg), ephemeral=True)
        return

    # sort newest first
    reqs_sorted   = sorted(reqs, key=lambda r: r.get("createdAt", ""), reverse=True)
    paid_reqs     = [r for r in reqs_sorted if r.get("status") == "PAID"]
    pending_reqs  = [r for r in reqs_sorted if r.get("status") == "PENDING"]
    rejected_reqs = [r for r in reqs_sorted if r.get("status") not in ("PAID", "PENDING")]

    total_paid_usd    = sum(r.get("amountUsd", 0)    for r in paid_reqs)
    total_paid_tokens = sum(r.get("validCount", 0)   for r in paid_reqs)
    total_pending_usd = sum(r.get("amountUsd", 0)    for r in pending_reqs)
    price_per         = db.get("tokenPrice", 0)

    kids = [
        _td(f"## {title}"),
        _sep(),
        _td(
            f"**Total Paid Out:** `${total_paid_usd:.2f}` ({total_paid_tokens:,} tokens)  ·  "
            f"**Pending:** `${total_pending_usd:.2f}` ({len(pending_reqs)} request(s))  ·  "
            f"**All Requests:** `{len(reqs)}` total @ ${price_per:.3f}/token"
        ),
    ]

    if pending_reqs:
        lines = []
        for r in pending_reqs[:6]:
            method_disp = str(r.get("payoutMethod", "—"))[:45]
            lines.append(
                f"`#{r['id']:03d}` **{r['discordUsername']}**  —  "
                f"**{r.get('validCount',0):,}** tokens  —  **${r.get('amountUsd',0):.2f}**\n"
                f"╰ Requested: {r.get('createdAt','—')[:10]}  ·  `{method_disp}`"
            )
        if len(pending_reqs) > 6:
            lines.append(f"*… and {len(pending_reqs) - 6} more*")
        kids.append(_td(f"** Pending ({len(pending_reqs)})**\n" + "\n".join(lines)))

    if paid_reqs:
        lines = []
        for r in paid_reqs[:10]:
            paid_at     = (r.get("paidAt") or "—")[:10]
            method_disp = str(r.get("payoutMethod", "—"))[:40]
            lines.append(
                f"`#{r['id']:03d}` **{r['discordUsername']}**  —  "
                f"**{r.get('validCount',0):,}** tokens  —  **${r.get('amountUsd',0):.2f}**\n"
                f"╰ Paid: {paid_at}  ·  `{method_disp}`"
            )
        if len(paid_reqs) > 10:
            lines.append(f"*… and {len(paid_reqs) - 10} more paid entries*")
        kids.append(_td(f"** Paid ({len(paid_reqs)})  —  ${total_paid_usd:.2f} total**\n" + "\n".join(lines)))

    if rejected_reqs:
        lines = []
        for r in rejected_reqs[:5]:
            lines.append(
                f"`#{r['id']:03d}` **{r['discordUsername']}**  —  "
                f"**${r.get('amountUsd',0):.2f}**  —  status: `{r.get('status','?')}`"
            )
        kids.append(_td(f"** Other ({len(rejected_reqs)})**\n" + "\n".join(lines)))

    kids.append(_td(f"-# Showing {len(reqs)} request(s)  ·  SkyHighEV"))
    await interaction.followup.send(view=_cv2(C_BRAND, *kids), ephemeral=True)


# ── /mark-paid ────────────────────────────────────────────────────────────────

@bot.tree.command(name="mark-paid", description="[Admin] Mark a payout request as paid")
@app_commands.describe(request_id="The payout request ID shown in /payouts")
@admin_only()
async def mark_paid(interaction: discord.Interaction, request_id: int):
    await interaction.response.defer(ephemeral=True)

    db  = _load_payout_db()
    req = next((r for r in db.get("payoutRequests", []) if r["id"] == request_id), None)

    if not req:
        await interaction.followup.send(
            view=cv2_err("Not Found", f"No payout request with ID `#{request_id}` exists."), ephemeral=True)
        return
    if req["status"] == "PAID":
        await interaction.followup.send(
            view=cv2_err("Already Paid", f"Request `#{request_id}` is already marked as paid."), ephemeral=True)
        return

    req["status"] = "PAID"
    req["paidAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _save_payout_db(db)

    # ── Confirm to admin ──
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##   Payout Marked as Paid"),
        _sep(),
        _td(
            f"**Worker:** {req['discordUsername']}  ·  "
            f"**Amount:** `${req['amountUsd']:.2f}`  ·  "
            f"**Tokens:** `{req['validCount']:,}`\n"
            f"**Method:**\n```{req['payoutMethod']}```"
        ),
        _td(f"-# Request ID: #{request_id}  ·  SkyHighEV"),
    ), ephemeral=True)

    # ── DM the worker (keep as embed — DMs excluded from CV2 conversion) ──
    try:
        worker_user = await bot.fetch_user(int(req["discordId"]))
        dm = base_embed(" You've Been Paid!", "", C_SUCCESS)
        dm.description = (
            f"Your payout request has been processed by the SkyHighEV admin team. "
            f"Check your **{req['payoutMethod'].split(':')[0].strip()}** for the payment."
        )
        dm.add_field(name=" Valid Tokens", value=f"**{req['validCount']:,}**",     inline=True)
        dm.add_field(name=" Amount Paid",  value=f"**${req['amountUsd']:.2f}**",   inline=True)
        dm.add_field(name=" Rate",         value=f"**${req['pricePerToken']:.4f}**/token", inline=True)
        dm.add_field(name="Paid To",         value=f"```{req['payoutMethod']}```",   inline=False)
        dm.add_field(name="Paid At",         value=req["paidAt"],                    inline=True)
        dm.set_footer(text=f"Request ID: #{request_id}  |  SkyHighEV — Thank you for your work!")
        await worker_user.send(embed=dm)
    except Exception as dm_err:
        print(f"[PAYOUT] Could not DM worker {req['discordId']}: {dm_err}")


# ══════════════════════════════════════════════════════════════════════════════
#  SUSPENSION SYSTEM  —  local JSON storage
# ══════════════════════════════════════════════════════════════════════════════

SUSPENSION_FILE = "suspension_data.json"

def _load_suspensions() -> dict:
    if os.path.exists(SUSPENSION_FILE):
        try:
            with open(SUSPENSION_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"suspended": {}}

def _save_suspensions(db: dict):
    with open(SUSPENSION_FILE, "w") as f:
        json.dump(db, f, indent=2)

def _is_suspended(discord_id: str) -> dict | None:
    """Return suspension record if still active, else None."""
    db  = _load_suspensions()
    rec = db["suspended"].get(str(discord_id))
    if not rec:
        return None
    if rec.get("until"):
        until_dt = datetime.fromisoformat(rec["until"])
        if datetime.now(timezone.utc) >= until_dt:
            # auto-lift expired suspension
            del db["suspended"][str(discord_id)]
            _save_suspensions(db)
            return None
    return rec


@bot.tree.command(name="suspend-worker", description="[Admin] Suspend a worker from payouts (optionally with expiry)")
@app_commands.describe(
    user="The worker to suspend",
    reason="Reason for suspension (shown to the worker)",
    hours="Duration in hours (0 = permanent)",
)
@admin_only()
async def suspend_worker(interaction: discord.Interaction, user: discord.Member, reason: str, hours: int = 0):
    await interaction.response.defer(ephemeral=True)

    until_str = None
    until_dt  = None
    if hours > 0:
        until_dt  = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
        until_str = until_dt.isoformat()

    db = _load_suspensions()
    db["suspended"][str(user.id)] = {
        "discordId":       str(user.id),
        "discordUsername": user.name,
        "reason":          reason,
        "until":           until_str,
        "suspendedBy":     str(interaction.user.id),
        "suspendedAt":     datetime.now(timezone.utc).isoformat(),
    }
    _save_suspensions(db)

    dur_text = f"{hours}h" if hours > 0 else "Permanent"
    lifts_str = f"\n**Lifts At:** <t:{int(until_dt.timestamp())}:F>" if until_dt else ""
    await interaction.followup.send(view=_cv2(C_ERROR,
        _td("##   Worker Suspended"),
        _sep(),
        _td(
            f"**Worker:** {user.mention}  ·  **Duration:** `{dur_text}`\n"
            f"**Reason:** > {reason}"
            + lifts_str
        ),
        _td("-# SkyHighEV"),
    ), ephemeral=True)

    try:
        dm = base_embed("  You Have Been Suspended", "", C_ERROR)
        dm.description = (
            f"You have been suspended from SkyHighEV payouts by an admin.\n\n"
            f"**Reason:** {reason}\n"
            f"**Duration:** {dur_text}"
        )
        if until_dt:
            dm.add_field(name="Your suspension lifts", value=f"<t:{int(until_dt.timestamp())}:F>", inline=False)
        dm.set_footer(text="Contact an admin if you believe this is a mistake  ·  SkyHighEV")
        await user.send(embed=dm)
    except Exception:
        pass


@bot.tree.command(name="unsuspend-worker", description="[Admin] Lift a worker's suspension")
@app_commands.describe(user="The worker to unsuspend")
@admin_only()
async def unsuspend_worker(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    db  = _load_suspensions()
    rec = db["suspended"].pop(str(user.id), None)
    _save_suspensions(db)

    if not rec:
        await interaction.followup.send(
            view=cv2_warn("Not Suspended", f"{user.mention} is not currently suspended."), ephemeral=True)
        return

    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##   Suspension Lifted"),
        _sep(),
        _td(f"**Worker:** {user.mention}  ·  **Previous Reason:** {rec.get('reason', '—')}"),
        _td("-# SkyHighEV"),
    ), ephemeral=True)

    try:
        dm = base_embed("  Suspension Lifted", "", C_SUCCESS)
        dm.description = "Your suspension has been lifted. You can request payouts again."
        dm.set_footer(text="SkyHighEV  ·  Worker System")
        await user.send(embed=dm)
    except Exception:
        pass


@bot.tree.command(name="suspensions", description="[Admin] List all currently suspended workers")
@admin_only()
async def list_suspensions(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    db      = _load_suspensions()
    records = list(db["suspended"].values())

    # Auto-prune expired
    now = datetime.now(timezone.utc)
    active = []
    for r in records:
        if r.get("until"):
            try:
                if datetime.fromisoformat(r["until"]) > now:
                    active.append(r)
            except Exception:
                active.append(r)
        else:
            active.append(r)

    if not active:
        await interaction.followup.send(
            view=cv2_info("Suspensions", "No workers are currently suspended."), ephemeral=True)
        return

    lines = []
    for r in active:
        dur = f"until <t:{int(datetime.fromisoformat(r['until']).timestamp())}:R>" if r.get("until") else "**Permanent**"
        lines.append(f"**{r['discordUsername']}** (`{r['discordId']}`) — {dur}\n> {r.get('reason','—')}")

    await interaction.followup.send(view=_cv2(C_ERROR,
        _td(f"##   Active Suspensions  ({len(active)})"),
        _sep(),
        _td("\n\n".join(lines)),
        _td("-# SkyHighEV"),
    ), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAYOUT FRAUD DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _check_payout_fraud(discord_id: str, valid_tokens: list, db: dict) -> list[str]:
    """
    Cross-check valid tokens against all previously PAID payout batches.
    Returns a list of fraud warning strings (empty = clean).
    """
    warnings = []
    paid_requests = [r for r in db.get("payoutRequests", []) if r["status"] == "PAID"]

    # Build a set of token strings from past paid batches (if stored)
    paid_token_sets = {}
    for r in paid_requests:
        stored = r.get("tokens", [])
        if stored:
            paid_token_sets[r["id"]] = set(stored)

    # Check if this worker already has a paid request with overlapping tokens
    current_token_set = set(valid_tokens)
    for req_id, token_set in paid_token_sets.items():
        overlap = current_token_set & token_set
        if overlap:
            warnings.append(
                f" **{len(overlap)} token(s) already paid** in request `#{req_id}` — possible duplicate submission"
            )

    # Check for workers submitting tokens that were already paid to ANOTHER worker
    for req in paid_requests:
        stored = req.get("tokens", [])
        if not stored or req["discordId"] == discord_id:
            continue
        overlap = current_token_set & set(stored)
        if overlap:
            warnings.append(
                f" **{len(overlap)} token(s) belong to another worker** (prev paid to `{req['discordUsername']}` in `#{req['id']}`)"
            )

    return warnings


# ══════════════════════════════════════════════════════════════════════════════
#  TICKET SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

class TicketCloseLayout(discord.ui.LayoutView):
    """Posted after a ticket is closed — shows closed status and Delete button for admins."""

    def __init__(self, closed_by: str = ""):
        super().__init__(timeout=None)
        info = (
            f"Closed by {closed_by}. Admins can still read and delete this channel."
            if closed_by
            else "This ticket has been closed. Admins can still read and delete this channel."
        )
        delete_btn = discord.ui.Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:delete_closed",
        )
        delete_btn.callback = self._delete_ticket
        self.add_item(_cv2_cont(
            _td("## Ticket Closed"),
            _sep(),
            _td(info),
            _td("-# SkyHighEV Support System"),
            discord.ui.ActionRow(delete_btn),
            color=C_WARN,
        ))

    async def _delete_ticket(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Only admins can delete tickets.", ephemeral=True)
            return
        await interaction.response.send_message("Deleting in 3 seconds...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception:
            pass


class TicketControlLayout(discord.ui.LayoutView):
    """Sent inside an open ticket — welcome message with Close and Delete buttons."""

    def __init__(self, mention: str = ""):
        super().__init__(timeout=None)
        close_btn = discord.ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket:close",
        )
        close_btn.callback = self._close_ticket
        delete_btn = discord.ui.Button(
            label="Delete Ticket",
            style=discord.ButtonStyle.danger,
            custom_id="ticket:delete",
        )
        delete_btn.callback = self._delete_ticket
        greeting = f"{mention} \u2014 " if mention else ""
        self.add_item(_cv2_cont(
            _td("## Support Ticket"),
            _sep(),
            _td(
                f"{greeting}A staff member will be with you shortly.\n"
                "Please describe your issue clearly and we will help as soon as possible."
            ),
            _sep(),
            _td("Click **Close Ticket** when your issue is resolved."),
            _sep(),
            _td("-# SkyHighEV Support System"),
            discord.ui.ActionRow(close_btn, delete_btn),
            color=C_BRAND,
        ))

    async def _close_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("Must be used inside a ticket channel.", ephemeral=True)
            return

        overwrites = ch.overwrites
        for target, overwrite in overwrites.items():
            if isinstance(target, discord.Member) and target.id not in ADMIN_IDS and target.id != bot.user.id:
                overwrite.send_messages = False
                overwrites[target] = overwrite

        try:
            new_name = ch.name if ch.name.startswith("closed-") else f"closed-{ch.name}"
            await ch.edit(name=new_name, overwrites=overwrites)
        except Exception:
            pass

        await ch.send(view=TicketCloseLayout(closed_by=str(interaction.user.mention)))
        await interaction.followup.send("Ticket closed.", ephemeral=True)

    async def _delete_ticket(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Only admins can delete tickets.", ephemeral=True)
            return
        await interaction.response.send_message("Deleting in 3 seconds...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception:
            pass


class TicketPanelLayout(discord.ui.LayoutView):
    """Persistent public panel — anyone clicks to open a ticket."""

    def __init__(self):
        super().__init__(timeout=None)
        create_btn = discord.ui.Button(
            label="Create Ticket",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_panel:create",
        )
        create_btn.callback = self._create_ticket
        self.add_item(_cv2_cont(
            _td("## Support Tickets"),
            _sep(),
            _td(
                "Need help or have a question? Open a private support ticket and "
                "a staff member will assist you.\n\n"
                "Click the button below to get started."
            ),
            _td("-# SkyHighEV Support System  |  One ticket per user at a time"),
            discord.ui.ActionRow(create_btn),
            color=C_BRAND,
        ))

    async def _create_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Must be used in a server.", ephemeral=True)
            return

        user_tag = interaction.user.name.lower()[:12].replace(" ", "_")
        ticket_prefix = f"ticket-{user_tag}"

        for ch in guild.channels:
            if isinstance(ch, discord.TextChannel) and ch.name.startswith(ticket_prefix):
                await interaction.followup.send(
                    view=cv2_err("Ticket Exists", f"You already have an open ticket: {ch.mention}"),
                    ephemeral=True)
                return

        category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
        ticket_name = f"{ticket_prefix}-{interaction.user.id % 10000:04d}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            interaction.user:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for admin_id in ADMIN_IDS:
            m = guild.get_member(admin_id)
            if m:
                overwrites[m] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)

        try:
            channel = await guild.create_text_channel(
                ticket_name,
                category=category,
                overwrites=overwrites,
                topic=f"Support ticket for {interaction.user} | {interaction.user.id}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                view=cv2_err("Missing Permissions", "I don't have permission to create channels."),
                ephemeral=True)
            return

        await channel.send(view=TicketControlLayout(mention=interaction.user.mention))
        await interaction.followup.send(
            view=cv2_ok("Ticket Created", f"Your ticket is ready: {channel.mention}"), ephemeral=True)


# ── /setup-ticket-panel ───────────────────────────────────────────────────────

@bot.tree.command(name="setup-ticket-panel", description="[Admin] Post the support ticket panel in this channel")
@admin_only()
async def setup_ticket_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(view=TicketPanelLayout())
    await interaction.followup.send(
        view=cv2_ok("Panel Posted", "Support ticket panel sent to this channel."), ephemeral=True)


# ── /ticket-transcript ────────────────────────────────────────────────────────

@bot.tree.command(name="ticket-transcript", description="[Admin] Export a transcript of this ticket channel")
@admin_only()
async def ticket_transcript(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    ch = interaction.channel
    if not isinstance(ch, discord.TextChannel):
        await interaction.followup.send(
            view=cv2_err("Wrong Channel", "Run this inside a ticket channel."), ephemeral=True)
        return

    if not (ch.name.startswith("ticket-") or ch.name.startswith("closed-ticket-")):
        await interaction.followup.send(
            view=cv2_err("Not a Ticket", "This channel doesn't look like a ticket."), ephemeral=True)
        return

    lines = []
    async for msg in ch.history(limit=1000, oldest_first=True):
        ts   = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        body = msg.content or ""
        for emb in msg.embeds:
            if emb.title:        body += f" [Embed: {emb.title}]"
            if emb.description:  body += f" — {emb.description[:120]}"
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {body}")

    if not lines:
        await interaction.followup.send(
            view=cv2_err("Empty", "No messages found in this channel."), ephemeral=True)
        return

    transcript_text = f"Ticket Transcript — #{ch.name}\n{'='*60}\n" + "\n".join(lines)
    file = discord.File(
        fp=io.BytesIO(transcript_text.encode()),
        filename=f"transcript-{ch.name}.txt",
    )
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Transcript Ready"),
        _sep(),
        _td(f"`{ch.name}` — **{len(lines)}** messages exported"),
        _td("-# SkyHighEV Support System"),
    ), file=file, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ECONOMY SYSTEM  —  Coins, Games, Robbery, Withdrawals
# ══════════════════════════════════════════════════════════════════════════════

ECONOMY_FILE = "economy_data.json"

# In-memory cooldown dicts (reset on restart, which is fine)
_rob_cooldowns: dict  = {}   # discord_id -> datetime when cooldown expires
_work_cooldowns: dict = {}   # discord_id -> datetime when cooldown expires

# ── Economy Data Helpers ──────────────────────────────────────────────────────

def _load_economy() -> dict:
    if os.path.exists(ECONOMY_FILE):
        try:
            with open(ECONOMY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "balances": {},
        "daily": {},
        "streaks": {},
        "rob_protection": {},
        "coin_rate": 1000,
        "withdrawals": [],
        "next_withdrawal_id": 1,
    }

def _save_economy(db: dict):
    with open(ECONOMY_FILE, "w") as f:
        json.dump(db, f, indent=2)

def _get_balance(discord_id, db: dict) -> int:
    return db["balances"].get(str(discord_id), 0)

def _add_coins(discord_id, amount: int, db: dict):
    sid = str(discord_id)
    db["balances"][sid] = db["balances"].get(sid, 0) + amount

def _deduct_coins(discord_id, amount: int, db: dict) -> bool:
    sid = str(discord_id)
    bal = db["balances"].get(sid, 0)
    if bal < amount:
        return False
    db["balances"][sid] = bal - amount
    return True

def _has_rob_protection(discord_id, db: dict) -> bool:
    sid = str(discord_id)
    rec = db.get("rob_protection", {}).get(sid)
    if not rec:
        return False
    try:
        expires = datetime.fromisoformat(rec["expires"])
        if datetime.now(timezone.utc) < expires:
            return True
        del db["rob_protection"][sid]
    except Exception:
        pass
    return False

def _fmt_coins(n: int) -> str:
    return f"**{n:,}** "

_MINES_RISK_BONUS = {
    "low":     1.00,
    "medium":  1.20,
    "high":    1.50,
    "extreme": 2.00,
}

def _mines_multiplier(total: int, mines: int, revealed: int, risk: str = "medium") -> float:
    if revealed == 0:
        return 1.0
    prob = 1.0
    for i in range(revealed):
        prob *= (total - mines - i) / (total - i)
    if prob <= 0:
        return 0.0
    bonus = _MINES_RISK_BONUS.get(risk, 1.0)
    return round((0.97 / prob) * bonus, 2)

# ── /balance ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="balance", description="Check your coin balance (or another user's)")
@app_commands.describe(user="The user to check (leave blank for yourself)")
async def balance_cmd(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    target = user or interaction.user
    db = _load_economy()
    bal = _get_balance(target.id, db)
    own = target.id == interaction.user.id
    who = "Your" if own else f"{target.display_name}'s"
    kids = [
        _td(f"## {who} Wallet"),
        _sep(),
        _td(f"**Balance:** {bal:,} "),
    ]
    if own and _has_rob_protection(target.id, db):
        rec = db.get("rob_protection", {}).get(str(target.id), {})
        if rec.get("expires"):
            exp_ts = int(datetime.fromisoformat(rec["expires"]).timestamp())
            kids.append(_td(f" Rob Protection active until <t:{exp_ts}:R>"))
    kids.append(_td(f"-# Earn more coins with !daily, !work, and !mines"))
    await interaction.followup.send(
        view=_cv2(C_GOLD, *kids), ephemeral=True)

# ── /daily ────────────────────────────────────────────────────────────────────

@bot.tree.command(name="daily", description="Claim your daily coin reward (resets at midnight UTC)")
async def daily_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    db = _load_economy()
    sid = str(interaction.user.id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_claimed = db.get("daily", {}).get(sid)

    if last_claimed == today:
        tomorrow = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1))
        await interaction.followup.send(
            view=cv2_err("Already Claimed",
                         f"You already claimed your daily reward today.\nCome back <t:{int(tomorrow.timestamp())}:R>!"), ephemeral=True)
        return

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = db.get("streaks", {}).get(sid, 0)
    streak = streak + 1 if last_claimed == yesterday else 1
    db.setdefault("streaks", {})[sid] = streak

    base_reward = _random.randint(500, 1500)
    streak_bonus = min(streak * 100, 1000)
    total = base_reward + streak_bonus
    _add_coins(interaction.user.id, total, db)
    db.setdefault("daily", {})[sid] = today
    _save_economy(db)
    new_bal = _get_balance(interaction.user.id, db)

    streak_line = f" **{streak}-day streak!** Keep it up!" if streak >= 7 else f"Streak: **{streak}/7** days"
    kids = [
        _td("## Daily Reward Claimed!"),
        _sep(),
        _td(streak_line),
        _sep(),
        _td(f"**Base Reward:** {base_reward:,} "),
    ]
    if streak_bonus > 0:
        kids.append(_td(f"**Streak Bonus (Day {streak}):** +{streak_bonus:,} "))
    kids.append(_td(f"**Total Earned:** **{total:,}** "))
    kids.append(_td(f"**New Balance:** {new_bal:,} "))
    await interaction.followup.send(view=_cv2(C_SUCCESS, *kids))

# ── /work ─────────────────────────────────────────────────────────────────────

_WORK_JOBS = [
    (" fixed some bugs",          100, 350),
    (" delivered packages",        80,  260),
    (" delivered pizzas",          90,  300),
    (" drove for a rideshare",     100, 280),
    (" wrote some code",           150, 450),
    (" filed expense reports",     70,  220),
    (" mowed some lawns",          90,  250),
    ("☕ served coffee",             60,  190),
    (" busked on the street",      50,  380),
    (" cleaned offices overnight", 80,  230),
    (" tested video games",        120, 400),
    (" took event photos",         100, 350),
    (" washed a yacht",            200, 500),
    (" stocked a pharmacy",        90,  270),
    (" hauled construction waste", 130, 380),
]

WORK_COOLDOWN_SECONDS = 3600

@bot.tree.command(name="work", description="Do some work to earn coins! (1-hour cooldown)")
async def work_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    sid = str(interaction.user.id)
    now = datetime.now(timezone.utc)
    cd = _work_cooldowns.get(sid)
    if cd and now < cd:
        await interaction.followup.send(
            view=cv2_err("On Break", f"You're resting. Come back <t:{int(cd.timestamp())}:R>."), ephemeral=True)
        return
    job_desc, min_pay, max_pay = _random.choice(_WORK_JOBS)
    earned = _random.randint(min_pay, max_pay)
    _work_cooldowns[sid] = now + timedelta(seconds=WORK_COOLDOWN_SECONDS)
    db = _load_economy()
    _add_coins(interaction.user.id, earned, db)
    _save_economy(db)
    new_bal = _get_balance(interaction.user.id, db)
    next_ts = int(_work_cooldowns[sid].timestamp())
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("## Work Complete!"),
        _sep(),
        _td(f"You {job_desc} and earned **{earned:,}** !"),
        _sep(),
        _td(f"**Earned:** +{earned:,} coins"),
        _td(f"**New Balance:** {new_bal:,} "),
        _td(f"**Next Shift:** <t:{next_ts}:R>"),
    ))

# ── MINES GAME ────────────────────────────────────────────────────────────────

_MINES_GRID = {
    "3x3": (3, 3),
    "4x4": (4, 4),
    "5x4": (4, 5),
    "5x5": (5, 5),
}
_MINES_RISK = {
    "low":     {"3x3": 1, "4x4": 2,  "5x4": 3,  "5x5": 4},
    "medium":  {"3x3": 3, "4x4": 5,  "5x4": 7,  "5x5": 9},
    "high":    {"3x3": 5, "4x4": 8,  "5x4": 11, "5x5": 14},
    "extreme": {"3x3": 6, "4x4": 11, "5x4": 15, "5x5": 19},
}


class MinesConfigLayout(discord.ui.LayoutView):
    GRIDS   = ["3x3", "4x4", "5x4", "5x5"]
    GLABELS = {
        "3x3": "Small (3x3)",
        "4x4": "Medium (4x4)",
        "5x4": "Large (5x4)",
        "5x5": "Extra Large (5x5)",
    }
    GDESCS = {
        "3x3": "9 tiles total",
        "4x4": "16 tiles total",
        "5x4": "20 tiles total",
        "5x5": "25 tiles total",
    }
    RISKS   = ["low", "medium", "high", "extreme"]
    RLABELS = {
        "low":     "Low Risk",
        "medium":  "Medium Risk",
        "high":    "High Risk",
        "extreme": "Extreme Risk",
    }
    RDESCS = {
        "low":     "Very few mines — safer payouts",
        "medium":  "Balanced mines and rewards",
        "high":    "Many mines — higher multipliers",
        "extreme": "Maximum mines — massive payouts",
    }

    def __init__(self, author_id: int, bet: int, balance: int,
                 grid: str = "4x4", risk: str = "medium"):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.bet       = bet
        self.balance   = balance
        self.grid      = grid
        self.risk      = risk
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        rows_n, cols_n = _MINES_GRID[self.grid]
        total       = rows_n * cols_n
        mines_count = _MINES_RISK[self.risk][self.grid]

        grid_select = discord.ui.Select(
            custom_id="mcfg_grid",
            placeholder="Choose grid size...",
            options=[
                discord.SelectOption(
                    label=self.GLABELS[g],
                    description=self.GDESCS[g],
                    value=g,
                    default=(g == self.grid),
                )
                for g in self.GRIDS
            ],
        )
        grid_select.callback = self._grid_changed

        risk_select = discord.ui.Select(
            custom_id="mcfg_risk",
            placeholder="Choose risk level...",
            options=[
                discord.SelectOption(
                    label=self.RLABELS[r],
                    description=self.RDESCS[r],
                    value=r,
                    default=(r == self.risk),
                )
                for r in self.RISKS
            ],
        )
        risk_select.callback = self._risk_changed

        start_btn = discord.ui.Button(
            label="Start Game", style=discord.ButtonStyle.success, custom_id="mcfg_start")
        start_btn.callback = self._start

        cancel_btn = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.danger, custom_id="mcfg_cancel")
        cancel_btn.callback = self._cancel

        grid_label = self.GLABELS[self.grid]
        risk_label = self.RLABELS[self.risk].replace(" Risk", "")

        self.add_item(_cv2_cont(
            _td("## Mines \u2014 Configuration"),
            _sep(),
            _td(
                f"**Current Settings:**\n"
                f"\u2022 Grid Size: {grid_label}\n"
                f"\u2022 Risk: {risk_label}\n"
                f"\u2022 Mines: **{mines_count}** of **{total}** tiles "
                f"(**{int(mines_count*100/total)}%** mine density)\n"
                f"\u2022 Safe Tiles: **{total - mines_count}**\n"
                f"\u2022 First-Click Safe Chance: **{int((total-mines_count)*100/total)}%**\n"
                f"\u2022 Risk Payout Bonus: **x{_MINES_RISK_BONUS[self.risk]:.2f}** "
                f"(higher risk = bigger multiplier per safe click)"
            ),
            _sep(),
            _td(f"**Your Balance:** {self.balance:,} \U0001fa99  \u00b7  **Bet:** {self.bet:,} \U0001fa99"),
            _sep(),
            _td("-# Provably fair: mines are placed once at game start using `random.sample()` and never moved. Select your grid size and risk level, then press Start."),
            discord.ui.ActionRow(grid_select),
            discord.ui.ActionRow(risk_select),
            discord.ui.ActionRow(start_btn, cancel_btn),
            color=C_BRAND,
        ))

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    async def _grid_changed(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        self.grid = interaction.data["values"][0]
        self._rebuild()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def _risk_changed(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        self.risk = interaction.data["values"][0]
        self._rebuild()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def _cancel(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        self.stop()
        await interaction.response.edit_message(
            content=None, embeds=[], attachments=[],
            view=cv2_warn("Mines Cancelled", "No coins were deducted."))

    async def _start(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        db = _load_economy()
        if not _deduct_coins(self.author_id, self.bet, db):
            bal = _get_balance(self.author_id, db)
            await interaction.response.send_message(
                f"Insufficient funds — need {self.bet:,} coins but you only have {bal:,} coins.",
                ephemeral=True)
            return
        _save_economy(db)
        rows_n, cols_n = _MINES_GRID[self.grid]
        total       = rows_n * cols_n
        mines_count = _MINES_RISK[self.risk][self.grid]
        mines       = set(_random.sample(range(total), mines_count))
        game = {
            "bet": self.bet, "rows": rows_n, "cols": cols_n,
            "total_cells": total, "mine_count": mines_count,
            "risk": self.risk,
            "mines": mines, "revealed": set(),
            "current_mult": 1.0, "over": False, "result": None, "new_bal": 0,
        }
        self.stop()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=MinesGameLayout(game, self.author_id))


class MinesGameLayout(discord.ui.LayoutView):
    def __init__(self, game: dict, player_id: int):
        super().__init__(timeout=300)
        self.game      = game
        self.player_id = player_id
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        game    = self.game
        rows_n  = game["rows"]
        cols_n  = game["cols"]
        revealed = game["revealed"]
        mines   = game["mines"]
        over    = game["over"]
        result  = game.get("result")
        mult    = game["current_mult"]
        bet     = game["bet"]
        potential = int(bet * mult)

        if result == "cashout":
            title, color = "## Cashed Out!", C_SUCCESS
        elif result == "boom":
            title, color = "## BOOM! You Hit a Mine!", C_ERROR
        elif result == "cleared":
            title, color = "## Minefield Cleared!", C_SUCCESS
        else:
            title, color = "## Mines", C_BRAND

        grid_rows = []
        for r in range(rows_n):
            buttons = []
            for c in range(cols_n):
                idx = r * cols_n + c
                if idx in revealed:
                    btn = discord.ui.Button(
                        label="\u2b50", style=discord.ButtonStyle.success,
                        disabled=True, custom_id=f"mg_{idx}")
                elif over and idx in mines:
                    btn = discord.ui.Button(
                        label="\U0001f4a3", style=discord.ButtonStyle.danger,
                        disabled=True, custom_id=f"mg_{idx}")
                else:
                    btn = discord.ui.Button(
                        label="?", style=discord.ButtonStyle.secondary,
                        disabled=over, custom_id=f"mg_{idx}")
                    if not over:
                        btn.callback = self._make_tile(idx)
                buttons.append(btn)
            grid_rows.append(discord.ui.ActionRow(*buttons))

        cont_items = [_td(title), _sep()] + grid_rows

        if result == "cashout":
            new_bal = game.get("new_bal", 0)
            cont_items += [_sep(), _td(
                f" **Cashed Out!**\n\n"
                f"**Tiles Revealed:** {len(revealed)}\n"
                f"**Multiplier:** x{mult}\n"
                f"**Winnings:** +{potential:,} \n"
                f"**New Balance:** {new_bal:,} "
            )]
        elif result == "boom":
            cont_items += [_sep(), _td(
                f" **You hit a mine!**\n\n"
                f"**Bet Lost:** {bet:,} \n"
                f"**Tiles Revealed:** {len(revealed)}\n"
                f"**Mines in Grid:** {game['mine_count']}"
            )]
        elif result == "cleared":
            new_bal = game.get("new_bal", 0)
            cont_items += [_sep(), _td(
                f" **All safe tiles revealed!**\n\n"
                f"**Multiplier:** x{mult}\n"
                f"**Winnings:** +{potential:,} \n"
                f"**New Balance:** {new_bal:,} "
            )]
        self.add_item(_cv2_cont(*cont_items, color=color))

        if not over:
            cashout_lbl = f"Cash Out \u2014 {potential:,} \U0001fa99  (x{mult})"
            co_btn = discord.ui.Button(
                label=cashout_lbl, style=discord.ButtonStyle.success,
                custom_id="mg_cashout", disabled=len(revealed) == 0)
            co_btn.callback = self._cashout
            self.add_item(discord.ui.ActionRow(co_btn))

    def _make_tile(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                await interaction.response.send_message("This isn't your game!", ephemeral=True)
                return
            game = self.game
            if game["over"] or idx in game["revealed"]:
                await interaction.response.defer()
                return
            if idx in game["mines"]:
                game["over"]   = True
                game["result"] = "boom"
                self._rebuild()
                await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)
            else:
                game["revealed"].add(idx)
                rev  = len(game["revealed"])
                mult = _mines_multiplier(game["total_cells"], game["mine_count"], rev, game.get("risk", "medium"))
                game["current_mult"] = mult
                if rev >= game["total_cells"] - game["mine_count"]:
                    game["over"]   = True
                    game["result"] = "cleared"
                    winnings = int(game["bet"] * mult)
                    db = _load_economy()
                    _add_coins(interaction.user.id, winnings, db)
                    game["new_bal"] = _get_balance(interaction.user.id, db)
                    _save_economy(db)
                self._rebuild()
                await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)
        return callback

    async def _cashout(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        game = self.game
        if game["over"] or not game["revealed"]:
            await interaction.response.defer()
            return
        game["over"]   = True
        game["result"] = "cashout"
        winnings = int(game["bet"] * game["current_mult"])
        db = _load_economy()
        _add_coins(interaction.user.id, winnings, db)
        game["new_bal"] = _get_balance(interaction.user.id, db)
        _save_economy(db)
        self._rebuild()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)


@bot.tree.command(name="mines", description="Reveal tiles without hitting a mine — cash out anytime!")
@app_commands.describe(
    bet="Coins to bet",
    grid="Grid size",
    risk="Risk level (affects mine count and rewards)",
)
@app_commands.choices(
    grid=[
        app_commands.Choice(name="Small  3×3",        value="3x3"),
        app_commands.Choice(name="Medium 4×4",        value="4x4"),
        app_commands.Choice(name="Large  5×4",        value="5x4"),
        app_commands.Choice(name="XL     5×5",        value="5x5"),
    ],
    risk=[
        app_commands.Choice(name="Low     — very few mines, safer payouts",  value="low"),
        app_commands.Choice(name="Medium  — balanced mines and rewards",      value="medium"),
        app_commands.Choice(name="High    — many mines, higher multipliers",  value="high"),
        app_commands.Choice(name="Extreme — maximum mines, massive payouts",  value="extreme"),
    ],
)
async def mines_cmd(interaction: discord.Interaction, bet: int, grid: str = "4x4", risk: str = "medium"):
    await interaction.response.defer(ephemeral=False)
    if bet < 50:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Minimum bet is **50** ."), ephemeral=True)
        return
    if bet > 5_000:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Maximum bet is **5,000** ."), ephemeral=True)
        return
    db  = _load_economy()
    bal = _get_balance(interaction.user.id, db)
    if bal < bet:
        await interaction.followup.send(
            view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    config = MinesConfigLayout(interaction.user.id, bet, bal, grid, risk)
    await interaction.followup.send(view=config)

# ── BLACKJACK ─────────────────────────────────────────────────────────────────

_BJ_SUITS = ["♠", "♥", "♦", "♣"]
_BJ_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def _bj_new_deck() -> list:
    deck = [(r, s) for s in _BJ_SUITS for r in _BJ_RANKS]
    _random.shuffle(deck)
    return deck

def _bj_card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)

def _bj_hand_value(hand: list) -> int:
    total = sum(_bj_card_value(r) for r, _ in hand)
    aces  = sum(1 for r, _ in hand if r == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total

def _bj_fmt_hand(hand: list, hide_second: bool = False) -> str:
    if hide_second and len(hand) > 1:
        return f"`{hand[0][0]}{hand[0][1]}`  `🂠`"
    return "  ".join(f"`{r}{s}`" for r, s in hand)


class BlackjackLayout(discord.ui.LayoutView):
    _COLORS = {"win": C_SUCCESS, "blackjack": C_GOLD, "push": C_WARN, "lose": C_ERROR, "bust": C_ERROR}
    _TITLES = {
        "win":       "## Blackjack — You Win!",
        "blackjack": "## Blackjack — Natural 21!",
        "push":      "## Blackjack — Push",
        "lose":      "## Blackjack — Dealer Wins",
        "bust":      "## Blackjack — Bust!",
    }

    def __init__(self, bet: int, player_id: int, deck: list, player_hand: list, dealer_hand: list):
        super().__init__(timeout=120)
        self.bet         = bet
        self.player_id   = player_id
        self.deck        = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.done        = False
        self._rebuild()

    def _rebuild(self, reveal_dealer: bool = False, result: str = None):
        self.clear_items()
        pv    = _bj_hand_value(self.player_hand)
        dv    = _bj_hand_value(self.dealer_hand)
        color = self._COLORS.get(result, C_BRAND)
        title = self._TITLES.get(result, "## Blackjack")

        dealer_label = f"Dealer's Hand{f'  —  {dv}' if reveal_dealer else ''}"
        kids = [
            _td(title),
            _sep(),
            _td(f"**{dealer_label}**\n{_bj_fmt_hand(self.dealer_hand, hide_second=not reveal_dealer)}"),
            _sep(),
            _td(f"**Your Hand — {pv}**\n{_bj_fmt_hand(self.player_hand)}"),
            _sep(),
            _td(f"**Bet:**  {self.bet:,}"),
        ]
        if result == "win":
            kids.append(_td(f"**Won:** +{self.bet:,} "))
        elif result == "blackjack":
            kids.append(_td(f"**Won:** +{int(self.bet * 1.5):,} "))
        elif result == "push":
            kids.append(_td("**Result:** Bet returned"))
        elif result in ("lose", "bust"):
            kids.append(_td(f"**Lost:** -{self.bet:,} "))

        self.add_item(_cv2_cont(*kids, color=color))

        if not self.done:
            hit_btn = discord.ui.Button(
                label="Hit", style=discord.ButtonStyle.primary, custom_id="bj_hit")
            hit_btn.callback = self._hit
            stand_btn = discord.ui.Button(
                label="Stand", style=discord.ButtonStyle.secondary, custom_id="bj_stand")
            stand_btn.callback = self._stand
            dbl_btn = discord.ui.Button(
                label="Double Down", style=discord.ButtonStyle.success, custom_id="bj_double")
            dbl_btn.callback = self._double
            self.add_item(discord.ui.ActionRow(hit_btn, stand_btn, dbl_btn))

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        if self.done:
            await interaction.response.defer()
            return False
        return True

    async def _end_game(self, interaction: discord.Interaction, result: str, payout: int):
        self.done = True
        db = _load_economy()
        if payout > 0:
            _add_coins(interaction.user.id, payout, db)
        _save_economy(db)
        self._rebuild(reveal_dealer=True, result=result)
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def _dealer_play(self, interaction: discord.Interaction):
        while _bj_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        pv = _bj_hand_value(self.player_hand)
        dv = _bj_hand_value(self.dealer_hand)
        if dv > 21 or pv > dv:
            if pv == 21 and len(self.player_hand) == 2:
                await self._end_game(interaction, "blackjack", self.bet + int(self.bet * 1.5))
            else:
                await self._end_game(interaction, "win", self.bet * 2)
        elif pv == dv:
            await self._end_game(interaction, "push", self.bet)
        else:
            await self._end_game(interaction, "lose", 0)

    async def _hit(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        self.player_hand.append(self.deck.pop())
        pv = _bj_hand_value(self.player_hand)
        if pv > 21:
            await self._end_game(interaction, "bust", 0)
        elif pv == 21:
            await self._dealer_play(interaction)
        else:
            self._rebuild()
            await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def _stand(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        await self._dealer_play(interaction)

    async def _double(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        if len(self.player_hand) != 2:
            await interaction.response.send_message(
                "Can only double down on your initial 2 cards!", ephemeral=True)
            return
        db = _load_economy()
        if not _deduct_coins(interaction.user.id, self.bet, db):
            await interaction.response.send_message(
                f"Not enough coins! Need {self.bet:,}  more to double down.", ephemeral=True)
            return
        _save_economy(db)
        self.bet *= 2
        self.player_hand.append(self.deck.pop())
        if _bj_hand_value(self.player_hand) > 21:
            await self._end_game(interaction, "bust", 0)
        else:
            await self._dealer_play(interaction)


@bot.tree.command(name="blackjack", description="Play blackjack against the dealer!")
@app_commands.describe(bet="Amount of coins to bet")
async def blackjack_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.defer(ephemeral=False)
    if bet < 50:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Minimum bet is **50** ."), ephemeral=True)
        return
    if bet > 50_000:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Maximum bet is **50,000** ."), ephemeral=True)
        return
    db = _load_economy()
    if not _deduct_coins(interaction.user.id, bet, db):
        bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(
            view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    _save_economy(db)
    deck        = _bj_new_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    layout = BlackjackLayout(bet, interaction.user.id, deck, player_hand, dealer_hand)
    pv = _bj_hand_value(player_hand)
    dv = _bj_hand_value(dealer_hand)
    if pv == 21:
        db2 = _load_economy()
        if dv == 21:
            _add_coins(interaction.user.id, bet, db2)
            _save_economy(db2)
            layout.done = True
            layout._rebuild(reveal_dealer=True, result="push")
        else:
            payout = bet + int(bet * 1.5)
            _add_coins(interaction.user.id, payout, db2)
            _save_economy(db2)
            layout.done = True
            layout._rebuild(reveal_dealer=True, result="blackjack")
    await interaction.followup.send(view=layout)

# ── SLOTS ─────────────────────────────────────────────────────────────────────

_SLOTS_SYMBOLS = [
    ("", 0.03, 10.0),
    ("7",  0.06,  5.0),
    ("", 0.10,  3.0),
    ("", 0.15,  2.0),
    ("", 0.20,  1.5),
    ("", 0.22,  1.2),
    ("", 0.24,  1.1),
]

def _spin_slots() -> list:
    syms    = [s[0] for s in _SLOTS_SYMBOLS]
    weights = [s[1] for s in _SLOTS_SYMBOLS]
    return _random.choices(syms, weights=weights, k=3)

def _slots_result(reels: list, bet: int) -> tuple:
    if reels[0] == reels[1] == reels[2]:
        mult = next(m for s, _, m in _SLOTS_SYMBOLS if s == reels[0])
        return int(bet * mult), f" **JACKPOT!** All three **{reels[0]}** — **{mult}x**"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        return int(bet * 0.5), "Two matching — 0.5x (small win)"
    return 0, "No match — better luck next time!"


@bot.tree.command(name="slots", description="Spin the slot machine!")
@app_commands.describe(bet="Coins to bet")
async def slots_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.defer(ephemeral=False)
    if bet < 10:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Minimum bet is **10** ."), ephemeral=True)
        return
    if bet > 25_000:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Maximum bet is **25,000** ."), ephemeral=True)
        return
    db = _load_economy()
    if not _deduct_coins(interaction.user.id, bet, db):
        bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(
            view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    reels = _spin_slots()
    payout, result_text = _slots_result(reels, bet)
    if payout > 0:
        _add_coins(interaction.user.id, payout, db)
    _save_economy(db)
    net   = payout - bet
    color = C_SUCCESS if payout > bet else (C_WARN if payout > 0 else C_ERROR)
    await interaction.followup.send(view=_cv2(color,
        _td("## Slot Machine"),
        _sep(),
        _td(f"## {reels[0]}  {reels[1]}  {reels[2]}"),
        _td(result_text),
        _sep(),
        _td(f"**Bet:** {bet:,} "),
        _td(f"**Payout:** {payout:,} "),
        _td(f"**Net:** {'**+**' if net >= 0 else ''}{net:,} "),
        _td("-# =10x  7=5x  =3x  =2x  =1.5x  =1.2x  =1.1x"),
    ))

# ── COIN FLIP ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="coinflip", description="Flip a coin — heads or tails? Double or nothing!")
@app_commands.describe(bet="Coins to bet", choice="Your prediction")
@app_commands.choices(choice=[
    app_commands.Choice(name="Heads", value="heads"),
    app_commands.Choice(name="Tails", value="tails"),
])
async def coinflip_cmd(interaction: discord.Interaction, bet: int, choice: str):
    await interaction.response.defer(ephemeral=False)
    if bet < 10:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Minimum bet is **10** ."), ephemeral=True)
        return
    if bet > 8_000:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Maximum bet is **8,000** ."), ephemeral=True)
        return
    db = _load_economy()
    if not _deduct_coins(interaction.user.id, bet, db):
        bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(
            view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    result = _random.choice(["heads", "tails"])
    won    = result == choice
    if won:
        _add_coins(interaction.user.id, bet * 2, db)
    _save_economy(db)
    title = "Coin Flip — WIN!" if won else "Coin Flip — LOSE!"
    await interaction.followup.send(view=_cv2(C_SUCCESS if won else C_ERROR,
        _td(f"## {title}"),
        _sep(),
        _td(f"The coin landed on **{result.upper()}**\nYou chose **{choice.upper()}** — {'Correct!' if won else 'Wrong!'}"),
        _sep(),
        _td(f"**Bet:** {bet:,} coins  |  **Net:** {'+' if won else '-'}{bet:,} coins"),
    ))

# ── DICE DUEL ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="dice", description="Roll a dice — guess high (4-6) or low (1-3) for 2x payout!")
@app_commands.describe(bet="Coins to bet", prediction="High (4-6) or Low (1-3)")
@app_commands.choices(prediction=[
    app_commands.Choice(name="High (4-6) — 2x payout", value="high"),
    app_commands.Choice(name="Low  (1-3) — 2x payout", value="low"),
])
async def dice_cmd(interaction: discord.Interaction, bet: int, prediction: str):
    await interaction.response.defer(ephemeral=False)
    if bet < 10:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Minimum bet is **10** ."), ephemeral=True)
        return
    if bet > 50_000:
        await interaction.followup.send(
            view=cv2_err("Invalid Bet", "Maximum bet is **50,000** ."), ephemeral=True)
        return
    db = _load_economy()
    if not _deduct_coins(interaction.user.id, bet, db):
        bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(
            view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    roll    = _random.randint(1, 6)
    is_high = roll >= 4
    won     = (prediction == "high" and is_high) or (prediction == "low" and not is_high)
    if won:
        _add_coins(interaction.user.id, bet * 2, db)
    _save_economy(db)
    title = "Dice Roll — WIN!" if won else "Dice Roll — LOSE!"
    await interaction.followup.send(view=_cv2(C_SUCCESS if won else C_ERROR,
        _td(f"## {title}"),
        _sep(),
        _td(f"You rolled **{roll}** ({'HIGH' if is_high else 'LOW'})\nYou predicted **{prediction.upper()}** — {'Correct!' if won else 'Wrong!'}"),
        _sep(),
        _td(f"**Bet:** {bet:,} coins  |  **Net:** {'+' if won else '-'}{bet:,} coins"),
    ))

# ── TIC-TAC-TOE ───────────────────────────────────────────────────────────────

class TicTacToeGameLayout(discord.ui.LayoutView):
    def __init__(self, player_x: int, player_o: int, bet: int):
        super().__init__(timeout=300)
        self.player_x       = player_x
        self.player_o       = player_o
        self.current_player = player_x
        self.board          = [None] * 9
        self.bet            = bet
        self._rebuild()

    def _check_winner(self):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a, b, c in wins:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return None

    def _is_draw(self):
        return all(c is not None for c in self.board) and not self._check_winner()

    def _rebuild(self, status: str = None, done: bool = False, color: int = C_BRAND):
        self.clear_items()
        sym = {None: "\u200b", "X": "", "O": ""}
        header = [_td("## Tic-Tac-Toe"), _sep()]
        if status:
            header.append(_td(status))
        if self.bet > 0:
            header.append(_td(f"**Wager:** {self.bet:,}  each  ·  **Prize Pool:** {self.bet * 2:,} "))
        self.add_item(_cv2_cont(*header, color=color))
        for r in range(3):
            buttons = []
            for c in range(3):
                pos  = r * 3 + c
                cell = self.board[pos]
                if cell == "X":
                    btn = discord.ui.Button(
                        label="", style=discord.ButtonStyle.danger,
                        disabled=True, custom_id=f"ttt_{pos}")
                elif cell == "O":
                    btn = discord.ui.Button(
                        label="", style=discord.ButtonStyle.primary,
                        disabled=True, custom_id=f"ttt_{pos}")
                else:
                    btn = discord.ui.Button(
                        label="\u200b", style=discord.ButtonStyle.secondary,
                        disabled=done, custom_id=f"ttt_{pos}")
                    if not done:
                        btn.callback = self._make_move(pos)
                buttons.append(btn)
            self.add_item(discord.ui.ActionRow(*buttons))

    def _make_move(self, pos: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in (self.player_x, self.player_o):
                await interaction.response.send_message("You're not in this game!", ephemeral=True)
                return
            if interaction.user.id != self.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if self.board[pos] is not None:
                await interaction.response.defer()
                return
            symbol = "X" if self.current_player == self.player_x else "O"
            self.board[pos] = symbol
            winner = self._check_winner()
            if winner:
                self.stop()
                winner_id = self.player_x if winner == "X" else self.player_o
                try:
                    wu = interaction.guild.get_member(winner_id) or await interaction.guild.fetch_member(winner_id)
                    wname = wu.display_name
                except Exception:
                    wname = "Winner"
                if self.bet > 0:
                    db = _load_economy()
                    _add_coins(winner_id, self.bet * 2, db)
                    _save_economy(db)
                prize = f"  ·  **Prize:** {self.bet * 2:,} " if self.bet > 0 else ""
                self._rebuild(status=f" **{wname} wins!**{prize}", done=True, color=C_SUCCESS)
                await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)
            elif self._is_draw():
                self.stop()
                if self.bet > 0:
                    db = _load_economy()
                    _add_coins(self.player_x, self.bet, db)
                    _add_coins(self.player_o, self.bet, db)
                    _save_economy(db)
                self._rebuild(status="It's a draw! Bets returned.", done=True, color=C_WARN)
                await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)
            else:
                self.current_player = self.player_o if self.current_player == self.player_x else self.player_x
                nxt_sym = "" if self.current_player == self.player_x else ""
                self._rebuild(status=f"{nxt_sym} <@{self.current_player}>'s turn")
                await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)
        return callback


class TicTacToeAcceptLayout(discord.ui.LayoutView):
    def __init__(self, challenger_id: int, challenged_id: int, bet: int,
                 challenger_mention: str, opponent_mention: str):
        super().__init__(timeout=60)
        self.challenger_id   = challenger_id
        self.challenged_id   = challenged_id
        self.bet             = bet
        self.challenger_men  = challenger_mention
        self.opponent_men    = opponent_mention
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        desc = (f"{self.challenger_men} has challenged {self.opponent_men} to **Tic-Tac-Toe**!\n"
                f"{self.opponent_men}, do you accept?")
        if self.bet > 0:
            desc += f"\n\n**Wager:** {self.bet:,}  each  ·  **Prize Pool:** {self.bet * 2:,} "
        self.add_item(_cv2_cont(
            _td("## Tic-Tac-Toe Challenge!"),
            _sep(),
            _td(desc),
            _td("-# Challenge expires in 60 seconds"),
            color=C_BRAND,
        ))
        accept_btn = discord.ui.Button(
            label="Accept", style=discord.ButtonStyle.success, custom_id="ttt_accept")
        accept_btn.callback = self._accept
        decline_btn = discord.ui.Button(
            label="Decline", style=discord.ButtonStyle.danger, custom_id="ttt_decline")
        decline_btn.callback = self._decline
        self.add_item(discord.ui.ActionRow(accept_btn, decline_btn))

    async def _accept(self, interaction: discord.Interaction):
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
        if self.bet > 0:
            db = _load_economy()
            if not _deduct_coins(self.challenged_id, self.bet, db):
                bal = _get_balance(self.challenged_id, db)
                await interaction.response.send_message(
                    f"Not enough coins! Need {self.bet:,} coins but have {bal:,} coins.", ephemeral=True)
                return
            _save_economy(db)
        self.stop()
        game_layout = TicTacToeGameLayout(self.challenger_id, self.challenged_id, self.bet)
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=game_layout)

    async def _decline(self, interaction: discord.Interaction):
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
        self.stop()
        if self.bet > 0:
            db = _load_economy()
            _add_coins(self.challenger_id, self.bet, db)
            _save_economy(db)
        await interaction.response.edit_message(
            content=None, embeds=[], attachments=[],
            view=cv2_warn("Challenge Declined", f"{interaction.user.mention} declined the challenge."))


@bot.tree.command(name="tictactoe", description="Challenge someone to Tic-Tac-Toe!")
@app_commands.describe(
    opponent="The user to challenge",
    bet="Coins to wager (0 = free game)",
)
async def tictactoe_cmd(interaction: discord.Interaction, opponent: discord.Member, bet: int = 0):
    await interaction.response.defer(ephemeral=False)
    if opponent.id == interaction.user.id:
        await interaction.followup.send(
            view=cv2_err("Invalid", "You can't challenge yourself!"), ephemeral=True)
        return
    if opponent.bot:
        await interaction.followup.send(
            view=cv2_err("Invalid", "You can't challenge a bot!"), ephemeral=True)
        return
    if bet < 0:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Bet must be 0 or greater."), ephemeral=True)
        return
    if bet > 0:
        db = _load_economy()
        if not _deduct_coins(interaction.user.id, bet, db):
            bal = _get_balance(interaction.user.id, db)
            await interaction.followup.send(
                view=cv2_err("Insufficient Funds", f"Need {bet:,} coins but have {bal:,} coins."), ephemeral=True)
            return
        _save_economy(db)
    accept_layout = TicTacToeAcceptLayout(
        interaction.user.id, opponent.id, bet,
        interaction.user.mention, opponent.mention)
    await interaction.followup.send(view=accept_layout)

# ── ROB SYSTEM ────────────────────────────────────────────────────────────────

ROB_COOLDOWN_SECONDS  = 60
ROB_SUCCESS_RATE      = 0.35
ROB_PROTECTION_COST   = 7500
ROB_PROTECTION_DAYS   = 7


@bot.tree.command(name="rob", description="Try to rob another user's coins!")
@app_commands.describe(user="The user you want to rob")
async def rob_cmd(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=False)
    if user.id == interaction.user.id:
        await interaction.followup.send(
            view=cv2_err("Invalid", "You can't rob yourself!"), ephemeral=True)
        return
    if user.bot:
        await interaction.followup.send(
            view=cv2_err("Invalid", "You can't rob a bot!"), ephemeral=True)
        return
    sid = str(interaction.user.id)
    now = datetime.now(timezone.utc)
    cd  = _rob_cooldowns.get(sid)
    if cd and now < cd:
        await interaction.followup.send(
            view=cv2_err("Cooldown", f"You can try again <t:{int(cd.timestamp())}:R>."), ephemeral=True)
        return
    db = _load_economy()
    target_bal = _get_balance(user.id, db)
    if target_bal < 500:
        await interaction.followup.send(
            view=cv2_err("Not Worth It",
                         f"{user.display_name} only has **{target_bal:,}** . "
                         f"You need at least **500**  in their wallet to rob."), ephemeral=True)
        return
    _rob_cooldowns[sid] = now + timedelta(seconds=ROB_COOLDOWN_SECONDS)
    if _has_rob_protection(user.id, db):
        fine = _random.randint(300, 600)
        _deduct_coins(interaction.user.id, fine, db)
        _save_economy(db)
        await interaction.followup.send(view=_cv2(C_ERROR,
            _td("##  Robbery Foiled!"),
            _sep(),
            _td(
                f"**{user.display_name}** has **Rob Protection** active!\n"
                f"Their guards caught you and fined you **{fine:,}** !\n\n"
                f"**Fine Paid:**  -{fine:,}  ·  "
                f"**Next Attempt:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))
        return
    success = _random.random() < ROB_SUCCESS_RATE
    if success:
        pct    = _random.uniform(0.10, 0.40)
        stolen = max(1, int(target_bal * pct))
        _deduct_coins(user.id, stolen, db)
        _add_coins(interaction.user.id, stolen, db)
        _save_economy(db)
        new_bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(view=_cv2(C_SUCCESS,
            _td("##  Robbery Successful! "),
            _sep(),
            _td(
                f"You successfully robbed **{user.display_name}** and got away with "
                f"**{stolen:,}**  ({int(pct * 100)}% of their wallet)!\n\n"
                f"**Stolen:**  +{stolen:,}  ·  **Your Balance:**  {new_bal:,}\n"
                f"**Cooldown:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))
    else:
        fine = _random.randint(200, 500)
        _deduct_coins(interaction.user.id, fine, db)
        _save_economy(db)
        await interaction.followup.send(view=_cv2(C_ERROR,
            _td("##  Caught Red-Handed!"),
            _sep(),
            _td(
                f"Your robbery attempt on **{user.display_name}** failed!\n"
                f"You were caught and fined **{fine:,}** .\n\n"
                f"**Fine:**  -{fine:,}  ·  "
                f"**Cooldown:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))


@bot.tree.command(name="robprotection", description=f"Buy 7-day rob protection for 7,500  — no one can rob you!")
async def rob_protection_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    db  = _load_economy()
    sid = str(interaction.user.id)
    if _has_rob_protection(interaction.user.id, db):
        rec    = db.get("rob_protection", {}).get(sid, {})
        exp_ts = int(datetime.fromisoformat(rec["expires"]).timestamp())
        await interaction.followup.send(view=cv2_warn("Already Protected",
            f"You already have rob protection until <t:{exp_ts}:F>.\n"
            f"You can purchase again after it expires."), ephemeral=True)
        return
    if not _deduct_coins(interaction.user.id, ROB_PROTECTION_COST, db):
        bal = _get_balance(interaction.user.id, db)
        await interaction.followup.send(view=cv2_err("Insufficient Funds",
            f"Rob Protection costs **{ROB_PROTECTION_COST:,}** .\n"
            f"You only have **{bal:,}** ."), ephemeral=True)
        return
    expires = datetime.now(timezone.utc) + timedelta(days=ROB_PROTECTION_DAYS)
    db.setdefault("rob_protection", {})[sid] = {
        "expires":      expires.isoformat(),
        "purchased_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_economy(db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##  Rob Protection Activated!"),
        _sep(),
        _td(
            f"You are now shielded from all robbery attempts for **{ROB_PROTECTION_DAYS} days**!\n"
            f"Anyone who tries to rob you will be fined instead.\n\n"
            f"**Cost:**  {ROB_PROTECTION_COST:,}  ·  **Duration:** {ROB_PROTECTION_DAYS} days\n"
            f"**Expires:** <t:{int(expires.timestamp())}:F>"
        ),
        _td("-# SkyHighEV Economy  ·  Use /balance to check your protection status"),
    ))

# ── COIN LEADERBOARD ─────────────────────────────────────────────────────────

@bot.tree.command(name="coin-leaderboard", description="See the richest coin holders on the server")
async def coin_leaderboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    db       = _load_economy()
    balances = db.get("balances", {})
    if not balances:
        await interaction.followup.send(
            view=cv2_info("Leaderboard", "No one has any coins yet!"), ephemeral=True)
        return
    sorted_bal = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:10]
    entries = []
    for i, (uid, bal) in enumerate(sorted_bal):
        try:
            u    = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
            name = u.display_name
        except Exception:
            name = f"User {uid[:6]}…"
        entries.append({"rank": i + 1, "name": name, "balance": bal})
    img_file = build_coin_lb_image(entries)
    await interaction.followup.send(file=img_file)

# ── GIVE / TAKE COINS (Admin) ─────────────────────────────────────────────────

@bot.tree.command(name="give-coins", description="[Admin] Give coins to a user")
@app_commands.describe(user="The user to give coins to", amount="Amount of coins")
@admin_only()
async def give_coins_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    if amount <= 0:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Amount must be positive."), ephemeral=True)
        return
    db = _load_economy()
    _add_coins(user.id, amount, db)
    _save_economy(db)
    new_bal = _get_balance(user.id, db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##  Coins Given"),
        _sep(),
        _td(f"**User:** {user.mention}  ·  **Given:**  +{amount:,}  ·  **New Balance:**  {new_bal:,}"),
    ), ephemeral=True)


@bot.tree.command(name="take-coins", description="[Admin] Take coins from a user")
@app_commands.describe(user="The user to take from", amount="Amount of coins")
@admin_only()
async def take_coins_cmd(interaction: discord.Interaction, user: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    if amount <= 0:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Amount must be positive."), ephemeral=True)
        return
    db     = _load_economy()
    actual = min(amount, _get_balance(user.id, db))
    _deduct_coins(user.id, actual, db)
    _save_economy(db)
    new_bal = _get_balance(user.id, db)
    await interaction.followup.send(view=_cv2(C_WARN,
        _td("##  Coins Taken"),
        _sep(),
        _td(f"**User:** {user.mention}  ·  **Taken:**  -{actual:,}  ·  **New Balance:**  {new_bal:,}"),
    ), ephemeral=True)

# ── COIN WITHDRAWAL ───────────────────────────────────────────────────────────

@bot.tree.command(name="withdraw-coins", description="Request to cash out your coins for real money")
@app_commands.describe(amount="Number of coins to withdraw")
async def withdraw_coins_cmd(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    await _do_coin_payout(interaction, amount)


async def _do_coin_payout(interaction: discord.Interaction, amount: int):
    """Shared coin-withdrawal flow used by /withdraw-coins and the payout panel button.
    Caller MUST defer the interaction (ephemeral) before calling."""
    if amount < 5000:
        await interaction.followup.send(view=cv2_err(
            "Minimum Withdrawal", "Minimum withdrawal is **5,000** ."), ephemeral=True)
        return
    db        = _load_economy()
    coin_rate = db.get("coin_rate", 1000)
    usd       = round(amount / coin_rate, 2)
    bal       = _get_balance(interaction.user.id, db)
    if bal < amount:
        await interaction.followup.send(view=cv2_err(
            "Insufficient Funds", f"Need **{amount:,}**  but have **{bal:,}** ."), ephemeral=True)
        return
    existing = [w for w in db.get("withdrawals", [])
                if w["discordId"] == str(interaction.user.id) and w["status"] == "PENDING"]
    if existing:
        await interaction.followup.send(view=cv2_err("Already Pending",
            f"You already have a pending withdrawal (`#{existing[0]['id']}`). Wait for admin approval."), ephemeral=True)
        return
    pdb           = _load_payout_db()
    payout_method = pdb.get("payoutMethods", {}).get(str(interaction.user.id))
    if not payout_method:
        await interaction.followup.send(view=cv2_err("No Payout Method",
            "Set your payout method first with `/set-payout` (e.g. PayPal, crypto)."), ephemeral=True)
        return
    _deduct_coins(interaction.user.id, amount, db)
    w_id = db.get("next_withdrawal_id", 1)
    withdrawal = {
        "id":              w_id,
        "discordId":       str(interaction.user.id),
        "discordUsername": interaction.user.name,
        "coins":           amount,
        "usd":             usd,
        "coinRate":        coin_rate,
        "payoutMethod":    payout_method,
        "status":          "PENDING",
        "createdAt":       datetime.now(timezone.utc).isoformat(),
    }
    db.setdefault("withdrawals", []).append(withdrawal)
    db["next_withdrawal_id"] = w_id + 1
    _save_economy(db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##  Withdrawal Requested"),
        _sep(),
        _td(
            f"**Coins:**  {amount:,}  ·  **USD Value:** ${usd:.2f}  ·  **Rate:** {coin_rate:,}  = $1\n"
            f"**Request ID:** `#{w_id}`\n**Method:**\n```{payout_method}```"
        ),
        _td("-# An admin will review and process your withdrawal  ·  SkyHighEV Economy"),
    ), ephemeral=True)
    if PAYOUT_NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(PAYOUT_NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(view=_cv2(C_WARN,
                _td("##  Coin Withdrawal Request"),
                _sep(),
                _td(
                    f"{interaction.user.mention} wants to cash out coins!\n\n"
                    f"**User:** {interaction.user.name} (`{interaction.user.id}`)\n"
                    f"**Coins:**  {amount:,}  ·  **USD:** ${usd:.2f}  ·  **Rate:** {coin_rate:,} /$1\n"
                    f"**ID:** `#{w_id}`\n**Method:**\n```{payout_method}```"
                ),
                _td(f"-# Use /approve-withdrawal {w_id} to approve  ·  SkyHighEV Economy"),
            ))


@bot.tree.command(name="coin-withdrawals", description="[Admin] View pending coin withdrawal requests")
@admin_only()
async def coin_withdrawals_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    db      = _load_economy()
    pending = [w for w in db.get("withdrawals", []) if w["status"] == "PENDING"]
    if not pending:
        await interaction.followup.send(
            view=cv2_info("Withdrawals", "No pending coin withdrawals."), ephemeral=True)
        return
    lines = []
    for w in pending[-15:]:
        lines.append(
            f"`#{w['id']}` **{w['discordUsername']}** —  {w['coins']:,} → **${w['usd']:.2f}**\n"
            f"  Method: `{w['payoutMethod'][:50]}`"
        )
    await interaction.followup.send(view=_cv2(C_WARN,
        _td(f"##  Pending Coin Withdrawals ({len(pending)})"),
        _sep(),
        _td("\n\n".join(lines)),
        _td("-# Use /approve-withdrawal <id> to mark as paid  ·  SkyHighEV Economy"),
    ), ephemeral=True)


@bot.tree.command(name="approve-withdrawal", description="[Admin] Approve and mark a coin withdrawal as paid")
@app_commands.describe(withdrawal_id="The withdrawal request ID number")
@admin_only()
async def approve_withdrawal_cmd(interaction: discord.Interaction, withdrawal_id: int):
    await interaction.response.defer(ephemeral=True)
    db         = _load_economy()
    withdrawal = next((w for w in db.get("withdrawals", []) if w["id"] == withdrawal_id), None)
    if not withdrawal:
        await interaction.followup.send(view=cv2_err(
            "Not Found", f"No withdrawal with ID `#{withdrawal_id}`."), ephemeral=True)
        return
    if withdrawal["status"] != "PENDING":
        await interaction.followup.send(view=cv2_err("Already Processed",
            f"Withdrawal `#{withdrawal_id}` is already **{withdrawal['status']}**."), ephemeral=True)
        return
    withdrawal["status"] = "PAID"
    withdrawal["paidAt"] = datetime.now(timezone.utc).isoformat()
    withdrawal["paidBy"] = str(interaction.user.id)
    _save_economy(db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td(f"##  Withdrawal #{withdrawal_id} Approved"),
        _sep(),
        _td(
            f"**User:** `{withdrawal['discordUsername']}`  ·  "
            f"**Coins:**  {withdrawal['coins']:,}  ·  "
            f"**USD:** ${withdrawal['usd']:.2f}\n"
            f"**Method:**\n```{withdrawal['payoutMethod']}```"
        ),
        _td("-# SkyHighEV Economy"),
    ), ephemeral=True)
    try:
        u  = bot.get_user(int(withdrawal["discordId"])) or await bot.fetch_user(int(withdrawal["discordId"]))
        dm = base_embed(" Withdrawal Approved!", "", C_SUCCESS)
        dm.description = (
            f"Your coin withdrawal `#{withdrawal_id}` has been approved and paid!\n\n"
            f"**Coins withdrawn:**  {withdrawal['coins']:,}\n"
            f"**USD paid:** ${withdrawal['usd']:.2f}\n"
            f"**Method:** {withdrawal['payoutMethod']}"
        )
        dm.set_footer(text="SkyHighEV Economy  ·  Thanks for grinding!")
        await u.send(embed=dm)
    except Exception:
        pass


@bot.tree.command(name="set-coin-rate", description="[Admin] Set the coin-to-dollar conversion rate")
@app_commands.describe(coins_per_dollar="How many coins = $1 (e.g. 1000 means 1000 coins = $1)")
@admin_only()
async def set_coin_rate_cmd(interaction: discord.Interaction, coins_per_dollar: int):
    await interaction.response.defer(ephemeral=True)
    if coins_per_dollar < 1:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Rate must be at least 1."), ephemeral=True)
        return
    db = _load_economy()
    db["coin_rate"] = coins_per_dollar
    _save_economy(db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##  Coin Rate Updated"),
        _sep(),
        _td(f"New rate: **{coins_per_dollar:,}**  = **$1.00**"),
        _td("-# Workers see this rate when requesting coin withdrawals  ·  SkyHighEV Economy"),
    ), ephemeral=True)


@bot.tree.command(name="set-coin-price", description="[Admin] Set coin price by specifying coin amount and its USD value")
@app_commands.describe(
    coins="Number of coins (e.g. 10000)",
    price="USD price for that many coins (e.g. 0.10 means 10,000 coins = $0.10)",
)
@admin_only()
async def set_coin_price_cmd(interaction: discord.Interaction, coins: int, price: float):
    await interaction.response.defer(ephemeral=True)
    if coins < 1:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Coin amount must be at least 1."), ephemeral=True)
        return
    if price <= 0:
        await interaction.followup.send(
            view=cv2_err("Invalid", "Price must be greater than 0."), ephemeral=True)
        return
    coins_per_dollar = int(round(coins / price))
    if coins_per_dollar < 1:
        coins_per_dollar = 1
    db = _load_economy()
    db["coin_rate"] = coins_per_dollar
    _save_economy(db)
    await interaction.followup.send(view=_cv2(C_SUCCESS,
        _td("##  Coin Price Set"),
        _sep(),
        _td(
            f"**{coins:,}**  = **${price:.4f}**\n"
            f"Per 10,000 coins = **${10_000 / coins_per_dollar:.4f}**\n"
            f"Effective rate: **{coins_per_dollar:,}**  per $1.00"
        ),
        _td("-# Workers see this rate when requesting coin withdrawals  ·  SkyHighEV Economy"),
    ), ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PREFIX ECONOMY COMMANDS  (prefix: :-:)
# ══════════════════════════════════════════════════════════════════════════════

# ── Help Menu ─────────────────────────────────────────────────────────────────

_HELP_PAGES = {
    "earning": {
        "title": "Economy — Earning Coins",
        "lines": [
            ("balance [user]",       "Check your coin balance or someone else's"),
            ("daily",                "Claim daily reward (500-2500 coins, streak bonus)"),
            ("work",                 "Do a job and earn coins — 1 hour cooldown"),
            ("fish",                 "Go fishing — 10 min cooldown"),
            ("hunt",                 "Go hunting — 15 min cooldown"),
            ("crime",                "Commit a crime for big coins, but risky — 30 min cooldown"),
            ("crate",                "Open a free loot crate — every 6 hours"),
            ("lb",                   "Top 10 richest coin holders"),
            ("withdraw <amount>",    "Request to cash out coins for real money"),
        ],
    },
    "games": {
        "title": "Economy — Games",
        "lines": [
            ("mines <bet> [grid] [risk]",    "Reveal tiles, cash out or boom (grid: 3x3/4x4/5x4/5x5, risk: low/medium/high/extreme)"),
            ("blackjack <bet>",               "Blackjack vs the dealer — Hit, Stand, Double"),
            ("slots <bet>",                   "Spin the slot machine — jackpot = 10x"),
            ("coinflip <bet> <heads/tails>",  "Heads or Tails — 2x payout"),
            ("dice <bet> <high/low>",         "Guess High (4-6) or Low (1-3) — 2x payout"),
            ("roulette <bet> <red/black/green/odd/even/0-36>", "Spin the wheel — up to 35x"),
            ("tictactoe @user [bet]",         "Challenge a user to Tic-Tac-Toe"),
            ("rps <bet> <r/p/s>",             "Rock Paper Scissors vs the bot"),
            ("crash <bet>",                   "Cash out before the rocket crashes"),
            ("buycrate",                      "Buy a loot crate for 500 — random reward"),
            ("lottery [buy <n>]",             "Buy lottery tickets for the jackpot"),
        ],
    },
    "bank": {
        "title": "Economy — Bank, Shop & Profile",
        "lines": [
            ("bank [user]",              "View bank balance — earns 2% / day interest"),
            ("deposit <amount|all>",     "Deposit coins into the bank (safe from rob)"),
            ("bankwithdraw <amount|all>","Withdraw coins from the bank to wallet"),
            ("pay @user <amount>",       "Send coins to another user (5% tax)"),
            ("shop",                     "Browse purchasable items"),
            ("buy <item_id>",            "Buy an item from the shop"),
            ("inventory [user]",         "View owned items"),
            ("profile [user]",           "Show full profile (wallet, bank, items, streak)"),
            ("history",                  "View your last 15 transactions"),
        ],
    },
    "robbery": {
        "title": "Economy — Robbery",
        "lines": [
            ("rob @user",        "Try to steal coins — 35% success, 1-hour cooldown"),
            ("robprotect",       "Buy 7-day rob protection for 7,500 coins"),
        ],
    },
    "admin": {
        "title": "Economy — Admin Commands",
        "lines": [
            ("give @user <amount>",             "Give coins to a user"),
            ("take @user <amount>",             "Take coins from a user"),
            ("setrate <coins>",                 "Set conversion rate: X coins = $1"),
            ("/set-coin-price <coins> <price>", "Set price: e.g. 10000 coins = $0.10"),
            ("withdrawals",                     "View all pending coin withdrawal requests"),
            ("approve <id>",                    "Mark a coin withdrawal as paid"),
        ],
    },
}

def _build_help_cv2(page: str) -> discord.ui.LayoutView:
    data  = _HELP_PAGES[page]
    lines = [f"`{cmd}`\n  {desc}" for cmd, desc in data["lines"]]
    return _cv2(C_BRAND,
        _td(f"## {data['title']}"),
        _sep(),
        _td("\n\n".join(lines)),
        _td("-# SkyHighEV Economy"),
    )


class HelpMenuLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, page: str = "earning"):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.page      = page
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        data  = _HELP_PAGES[self.page]
        lines = [f"`{cmd}`\n  {desc}" for cmd, desc in data["lines"]]
        earn_btn = discord.ui.Button(
            label="Earning", style=discord.ButtonStyle.primary, custom_id="hmenu_earn")
        earn_btn.callback = self._btn_earning
        games_btn = discord.ui.Button(
            label="Games", style=discord.ButtonStyle.primary, custom_id="hmenu_games")
        games_btn.callback = self._btn_games
        bank_btn = discord.ui.Button(
            label="Bank/Shop", style=discord.ButtonStyle.success, custom_id="hmenu_bank")
        bank_btn.callback = self._btn_bank
        rob_btn = discord.ui.Button(
            label="Robbery", style=discord.ButtonStyle.danger, custom_id="hmenu_rob")
        rob_btn.callback = self._btn_robbery
        admin_btn = discord.ui.Button(
            label="Admin", style=discord.ButtonStyle.secondary, custom_id="hmenu_admin")
        admin_btn.callback = self._btn_admin
        self.add_item(_cv2_cont(
            _td(f"## {data['title']}"),
            _sep(),
            _td("\n\n".join(lines)),
            _td("-# SkyHighEV Economy"),
            color=C_BRAND,
        ))
        self.add_item(discord.ui.ActionRow(earn_btn, games_btn, bank_btn, rob_btn, admin_btn))

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Open your own help menu with `:-:help`.", ephemeral=True)
            return False
        return True

    async def _switch(self, interaction: discord.Interaction, page: str):
        if not await self._guard(interaction): return
        self.page = page
        self._rebuild()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def _btn_earning(self, interaction: discord.Interaction):
        await self._switch(interaction, "earning")

    async def _btn_games(self, interaction: discord.Interaction):
        await self._switch(interaction, "games")

    async def _btn_bank(self, interaction: discord.Interaction):
        await self._switch(interaction, "bank")

    async def _btn_robbery(self, interaction: discord.Interaction):
        await self._switch(interaction, "robbery")

    async def _btn_admin(self, interaction: discord.Interaction):
        if not await self._guard(interaction): return
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Admin section is restricted.", ephemeral=True)
            return
        await self._switch(interaction, "admin")


@bot.command(name="help", aliases=["h"])
async def prefix_help(ctx: commands.Context):
    view = HelpMenuLayout(ctx.author.id)
    await ctx.send(view=view)

# ── :-:balance ────────────────────────────────────────────────────────────────

@bot.command(name="balance", aliases=["bal", "wallet", "coins"])
async def prefix_balance(ctx: commands.Context, user: discord.Member = None):
    target   = user or ctx.author
    db       = _load_economy()
    bal      = _get_balance(target.id, db)
    own      = target.id == ctx.author.id
    who      = "Your" if own else f"{target.display_name}'s"
    kids = [_td(f"## {who} Wallet"), _sep(), _td(f"**Balance:** {bal:,} ")]
    if own and _has_rob_protection(target.id, db):
        rec = db.get("rob_protection", {}).get(str(target.id), {})
        if rec.get("expires"):
            exp_ts = int(datetime.fromisoformat(rec["expires"]).timestamp())
            kids.append(_td(f" Rob Protection active until <t:{exp_ts}:R>"))
    kids.append(_td("-# SkyHighEV Economy  ·  :-:balance"))
    await ctx.send(view=_cv2(C_GOLD, *kids))

# ── :-:daily ──────────────────────────────────────────────────────────────────

@bot.command(name="daily")
async def prefix_daily(ctx: commands.Context):
    db  = _load_economy()
    sid = str(ctx.author.id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last  = db.get("daily", {}).get(sid)
    if last == today:
        tomorrow = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=1))
        await ctx.send(view=cv2_err("Already Claimed",
            f"Already claimed today. Come back <t:{int(tomorrow.timestamp())}:R>!"))
        return
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    streak    = db.get("streaks", {}).get(sid, 0)
    streak    = streak + 1 if last == yesterday else 1
    db.setdefault("streaks", {})[sid]  = streak
    base_r    = _random.randint(500, 1500)
    bonus     = min(streak * 100, 1000)
    total     = base_r + bonus
    _add_coins(ctx.author.id, total, db)
    db.setdefault("daily", {})[sid] = today
    _save_economy(db)
    new_bal = _get_balance(ctx.author.id, db)
    streak_line = f" **{streak}-day streak!** Keep it up!" if streak >= 7 else f"Streak: **{streak}/7** days"
    kids = [_td("## Daily Reward Claimed!"), _sep(), _td(streak_line), _sep(),
            _td(f"**Base:**  {base_r:,}")]
    if bonus:
        kids.append(_td(f"**Streak Bonus (Day {streak}):**  +{bonus:,}"))
    kids.append(_td(f"**Total:**  **{total:,}**  ·  **Balance:**  {new_bal:,}"))
    await ctx.send(view=_cv2(C_SUCCESS, *kids))

# ── :-:work ───────────────────────────────────────────────────────────────────

@bot.command(name="work")
async def prefix_work(ctx: commands.Context):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _work_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("On Break", f"Come back <t:{int(cd.timestamp())}:R>."))
        return
    job_desc, mn, mx = _random.choice(_WORK_JOBS)
    earned = _random.randint(mn, mx)
    _work_cooldowns[sid] = now + timedelta(seconds=WORK_COOLDOWN_SECONDS)
    db  = _load_economy()
    _add_coins(ctx.author.id, earned, db)
    _save_economy(db)
    new_bal = _get_balance(ctx.author.id, db)
    next_ts = int(_work_cooldowns[sid].timestamp())
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("## Work Complete!"),
        _sep(),
        _td(f"You {job_desc} and earned **{earned:,}** !\n\n"
            f"**Earned:**  +{earned:,} coins ·  **Balance:**  {new_bal:,}\n"
            f"**Next Shift:** <t:{next_ts}:R>"),
    ))

# ── :-:lb (leaderboard) ───────────────────────────────────────────────────────

@bot.command(name="lb", aliases=["leaderboard", "rich", "top"])
async def prefix_lb(ctx: commands.Context):
    db       = _load_economy()
    balances = db.get("balances", {})
    if not balances:
        await ctx.send(view=cv2_info("Leaderboard", "No one has any coins yet!"))
        return
    sorted_bal = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:10]
    entries = []
    for i, (uid, bal) in enumerate(sorted_bal):
        try:
            u    = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
            name = u.display_name
        except Exception:
            name = f"User {uid[:6]}"
        entries.append({"rank": i + 1, "name": name, "balance": bal})
    img_file = build_coin_lb_image(entries)
    await ctx.send(file=img_file)

# ── :-:mines ──────────────────────────────────────────────────────────────────

@bot.command(name="mines", aliases=["mine", "m"])
async def prefix_mines(ctx: commands.Context, bet: int = 0):
    if bet < 50:
        await ctx.send(view=cv2_err("Invalid Bet", "Minimum bet is **50** \U0001fa99.\nUsage: `!mines <bet>`"))
        return
    if bet > 5_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is **5,000** \U0001fa99."))
        return
    db  = _load_economy()
    bal = _get_balance(ctx.author.id, db)
    if bal < bet:
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}** \U0001fa99 but have **{bal:,}** \U0001fa99."))
        return
    await ctx.send(view=MinesConfigLayout(ctx.author.id, bet, bal))

# ── :-:blackjack ──────────────────────────────────────────────────────────────

@bot.command(name="blackjack", aliases=["bj"])
async def prefix_blackjack(ctx: commands.Context, bet: int = 0):
    if bet < 50:
        await ctx.send(view=cv2_err("Invalid Bet", "Minimum bet is 50 . Usage: `:-:blackjack <bet>`"))
        return
    if bet > 50_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is 50,000 ."))
        return
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
        return
    _save_economy(db)
    deck        = _bj_new_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    layout = BlackjackLayout(bet, ctx.author.id, deck, player_hand, dealer_hand)
    pv = _bj_hand_value(player_hand)
    dv = _bj_hand_value(dealer_hand)
    if pv == 21:
        db2 = _load_economy()
        if dv == 21:
            _add_coins(ctx.author.id, bet, db2)
            _save_economy(db2)
            layout.done = True
            layout._rebuild(reveal_dealer=True, result="push")
        else:
            payout = bet + int(bet * 1.5)
            _add_coins(ctx.author.id, payout, db2)
            _save_economy(db2)
            layout.done = True
            layout._rebuild(reveal_dealer=True, result="blackjack")
    await ctx.send(view=layout)

# ── :-:slots ──────────────────────────────────────────────────────────────────

@bot.command(name="slots", aliases=["slot", "s"])
async def prefix_slots(ctx: commands.Context, bet: int = 0):
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Bet", "Minimum bet is 10 . Usage: `:-:slots <bet>`"))
        return
    if bet > 25_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is 25,000 ."))
        return
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
        return
    reels = _spin_slots()
    payout, result_text = _slots_result(reels, bet)
    if payout > 0:
        _add_coins(ctx.author.id, payout, db)
    _save_economy(db)
    net   = payout - bet
    color = C_SUCCESS if payout > bet else (C_WARN if payout > 0 else C_ERROR)
    await ctx.send(view=_cv2(color,
        _td("## Slot Machine"),
        _sep(),
        _td(f"## {reels[0]}  {reels[1]}  {reels[2]}"),
        _td(result_text),
        _sep(),
        _td(f"**Bet:**  {bet:,}  ·  **Payout:**  {payout:,}  ·  **Net:** {' +' if net >= 0 else ' '}{net:,}"),
        _td("-# Jackpot = all 3 matching  ·  SkyHighEV Economy"),
    ))

# ── :-:coinflip ───────────────────────────────────────────────────────────────

@bot.command(name="coinflip", aliases=["cf", "flip"])
async def prefix_coinflip(ctx: commands.Context, bet: int = 0, choice: str = ""):
    choice = choice.lower()
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Bet", "Usage: `:-:coinflip <bet> <heads/tails>`"))
        return
    if bet > 8_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is 8,000 ."))
        return
    if choice not in ("heads", "tails", "h", "t"):
        await ctx.send(view=cv2_err("Invalid Choice", "Choose `heads` or `tails`. Usage: `:-:coinflip <bet> <heads/tails>`"))
        return
    choice = "heads" if choice in ("heads", "h") else "tails"
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
        return
    result = _random.choice(["heads", "tails"])
    won    = result == choice
    if won:
        _add_coins(ctx.author.id, bet * 2, db)
    _save_economy(db)
    title = "Coin Flip — WIN!" if won else "Coin Flip — LOSE!"
    await ctx.send(view=_cv2(C_SUCCESS if won else C_ERROR,
        _td(f"## {title}"),
        _sep(),
        _td(f"The coin landed on **{result.upper()}**\n"
            f"You chose **{choice.upper()}** — {'Correct!' if won else 'Wrong!'}\n\n"
            f"**Bet:** {bet:,} coins  |  **Net:** {'+' if won else '-'}{bet:,} coins"),
    ))

# ── :-:dice ───────────────────────────────────────────────────────────────────

@bot.command(name="dice", aliases=["d", "roll"])
async def prefix_dice(ctx: commands.Context, bet: int = 0, prediction: str = ""):
    prediction = prediction.lower()
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Bet", "Usage: `:-:dice <bet> <high/low>`"))
        return
    if bet > 50_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is 50,000 ."))
        return
    if prediction not in ("high", "low", "h", "l"):
        await ctx.send(view=cv2_err("Invalid Prediction", "Choose `high` or `low`. Usage: `:-:dice <bet> <high/low>`"))
        return
    prediction = "high" if prediction in ("high", "h") else "low"
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
        return
    roll    = _random.randint(1, 6)
    is_high = roll >= 4
    won     = (prediction == "high" and is_high) or (prediction == "low" and not is_high)
    if won:
        _add_coins(ctx.author.id, bet * 2, db)
    _save_economy(db)
    title = "Dice Roll — WIN!" if won else "Dice Roll — LOSE!"
    await ctx.send(view=_cv2(C_SUCCESS if won else C_ERROR,
        _td(f"## {title}"),
        _sep(),
        _td(f"You rolled **{roll}** ({'HIGH' if is_high else 'LOW'})\n"
            f"You predicted **{prediction.upper()}** — {'Correct!' if won else 'Wrong!'}\n\n"
            f"**Bet:** {bet:,} coins  |  **Net:** {'+' if won else '-'}{bet:,} coins"),
    ))

# ── :-:tictactoe ──────────────────────────────────────────────────────────────

@bot.command(name="tictactoe", aliases=["ttt"])
async def prefix_tictactoe(ctx: commands.Context, opponent: discord.Member = None, bet: int = 0):
    if not opponent:
        await ctx.send(view=cv2_err("Missing User", "Usage: `:-:tictactoe @user [bet]`"))
        return
    if opponent.id == ctx.author.id:
        await ctx.send(view=cv2_err("Invalid", "You can't challenge yourself!"))
        return
    if opponent.bot:
        await ctx.send(view=cv2_err("Invalid", "You can't challenge a bot!"))
        return
    if bet < 0:
        await ctx.send(view=cv2_err("Invalid", "Bet must be 0 or more."))
        return
    if bet > 0:
        db = _load_economy()
        if not _deduct_coins(ctx.author.id, bet, db):
            bal = _get_balance(ctx.author.id, db)
            await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
            return
        _save_economy(db)
    accept_layout = TicTacToeAcceptLayout(
        ctx.author.id, opponent.id, bet,
        ctx.author.mention, opponent.mention)
    await ctx.send(view=accept_layout)

# ── :-:rob ────────────────────────────────────────────────────────────────────

@bot.command(name="rob")
async def prefix_rob(ctx: commands.Context, user: discord.Member = None):
    if not user:
        await ctx.send(view=cv2_err("Missing User", "Usage: `:-:rob @user`"))
        return
    if user.id == ctx.author.id:
        await ctx.send(view=cv2_err("Invalid", "You can't rob yourself!"))
        return
    if user.bot:
        await ctx.send(view=cv2_err("Invalid", "You can't rob a bot!"))
        return
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _rob_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("Cooldown", f"You can try again <t:{int(cd.timestamp())}:R>."))
        return
    db         = _load_economy()
    target_bal = _get_balance(user.id, db)
    if target_bal < 500:
        await ctx.send(view=cv2_err("Not Worth It",
            f"{user.display_name} only has **{target_bal:,}** . Need 500+ to attempt a robbery."))
        return
    _rob_cooldowns[sid] = now + timedelta(seconds=ROB_COOLDOWN_SECONDS)
    if _has_rob_protection(user.id, db):
        fine = _random.randint(300, 600)
        _deduct_coins(ctx.author.id, fine, db)
        _save_economy(db)
        await ctx.send(view=_cv2(C_ERROR,
            _td("##  Robbery Foiled!"),
            _sep(),
            _td(
                f"**{user.display_name}** has Rob Protection active!\n"
                f"Their guards caught you and fined you **{fine:,}** !\n\n"
                f"**Fine Paid:**  -{fine:,}  ·  "
                f"**Next Attempt:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))
        return
    success = _random.random() < ROB_SUCCESS_RATE
    if success:
        pct    = _random.uniform(0.10, 0.40)
        stolen = max(1, int(target_bal * pct))
        _deduct_coins(user.id, stolen, db)
        _add_coins(ctx.author.id, stolen, db)
        _save_economy(db)
        new_bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=_cv2(C_SUCCESS,
            _td("##  Robbery Successful! "),
            _sep(),
            _td(
                f"You robbed **{user.display_name}** and got away with "
                f"**{stolen:,}**  ({int(pct * 100)}% of their wallet)!\n\n"
                f"**Stolen:**  +{stolen:,}  ·  **Your Balance:**  {new_bal:,}\n"
                f"**Cooldown:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))
    else:
        fine = _random.randint(200, 500)
        _deduct_coins(ctx.author.id, fine, db)
        _save_economy(db)
        await ctx.send(view=_cv2(C_ERROR,
            _td("##  Caught Red-Handed!"),
            _sep(),
            _td(
                f"Your robbery attempt on **{user.display_name}** failed!\n"
                f"You were caught and fined **{fine:,}** .\n\n"
                f"**Fine:**  -{fine:,}  ·  "
                f"**Cooldown:** <t:{int(_rob_cooldowns[sid].timestamp())}:R>"
            ),
        ))

# ── :-:robprotect ─────────────────────────────────────────────────────────────

@bot.command(name="robprotect", aliases=["rp", "protect"])
async def prefix_robprotect(ctx: commands.Context):
    db  = _load_economy()
    sid = str(ctx.author.id)
    if _has_rob_protection(ctx.author.id, db):
        rec    = db.get("rob_protection", {}).get(sid, {})
        exp_ts = int(datetime.fromisoformat(rec["expires"]).timestamp())
        await ctx.send(view=cv2_warn("Already Protected",
            f"You are protected until <t:{exp_ts}:F>. Purchase again after it expires."))
        return
    if not _deduct_coins(ctx.author.id, ROB_PROTECTION_COST, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds",
            f"Rob Protection costs **{ROB_PROTECTION_COST:,}** .\nYou have **{bal:,}** ."))
        return
    expires = datetime.now(timezone.utc) + timedelta(days=ROB_PROTECTION_DAYS)
    db.setdefault("rob_protection", {})[sid] = {
        "expires":      expires.isoformat(),
        "purchased_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Rob Protection Activated!"),
        _sep(),
        _td(
            f"You are now shielded from all robberies for **{ROB_PROTECTION_DAYS} days**!\n"
            f"Anyone who tries to rob you will be fined instead.\n\n"
            f"**Cost:**  {ROB_PROTECTION_COST:,}  ·  **Duration:** {ROB_PROTECTION_DAYS} days\n"
            f"**Expires:** <t:{int(expires.timestamp())}:F>"
        ),
        _td("-# SkyHighEV Economy  ·  Use :-:balance to check your protection status"),
    ))

# ── :-:withdraw ───────────────────────────────────────────────────────────────

@bot.command(name="withdraw", aliases=["cash", "cashout"])
async def prefix_withdraw(ctx: commands.Context, amount: int = 0):
    if amount < 5000:
        await ctx.send(view=cv2_err("Minimum Withdrawal", "Minimum is **5,000** . Usage: `:-:withdraw <amount>`"))
        return
    db        = _load_economy()
    coin_rate = db.get("coin_rate", 1000)
    usd       = round(amount / coin_rate, 2)
    bal       = _get_balance(ctx.author.id, db)
    if bal < amount:
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{amount:,}**  but have **{bal:,}** ."))
        return
    existing = [w for w in db.get("withdrawals", [])
                if w["discordId"] == str(ctx.author.id) and w["status"] == "PENDING"]
    if existing:
        await ctx.send(view=cv2_err("Already Pending",
            f"You have a pending withdrawal (`#{existing[0]['id']}`). Wait for admin approval."))
        return
    pdb           = _load_payout_db()
    payout_method = pdb.get("payoutMethods", {}).get(str(ctx.author.id))
    if not payout_method:
        await ctx.send(view=cv2_err("No Payout Method",
            "Set your payout method first with `/set-payout` (e.g. PayPal, crypto)."))
        return
    _deduct_coins(ctx.author.id, amount, db)
    w_id = db.get("next_withdrawal_id", 1)
    withdrawal = {
        "id":              w_id,
        "discordId":       str(ctx.author.id),
        "discordUsername": ctx.author.name,
        "coins":           amount,
        "usd":             usd,
        "coinRate":        coin_rate,
        "payoutMethod":    payout_method,
        "status":          "PENDING",
        "createdAt":       datetime.now(timezone.utc).isoformat(),
    }
    db.setdefault("withdrawals", []).append(withdrawal)
    db["next_withdrawal_id"] = w_id + 1
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Withdrawal Requested"),
        _sep(),
        _td(
            f"**Coins:**  {amount:,}  ·  **USD Value:** ${usd:.2f}  ·  **Rate:** {coin_rate:,}  = $1\n"
            f"**Request ID:** `#{w_id}`\n**Method:**\n```{payout_method}```"
        ),
        _td("-# An admin will review and process your withdrawal  ·  SkyHighEV Economy"),
    ))
    if PAYOUT_NOTIFY_CHANNEL_ID:
        ch = bot.get_channel(PAYOUT_NOTIFY_CHANNEL_ID)
        if ch:
            await ch.send(view=_cv2(C_WARN,
                _td("##  Coin Withdrawal Request"),
                _sep(),
                _td(
                    f"{ctx.author.mention} wants to cash out!\n\n"
                    f"**User:** {ctx.author.name} (`{ctx.author.id}`)\n"
                    f"**Coins:**  {amount:,}  ·  **USD:** ${usd:.2f}  ·  **Rate:** {coin_rate:,} /$1\n"
                    f"**ID:** `#{w_id}`\n**Method:**\n```{payout_method}```"
                ),
                _td(f"-# Use /approve-withdrawal {w_id} or :-:approve {w_id}  ·  SkyHighEV Economy"),
            ))

# ── Admin prefix commands ─────────────────────────────────────────────────────

def _prefix_admin_check(ctx: commands.Context) -> bool:
    return ctx.author.id in ADMIN_IDS

@bot.command(name="give", aliases=["addcoins"])
async def prefix_give(ctx: commands.Context, user: discord.Member = None, amount: int = 0):
    if not _prefix_admin_check(ctx):
        await ctx.send(view=cv2_err("Access Denied", "Admins only."))
        return
    if not user or amount <= 0:
        await ctx.send(view=cv2_err("Usage", "`:-:give @user <amount>`"))
        return
    db = _load_economy()
    _add_coins(user.id, amount, db)
    _save_economy(db)
    new_bal = _get_balance(user.id, db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Coins Given"),
        _sep(),
        _td(f"**User:** {user.mention}  ·  **Given:**  +{amount:,}  ·  **New Balance:**  {new_bal:,}"),
    ))

@bot.command(name="take", aliases=["removecoins"])
async def prefix_take(ctx: commands.Context, user: discord.Member = None, amount: int = 0):
    if not _prefix_admin_check(ctx):
        await ctx.send(view=cv2_err("Access Denied", "Admins only."))
        return
    if not user or amount <= 0:
        await ctx.send(view=cv2_err("Usage", "`:-:take @user <amount>`"))
        return
    db     = _load_economy()
    actual = min(amount, _get_balance(user.id, db))
    _deduct_coins(user.id, actual, db)
    _save_economy(db)
    new_bal = _get_balance(user.id, db)
    await ctx.send(view=_cv2(C_WARN,
        _td("##  Coins Taken"),
        _sep(),
        _td(f"**User:** {user.mention}  ·  **Taken:**  -{actual:,}  ·  **New Balance:**  {new_bal:,}"),
    ))

@bot.command(name="setrate")
async def prefix_setrate(ctx: commands.Context, coins_per_dollar: int = 0):
    if not _prefix_admin_check(ctx):
        await ctx.send(view=cv2_err("Access Denied", "Admins only."))
        return
    if coins_per_dollar < 1:
        await ctx.send(view=cv2_err("Usage", "`:-:setrate <coins_per_dollar>`"))
        return
    db = _load_economy()
    db["coin_rate"] = coins_per_dollar
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Coin Rate Updated"),
        _sep(),
        _td(f"New rate: **{coins_per_dollar:,}**  = **$1.00**"),
        _td("-# SkyHighEV Economy"),
    ))

@bot.command(name="withdrawals")
async def prefix_withdrawals(ctx: commands.Context):
    if not _prefix_admin_check(ctx):
        await ctx.send(view=cv2_err("Access Denied", "Admins only."))
        return
    db      = _load_economy()
    pending = [w for w in db.get("withdrawals", []) if w["status"] == "PENDING"]
    if not pending:
        await ctx.send(view=cv2_info("Withdrawals", "No pending coin withdrawals."))
        return
    lines = []
    for w in pending[-15:]:
        lines.append(
            f"`#{w['id']}` **{w['discordUsername']}** —  {w['coins']:,} → **${w['usd']:.2f}**\n"
            f"  Method: `{w['payoutMethod'][:50]}`"
        )
    await ctx.send(view=_cv2(C_WARN,
        _td(f"##  Pending Coin Withdrawals ({len(pending)})"),
        _sep(),
        _td("\n\n".join(lines)),
        _td("-# Use :-:approve <id> to mark as paid  ·  SkyHighEV Economy"),
    ))

@bot.command(name="approve")
async def prefix_approve(ctx: commands.Context, withdrawal_id: int = 0):
    if not _prefix_admin_check(ctx):
        await ctx.send(view=cv2_err("Access Denied", "Admins only."))
        return
    if withdrawal_id <= 0:
        await ctx.send(view=cv2_err("Usage", "`:-:approve <withdrawal_id>`"))
        return
    db         = _load_economy()
    withdrawal = next((w for w in db.get("withdrawals", []) if w["id"] == withdrawal_id), None)
    if not withdrawal:
        await ctx.send(view=cv2_err("Not Found", f"No withdrawal with ID `#{withdrawal_id}`."))
        return
    if withdrawal["status"] != "PENDING":
        await ctx.send(view=cv2_err("Already Processed",
            f"Withdrawal `#{withdrawal_id}` is already **{withdrawal['status']}**."))
        return
    withdrawal["status"] = "PAID"
    withdrawal["paidAt"] = datetime.now(timezone.utc).isoformat()
    withdrawal["paidBy"] = str(ctx.author.id)
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td(f"##  Withdrawal #{withdrawal_id} Approved"),
        _sep(),
        _td(
            f"**User:** `{withdrawal['discordUsername']}`  ·  "
            f"**Coins:**  {withdrawal['coins']:,}  ·  "
            f"**USD:** ${withdrawal['usd']:.2f}\n"
            f"**Method:**\n```{withdrawal['payoutMethod']}```"
        ),
        _td("-# SkyHighEV Economy"),
    ))
    try:
        u  = bot.get_user(int(withdrawal["discordId"])) or await bot.fetch_user(int(withdrawal["discordId"]))
        dm = base_embed("Withdrawal Approved", "", C_SUCCESS)
        dm.description = (
            f"Your withdrawal `#{withdrawal_id}` has been approved and paid!\n\n"
            f"Coins:  {withdrawal['coins']:,}\n"
            f"USD paid: ${withdrawal['usd']:.2f}\n"
            f"Method: {withdrawal['payoutMethod']}"
        )
        dm.set_footer(text="SkyHighEV Economy  |  Thanks for grinding!")
        await u.send(embed=dm)
    except Exception:
        pass


# ── :-:hack ───────────────────────────────────────────────────────────────────

_hack_cooldowns: dict = {}
_HACK_CD_SECS = 3600

_HACK_SCENARIOS = [
    ("SUCCESS",   0.22, "firewall breach",       400,  1200),
    ("SUCCESS",   0.18, "database leak",          700,  2000),
    ("SUCCESS",   0.08, "crypto wallet drained",  2000, 5000),
    ("CAUGHT",    0.28, "police traced your IP",  300,  900),
    ("CAUGHT",    0.12, "federal agents raided",  800,  2500),
    ("CAUGHT",    0.05, "Interpol arrest",        3000, 8000),
    ("NOTHING",   0.05, "target offline",         0,    0),
    ("NOTHING",   0.02, "VPN overloaded",         0,    0),
]

@bot.command(name="hack", aliases=["hk"])
async def prefix_hack(ctx: commands.Context, target: str = ""):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _hack_cooldowns.get(sid)
    if cd and now < cd:
        ts = int(cd.timestamp())
        await ctx.send(view=cv2_err("Cooling Down",
            f"Your hacking tools are recharging.\nTry again <t:{ts}:R>."))
        return

    _hack_cooldowns[sid] = now + timedelta(seconds=_HACK_CD_SECS)

    # loading animation line
    loading_lines = [
        "```",
        "> Initializing exploit kit...",
        "> Scanning open ports...",
        "> Injecting payload...",
        "> Bypassing firewall...",
        "```",
    ]
    await ctx.send(view=_cv2(C_BRAND,
        _td("## \U0001f5a5\ufe0f  Hack Attempt"),
        _sep(),
        _td("\n".join(loading_lines)),
        _td("-# This is a simulation  ·  SkyHighEV Economy"),
    ))
    await asyncio.sleep(2.0)

    r = _random.random()
    cumulative = 0.0
    chosen = _HACK_SCENARIOS[-1]
    for scenario in _HACK_SCENARIOS:
        cumulative += scenario[1]
        if r < cumulative:
            chosen = scenario
            break

    outcome, _, desc, amt_min, amt_max = chosen
    db = _load_economy()
    bal = _get_balance(ctx.author.id, db)

    if outcome == "SUCCESS":
        steal = _random.randint(amt_min, amt_max)
        _add_coins(ctx.author.id, steal, db)
        _save_economy(db)
        new_bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=_cv2(C_SUCCESS,
            _td("## \U0001f5a5\ufe0f  Hack Successful!"),
            _sep(),
            _td(
                f"**Target system:** `{desc.upper()}`\n"
                f"You slipped through undetected and looted the vault."
            ),
            _sep(),
            _td(
                f"**Stolen:** +{steal:,} \U0001fa99\n"
                f"**New Balance:** {new_bal:,} \U0001fa99"
            ),
            _td("-# Next hack available in 1 hour  ·  SkyHighEV Economy"),
        ))
    elif outcome == "CAUGHT":
        fine = _random.randint(amt_min, min(amt_max, bal))
        fine = max(fine, 0)
        _deduct_coins(ctx.author.id, fine, db)
        _save_economy(db)
        new_bal = _get_balance(ctx.author.id, db)
        cop_lines = [
            "\U0001f6a8  **POLICE DETECTED YOU!**  \U0001f6a8",
            f"**Reason:** {desc.upper()}",
            "",
            f"**Fine issued:** -{fine:,} \U0001fa99",
            f"**New Balance:** {new_bal:,} \U0001fa99",
        ]
        await ctx.send(view=_cv2(C_ERROR,
            _td("## \U0001f5a5\ufe0f  Hack Failed — Busted!"),
            _sep(),
            _td("\n".join(cop_lines)),
            _td("-# Next hack available in 1 hour  ·  SkyHighEV Economy"),
        ))
    else:
        await ctx.send(view=_cv2(C_WARN,
            _td("## \U0001f5a5\ufe0f  Hack Failed — No Result"),
            _sep(),
            _td(
                f"**Reason:** {desc.upper()}\n"
                f"You escaped without profit — or penalty."
            ),
            _sep(),
            _td(f"**Balance:** {bal:,} \U0001fa99"),
            _td("-# Next hack available in 1 hour  ·  SkyHighEV Economy"),
        ))


# ── crash game ─────────────────────────────────────────────────────────────────

def _crash_point() -> float:
    r = _random.random()
    if r < 0.35: return round(_random.uniform(1.01, 1.50), 2)
    if r < 0.58: return round(_random.uniform(1.50, 2.50), 2)
    if r < 0.75: return round(_random.uniform(2.50, 5.00), 2)
    if r < 0.88: return round(_random.uniform(5.00, 10.0), 2)
    if r < 0.95: return round(_random.uniform(10.0, 25.0), 2)
    return round(_random.uniform(25.0, 50.0), 2)

def _crash_bar(current: float, scale: float) -> str:
    BAR_LEN = 22
    pct    = min(current / max(scale, current + 0.01), 1.0)
    filled = int(BAR_LEN * pct)
    bar    = "\u2588" * filled + "\u2591" * (BAR_LEN - filled)
    return f"`[ {bar} ]`  x{current:.2f}"

class CrashGameLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, bet: int):
        super().__init__(timeout=180)
        self.author_id    = author_id
        self.bet          = bet
        self.crash_point  = _crash_point()
        self.current_mult = 1.00
        self.cashed_out   = False
        self.crashed      = False
        self._msg         = None
        self._task        = None
        self._lock        = asyncio.Lock()
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        if self.crashed:
            self.add_item(_cv2_cont(
                _td("## Crash"),
                _sep(),
                _td(f"\u274c  **Crashed at x{self.crash_point:.2f}!**"),
                _sep(),
                _td(_crash_bar(self.crash_point, self.crash_point + 1)),
                _sep(),
                _td(
                    f"**Bet:** {self.bet:,} \U0001fa99\n"
                    f"**Lost:** -{self.bet:,} \U0001fa99"
                ),
                _td("-# Better luck next time  ·  SkyHighEV Economy"),
                color=C_ERROR,
            ))
        elif self.cashed_out:
            winnings = int(self.bet * self.current_mult)
            net      = winnings - self.bet
            self.add_item(_cv2_cont(
                _td("## Crash"),
                _sep(),
                _td(f"\u2705  **Cashed out at x{self.current_mult:.2f}!**"),
                _sep(),
                _td(_crash_bar(self.current_mult, max(self.current_mult * 1.3, 2))),
                _sep(),
                _td(
                    f"**Bet:** {self.bet:,} \U0001fa99\n"
                    f"**Won:** +{winnings:,} \U0001fa99\n"
                    f"**Net:** +{net:,} \U0001fa99"
                ),
                _td("-# Nice timing!  ·  SkyHighEV Economy"),
                color=C_SUCCESS,
            ))
        else:
            cashout_btn = discord.ui.Button(
                label=f"Cash Out \u2014 x{self.current_mult:.2f}",
                style=discord.ButtonStyle.success,
                custom_id="crash_cashout",
            )
            cashout_btn.callback = self._do_cashout
            scale = max(self.crash_point * 0.8, self.current_mult + 2)
            self.add_item(_cv2_cont(
                _td("## Crash"),
                _sep(),
                _td(f"\U0001f680  **Flying at x{self.current_mult:.2f}** \u2014 Cash out before it crashes!"),
                _sep(),
                _td(_crash_bar(self.current_mult, scale)),
                _sep(),
                _td(f"**Bet:** {self.bet:,} \U0001fa99"),
                _td("-# Click Cash Out before the rocket crashes!  ·  SkyHighEV"),
                discord.ui.ActionRow(cashout_btn),
                color=C_SUCCESS,
            ))

    async def _do_cashout(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        async with self._lock:
            if self.crashed or self.cashed_out:
                await interaction.response.defer()
                return
            self.cashed_out = True
            if self._task:
                self._task.cancel()
            winnings = int(self.bet * self.current_mult)
            db = _load_economy()
            _add_coins(self.author_id, winnings, db)
            _save_economy(db)
        self._rebuild()
        await interaction.response.edit_message(content=None, embeds=[], attachments=[], view=self)

    async def start_ticking(self):
        self._task = asyncio.get_event_loop().create_task(self._tick())

    async def _tick(self):
        step = 0.06
        try:
            while not self.crashed and not self.cashed_out:
                await asyncio.sleep(1.4)
                async with self._lock:
                    if self.cashed_out:
                        break
                    self.current_mult = round(self.current_mult + step, 2)
                    step = round(step * 1.07, 3)
                    if self.current_mult >= self.crash_point:
                        self.current_mult = self.crash_point
                        self.crashed      = True
                self._rebuild()
                if self._msg:
                    try:
                        await self._msg.edit(content=None, embeds=[], attachments=[], view=self)
                    except Exception:
                        pass
                if self.crashed:
                    break
        except asyncio.CancelledError:
            pass


@bot.command(name="crash", aliases=["cr"])
async def prefix_crash(ctx: commands.Context, bet: int = 0):
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Bet",
            "Minimum bet is **10** \U0001fa99.\nUsage: `!crash <bet>`"))
        return
    if bet > 10_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is **10,000** \U0001fa99."))
        return
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds",
            f"Need **{bet:,}** \U0001fa99 but have **{bal:,}** \U0001fa99."))
        return
    _save_economy(db)
    layout      = CrashGameLayout(ctx.author.id, bet)
    msg         = await ctx.send(view=layout)
    layout._msg = msg
    await layout.start_ticking()


# ── rock paper scissors ────────────────────────────────────────────────────────

_RPS_CHOICES = {
    "rock":     ("\U0001faa8", "ROCK"),
    "paper":    ("\U0001f4c4", "PAPER"),
    "scissors": ("\u2702\ufe0f", "SCISSORS"),
    "r":        ("\U0001faa8", "ROCK"),
    "p":        ("\U0001f4c4", "PAPER"),
    "s":        ("\u2702\ufe0f", "SCISSORS"),
}
_RPS_BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
_RPS_CANONICAL = {"r": "rock", "p": "paper", "s": "scissors",
                  "rock": "rock", "paper": "paper", "scissors": "scissors"}

@bot.command(name="rps", aliases=["rockpaperscissors"])
async def prefix_rps(ctx: commands.Context, bet: int = 0, choice: str = ""):
    choice = choice.lower()
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Usage",
            "Usage: `!rps <bet> <rock/paper/scissors>`\nMinimum bet is **10** \U0001fa99."))
        return
    if bet > 15_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is **15,000** \U0001fa99."))
        return
    if choice not in _RPS_CHOICES:
        await ctx.send(view=cv2_err("Invalid Choice",
            "Choose `rock`, `paper`, or `scissors`.\nAliases: `r`, `p`, `s`."))
        return

    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds",
            f"Need **{bet:,}** \U0001fa99 but have **{bal:,}** \U0001fa99."))
        return

    player_key  = _RPS_CANONICAL[choice]
    bot_key     = _random.choice(["rock", "paper", "scissors"])
    p_emoji, p_label = _RPS_CHOICES[player_key]
    b_emoji, b_label = _RPS_CHOICES[bot_key]
    name = ctx.author.display_name

    if player_key == bot_key:
        result = "tie"
        _add_coins(ctx.author.id, bet, db)
        _save_economy(db)
        new_bal  = _get_balance(ctx.author.id, db)
        outcome_line = "\U0001f91d  **It's a Tie!**\nYour bet has been returned."
        net_line     = f"**Returned:** {bet:,} \U0001fa99"
        color = C_WARN
    elif _RPS_BEATS[player_key] == bot_key:
        result   = "win"
        winnings = bet * 2
        _add_coins(ctx.author.id, winnings, db)
        _save_economy(db)
        new_bal      = _get_balance(ctx.author.id, db)
        outcome_line = "\U0001f3c6  **You Win!**\nYou beat the bot!"
        net_line     = f"**Won:** +{bet:,} \U0001fa99"
        color = C_SUCCESS
    else:
        result  = "lose"
        _save_economy(db)
        new_bal     = _get_balance(ctx.author.id, db)
        outcome_line = "\U0001f62d  **You Lose!**\nYou lost your bet."
        net_line     = f"**Lost:** -{bet:,} \U0001fa99"
        color = C_ERROR

    await ctx.send(view=_cv2(color,
        _td("## Rock Paper Scissors"),
        _sep(),
        _td(
            f"**{name}** chose {p_emoji} **{p_label}**\n"
            f"**Bot** chose {b_emoji} **{b_label}**"
        ),
        _sep(),
        _td(outcome_line),
        _sep(),
        _td(
            f"{net_line}\n"
            f"**Balance:** {new_bal:,} \U0001fa99"
        ),
        _td("-# SkyHighEV Economy"),
    ))


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRA ECONOMY — earning, bank, transfers, shop, lottery, lootbox, profile
# ══════════════════════════════════════════════════════════════════════════════

_fish_cooldowns:  dict = {}
_hunt_cooldowns:  dict = {}
_crime_cooldowns: dict = {}
_crate_cooldowns: dict = {}

FISH_COOLDOWN_SECONDS  = 600     # 10 min
HUNT_COOLDOWN_SECONDS  = 900     # 15 min
CRIME_COOLDOWN_SECONDS = 1800    # 30 min
CRATE_COOLDOWN_SECONDS = 21600   # 6 h free crate
BANK_INTEREST_PER_DAY  = 0.02    # 2% / day on bank balance
BANK_DEPOSIT_FEE_PCT   = 0.25    # 25% bank fee on deposit
BANK_WITHDRAW_FEE_PCT  = 0.10    # 10% bank fee on withdrawal
TRANSFER_TAX_PCT       = 0.05    # 5% tax on :-:pay
LOTTERY_TICKET_PRICE   = 200
LOTTERY_DRAW_INTERVAL  = 21600   # 6 h
HISTORY_KEEP           = 25

_FISH_CATCHES = [
    (" salmon",      120, 280),
    (" goldfish",    50,  150),
    (" pufferfish",  200, 420),
    (" octopus",     250, 500),
    (" shrimp",      40,  120),
    (" tuna",        150, 350),
    (" rare koi",    400, 800),
    (" rusty boot",  5,   30),
    (" tropical fish",100, 260),
]

_HUNT_CATCHES = [
    (" rabbit",     150, 320),
    (" deer",       300, 600),
    (" wild boar",  250, 500),
    (" pheasant",   180, 380),
    (" wolf pelt",  400, 750),
    (" rare fox",   500, 950),
    (" duck",       120, 280),
    (" empty trap", 0,   0),
]

_CRIMES = [
    ("pickpocketed a tourist",    300, 700,  0.65),
    ("robbed a small store",      500, 1100, 0.55),
    ("hacked an ATM",             900, 2000, 0.40),
    ("stole a luxury car",        1200, 2800, 0.35),
    ("broke into a mansion",      1500, 3500, 0.30),
    ("ran an online scam",        400, 1000, 0.60),
]

_SHOP_ITEMS = {
    "fishingrod": {"name": " Fishing Rod",      "price": 2500,  "desc": "+25% fish payout (permanent)"},
    "rifle":       {"name": " Hunting Rifle",     "price": 4000,  "desc": "+30% hunt payout (permanent)"},
    "lockpick":    {"name": " Lockpick Set",      "price": 3000,  "desc": "+10% crime success rate (permanent)"},
    "vault":       {"name": " Bank Vault Upgrade","price": 10000, "desc": "+50% bank interest (permanent)"},
    "luckycharm":  {"name": " Lucky Charm",       "price": 6000,  "desc": "+5% luck on all gambling (permanent)"},
}

_CRATE_REWARDS = [
    ("Common",     "common",    50,    300,   55),
    ("Uncommon",   "uncommon",  300,   800,   25),
    ("Rare",       "rare",      800,   2000,  12),
    ("Epic",       "epic",      2000,  5000,  6),
    ("Legendary",  "legend",    5000,  15000, 2),
]

_ROULETTE_RED   = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
_ROULETTE_BLACK = {2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _inv_get(db: dict, uid) -> dict:
    return db.setdefault("inventory", {}).setdefault(str(uid), {})

def _inv_has(db: dict, uid, item_id: str) -> bool:
    return _inv_get(db, uid).get(item_id, 0) > 0

def _log_tx(db: dict, uid, label: str, delta: int):
    hist = db.setdefault("history", {}).setdefault(str(uid), [])
    hist.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "delta": delta,
    })
    if len(hist) > HISTORY_KEEP:
        del hist[:-HISTORY_KEEP]

def _bank_get(db: dict, uid) -> int:
    return db.setdefault("bank", {}).get(str(uid), 0)

def _bank_set(db: dict, uid, amount: int):
    db.setdefault("bank", {})[str(uid)] = max(0, int(amount))

def _apply_bank_interest(db: dict, uid) -> int:
    sid = str(uid)
    last_map = db.setdefault("bank_last_interest", {})
    now = datetime.now(timezone.utc)
    last_iso = last_map.get(sid)
    bank = _bank_get(db, uid)
    if bank <= 0:
        last_map[sid] = now.isoformat()
        return 0
    if not last_iso:
        last_map[sid] = now.isoformat()
        return 0
    try:
        last = datetime.fromisoformat(last_iso)
    except Exception:
        last_map[sid] = now.isoformat()
        return 0
    days = (now - last).total_seconds() / 86400.0
    if days <= 0:
        return 0
    rate = BANK_INTEREST_PER_DAY * (1.5 if _inv_has(db, uid, "vault") else 1.0)
    gained = int(bank * rate * days)
    if gained > 0:
        _bank_set(db, uid, bank + gained)
        last_map[sid] = now.isoformat()
        _log_tx(db, uid, " Bank Interest", gained)
    return gained

def _luck_bonus(db: dict, uid) -> float:
    return 0.05 if _inv_has(db, uid, "luckycharm") else 0.0

# ── :-:fish ──────────────────────────────────────────────────────────────────

@bot.command(name="fish", aliases=["fishing"])
async def prefix_fish(ctx: commands.Context):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _fish_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("Cooldown", f"Cast your line again <t:{int(cd.timestamp())}:R>."))
        return
    catch, mn, mx = _random.choice(_FISH_CATCHES)
    earned = _random.randint(mn, mx)
    db = _load_economy()
    if _inv_has(db, ctx.author.id, "fishingrod"):
        earned = int(earned * 1.25)
    _add_coins(ctx.author.id, earned, db)
    _log_tx(db, ctx.author.id, f"Fishing — {catch}", earned)
    _save_economy(db)
    _fish_cooldowns[sid] = now + timedelta(seconds=FISH_COOLDOWN_SECONDS)
    new_bal = _get_balance(ctx.author.id, db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Gone Fishing!"),
        _sep(),
        _td(f"You caught a **{catch.strip()}** and sold it for **{earned:,}** !\n\n"
            f"**Balance:** {new_bal:,}  ·  **Next Cast:** <t:{int(_fish_cooldowns[sid].timestamp())}:R>"),
    ))

# ── :-:hunt ──────────────────────────────────────────────────────────────────

@bot.command(name="hunt", aliases=["hunting"])
async def prefix_hunt(ctx: commands.Context):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _hunt_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("Cooldown", f"Track again <t:{int(cd.timestamp())}:R>."))
        return
    catch, mn, mx = _random.choice(_HUNT_CATCHES)
    earned = _random.randint(mn, mx) if mx > 0 else 0
    db = _load_economy()
    if _inv_has(db, ctx.author.id, "rifle") and earned > 0:
        earned = int(earned * 1.30)
    if earned > 0:
        _add_coins(ctx.author.id, earned, db)
    _log_tx(db, ctx.author.id, f"Hunting — {catch}", earned)
    _save_economy(db)
    _hunt_cooldowns[sid] = now + timedelta(seconds=HUNT_COOLDOWN_SECONDS)
    new_bal = _get_balance(ctx.author.id, db)
    if earned > 0:
        await ctx.send(view=_cv2(C_SUCCESS,
            _td("##  Hunt Successful"),
            _sep(),
            _td(f"You caught a **{catch.strip()}** worth **{earned:,}** !\n\n"
                f"**Balance:** {new_bal:,}  ·  **Next Hunt:** <t:{int(_hunt_cooldowns[sid].timestamp())}:R>"),
        ))
    else:
        await ctx.send(view=_cv2(C_WARN,
            _td("##  No Luck"),
            _sep(),
            _td(f"Your trap was **empty** this time.\n\n"
                f"**Balance:** {new_bal:,}  ·  **Next Hunt:** <t:{int(_hunt_cooldowns[sid].timestamp())}:R>"),
        ))

# ── :-:crime ─────────────────────────────────────────────────────────────────

@bot.command(name="crime", aliases=["criminal"])
async def prefix_crime(ctx: commands.Context):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _crime_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("Lay Low", f"The cops are watching. Try again <t:{int(cd.timestamp())}:R>."))
        return
    desc, mn, mx, success_rate = _random.choice(_CRIMES)
    db = _load_economy()
    if _inv_has(db, ctx.author.id, "lockpick"):
        success_rate += 0.10
    success_rate += _luck_bonus(db, ctx.author.id)
    success = _random.random() < success_rate
    if success:
        gained = _random.randint(mn, mx)
        _add_coins(ctx.author.id, gained, db)
        _log_tx(db, ctx.author.id, f"Crime — {desc}", gained)
        _save_economy(db)
        _crime_cooldowns[sid] = now + timedelta(seconds=CRIME_COOLDOWN_SECONDS)
        new_bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=_cv2(C_SUCCESS,
            _td("##  Crime Pays!"),
            _sep(),
            _td(f"You **{desc}** and got away with **{gained:,}** !\n\n"
                f"**Balance:** {new_bal:,}  ·  **Cooldown:** <t:{int(_crime_cooldowns[sid].timestamp())}:R>"),
        ))
    else:
        fine = _random.randint(mn // 2, mx // 2)
        bal = _get_balance(ctx.author.id, db)
        actual = min(bal, fine)
        if actual > 0:
            _deduct_coins(ctx.author.id, actual, db)
        _log_tx(db, ctx.author.id, f"Crime FAIL — {desc}", -actual)
        _save_economy(db)
        _crime_cooldowns[sid] = now + timedelta(seconds=CRIME_COOLDOWN_SECONDS)
        new_bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=_cv2(C_ERROR,
            _td("##  Caught!"),
            _sep(),
            _td(f"You tried to **{desc}** but got caught!\n"
                f"**Fine:** -{actual:,} \n\n"
                f"**Balance:** {new_bal:,}  ·  **Cooldown:** <t:{int(_crime_cooldowns[sid].timestamp())}:R>"),
        ))

# ── :-:bank / :-:deposit / :-:bankwithdraw ───────────────────────────────────

@bot.command(name="bank", aliases=["b"])
async def prefix_bank(ctx: commands.Context, user: discord.Member = None):
    target = user or ctx.author
    db = _load_economy()
    gained = _apply_bank_interest(db, target.id) if target.id == ctx.author.id else 0
    _save_economy(db)
    bal  = _get_balance(target.id, db)
    bank = _bank_get(db, target.id)
    own  = target.id == ctx.author.id
    who  = "Your" if own else f"{target.display_name}'s"
    rate_pct = int(BANK_INTEREST_PER_DAY * (1.5 if _inv_has(db, target.id, "vault") else 1.0) * 100)
    kids = [
        _td(f"## {who} Bank"),
        _sep(),
        _td(f"**Wallet:** {bal:,} \n**Bank:**   {bank:,} \n**Total:**  {bal+bank:,} "),
        _td(f"-# Interest: **{rate_pct}% / day**  ·  Bank coins are safe from robberies"),
    ]
    if gained > 0:
        kids.insert(2, _td(f" Earned **+{gained:,}** in interest since last visit."))
    await ctx.send(view=_cv2(C_GOLD, *kids))

@bot.command(name="deposit", aliases=["dep"])
async def prefix_deposit(ctx: commands.Context, amount: str = ""):
    db  = _load_economy()
    bal = _get_balance(ctx.author.id, db)
    if amount.lower() in ("all", "max"):
        amt = bal
    else:
        try: amt = int(amount.replace(",", ""))
        except: amt = 0
    if amt <= 0:
        await ctx.send(view=cv2_err("Invalid Amount", "Usage: `!deposit <amount|all>`"))
        return
    if amt > bal:
        await ctx.send(view=cv2_err("Insufficient Funds", f"You only have **{bal:,}** in your wallet."))
        return
    _apply_bank_interest(db, ctx.author.id)
    fee     = int(amt * BANK_DEPOSIT_FEE_PCT)
    credited = amt - fee
    _deduct_coins(ctx.author.id, amt, db)
    _bank_set(db, ctx.author.id, _bank_get(db, ctx.author.id) + credited)
    _log_tx(db, ctx.author.id, f" Deposit (fee {fee:,})", -amt)
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Deposit Complete"),
        _sep(),
        _td(f"You deposited **{amt:,}** \n"
            f" **Bank Fee ({int(BANK_DEPOSIT_FEE_PCT*100)}%):** -{fee:,} \n"
            f" **Credited to Bank:** **+{credited:,}** \n\n"
            f"**Wallet:** {_get_balance(ctx.author.id, db):,}  ·  **Bank:** {_bank_get(db, ctx.author.id):,} "),
    ))

@bot.command(name="bankwithdraw", aliases=["bw", "wbank"])
async def prefix_bankwithdraw(ctx: commands.Context, amount: str = ""):
    db   = _load_economy()
    _apply_bank_interest(db, ctx.author.id)
    bank = _bank_get(db, ctx.author.id)
    if amount.lower() in ("all", "max"):
        amt = bank
    else:
        try: amt = int(amount.replace(",", ""))
        except: amt = 0
    if amt <= 0:
        await ctx.send(view=cv2_err("Invalid Amount", "Usage: `!bankwithdraw <amount|all>`"))
        return
    if amt > bank:
        await ctx.send(view=cv2_err("Insufficient Bank", f"Your bank only holds **{bank:,}** ."))
        return
    fee     = int(amt * BANK_WITHDRAW_FEE_PCT)
    payout  = amt - fee
    _bank_set(db, ctx.author.id, bank - amt)
    _add_coins(ctx.author.id, payout, db)
    _log_tx(db, ctx.author.id, f" Bank Withdraw (fee {fee:,})", payout)
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Bank Withdrawal"),
        _sep(),
        _td(f"You withdrew **{amt:,}**  from your bank\n"
            f" **Bank Fee ({int(BANK_WITHDRAW_FEE_PCT*100)}%):** -{fee:,} \n"
            f" **You received:** **+{payout:,}** \n\n"
            f"**Wallet:** {_get_balance(ctx.author.id, db):,}  ·  **Bank:** {_bank_get(db, ctx.author.id):,} "),
    ))

# ── :-:pay (transfer with tax) ───────────────────────────────────────────────

@bot.command(name="pay", aliases=["gift", "send", "transfer"])
async def prefix_pay(ctx: commands.Context, user: discord.Member = None, amount: int = 0):
    if not user:
        await ctx.send(view=cv2_err("Missing User", "Usage: `!pay @user <amount>`"))
        return
    if user.id == ctx.author.id:
        await ctx.send(view=cv2_err("Invalid", "You can't pay yourself."))
        return
    if user.bot:
        await ctx.send(view=cv2_err("Invalid", "You can't pay a bot."))
        return
    if amount < 10:
        await ctx.send(view=cv2_err("Invalid Amount", "Minimum transfer is **10** ."))
        return
    db   = _load_economy()
    _apply_bank_interest(db, ctx.author.id)
    bal  = _get_balance(ctx.author.id, db)
    bank = _bank_get(db, ctx.author.id)
    total_avail = bal + bank
    if amount > total_avail:
        await ctx.send(view=cv2_err("Insufficient Funds",
            f"Need **{amount:,}**  but you only have **{bal:,}**  in wallet "
            f"and **{bank:,}**  in bank (total: **{total_avail:,}** )."))
        return
    from_bank = 0
    if bal >= amount:
        _deduct_coins(ctx.author.id, amount, db)
    else:
        from_bank = amount - bal
        if bal > 0:
            _deduct_coins(ctx.author.id, bal, db)
        _bank_set(db, ctx.author.id, bank - from_bank)
    tax       = int(amount * TRANSFER_TAX_PCT)
    received  = amount - tax
    _add_coins(user.id, received, db)
    src_line = (f"From wallet: **{amount - from_bank:,}**  ·  From bank: **{from_bank:,}** \n"
                if from_bank > 0 else "")
    _log_tx(db, ctx.author.id, f" Sent to {user.display_name}", -amount)
    _log_tx(db, user.id,        f" Received from {ctx.author.display_name}", received)
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Transfer Complete"),
        _sep(),
        _td(f"You sent **{amount:,}**  to {user.mention}\n"
            f"{src_line}"
            f" **Tax:** -{tax:,}  ({int(TRANSFER_TAX_PCT*100)}%)\n"
            f" **They received:** **{received:,}** \n\n"
            f"**Your Wallet:** {_get_balance(ctx.author.id, db):,}   ·  "
            f"**Your Bank:** {_bank_get(db, ctx.author.id):,} "),
    ))

# ── :-:roulette ──────────────────────────────────────────────────────────────

@bot.command(name="roulette", aliases=["rl", "roul"])
async def prefix_roulette(ctx: commands.Context, bet: int = 0, choice: str = ""):
    choice = choice.lower().strip()
    if bet < 10:
        await ctx.send(view=cv2_err("Invalid Bet",
            "Usage: `!roulette <bet> <red/black/green/odd/even/0-36>`\nMinimum bet is **10** ."))
        return
    if bet > 25_000:
        await ctx.send(view=cv2_err("Invalid Bet", "Maximum bet is **25,000** ."))
        return
    is_number = choice.isdigit() and 0 <= int(choice) <= 36
    if choice not in ("red","r","black","b","green","g","odd","o","even","e") and not is_number:
        await ctx.send(view=cv2_err("Invalid Choice",
            "Choose `red`, `black`, `green`, `odd`, `even`, or a number `0-36`."))
        return
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, bet, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{bet:,}**  but have **{bal:,}** ."))
        return
    spun = _random.randint(0, 36)
    if spun == 0:    color_name, emoji = "GREEN", ""
    elif spun in _ROULETTE_RED:   color_name, emoji = "RED", ""
    else:                          color_name, emoji = "BLACK", ""
    payout = 0
    if is_number and int(choice) == spun:
        payout = bet * 35
    elif choice in ("red","r") and color_name == "RED":
        payout = bet * 2
    elif choice in ("black","b") and color_name == "BLACK":
        payout = bet * 2
    elif choice in ("green","g") and color_name == "GREEN":
        payout = bet * 14
    elif choice in ("odd","o") and spun != 0 and spun % 2 == 1:
        payout = bet * 2
    elif choice in ("even","e") and spun != 0 and spun % 2 == 0:
        payout = bet * 2
    won = payout > 0
    if won:
        _add_coins(ctx.author.id, payout, db)
    _log_tx(db, ctx.author.id, f" Roulette {choice}", (payout - bet) if won else -bet)
    _save_economy(db)
    title = " WIN!" if won else " LOSE"
    net   = payout - bet
    await ctx.send(view=_cv2(C_SUCCESS if won else C_ERROR,
        _td(f"## Roulette — {title}"),
        _sep(),
        _td(f"The wheel landed on {emoji} **{spun} {color_name}**\n"
            f"You bet on **{choice.upper()}**\n\n"
            f"**Bet:** {bet:,}  ·  **Payout:** {payout:,}  ·  **Net:** {'+' if net>=0 else ''}{net:,}"),
    ))

# ── :-:lottery ───────────────────────────────────────────────────────────────

def _lottery_state(db: dict) -> dict:
    lot = db.setdefault("lottery", {
        "pot": 0, "tickets": {}, "next_draw": None, "last_winner": None,
    })
    if not lot.get("next_draw"):
        lot["next_draw"] = (datetime.now(timezone.utc) + timedelta(seconds=LOTTERY_DRAW_INTERVAL)).isoformat()
    return lot

def _maybe_draw_lottery(db: dict) -> dict | None:
    lot = _lottery_state(db)
    try:
        nd = datetime.fromisoformat(lot["next_draw"])
    except Exception:
        nd = datetime.now(timezone.utc) + timedelta(seconds=LOTTERY_DRAW_INTERVAL)
        lot["next_draw"] = nd.isoformat()
        return None
    if datetime.now(timezone.utc) < nd:
        return None
    tickets = lot.get("tickets", {})
    pool = []
    for uid, count in tickets.items():
        pool += [uid] * int(count)
    result = None
    if pool:
        winner = _random.choice(pool)
        prize  = lot.get("pot", 0)
        if prize > 0:
            _add_coins(winner, prize, db)
            _log_tx(db, winner, " Lottery Jackpot", prize)
        result = {"winner": winner, "prize": prize, "tickets": sum(tickets.values())}
        lot["last_winner"] = result
    lot["pot"] = 0
    lot["tickets"] = {}
    lot["next_draw"] = (datetime.now(timezone.utc) + timedelta(seconds=LOTTERY_DRAW_INTERVAL)).isoformat()
    return result

@bot.command(name="lottery", aliases=["lotto"])
async def prefix_lottery(ctx: commands.Context, action: str = "info", amount: str = "1"):
    db  = _load_economy()
    drew = _maybe_draw_lottery(db)
    lot  = _lottery_state(db)
    sid  = str(ctx.author.id)
    action = action.lower()
    extra_lines = []
    if drew:
        try:
            wu = bot.get_user(int(drew["winner"])) or await bot.fetch_user(int(drew["winner"]))
            wname = wu.display_name
        except Exception:
            wname = f"User {drew['winner'][:6]}"
        extra_lines.append(f" **Last Draw:** {wname} won **{drew['prize']:,}**  with {drew['tickets']} ticket(s)!")
    if action in ("buy", "ticket", "tickets"):
        try: n = int(amount)
        except: n = 1
        if n < 1 or n > 50:
            await ctx.send(view=cv2_err("Invalid", "Buy between 1 and 50 tickets."))
            return
        cost = n * LOTTERY_TICKET_PRICE
        if not _deduct_coins(ctx.author.id, cost, db):
            bal = _get_balance(ctx.author.id, db)
            await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{cost:,}**  but have **{bal:,}** ."))
            return
        lot["pot"] = lot.get("pot", 0) + cost
        lot.setdefault("tickets", {})[sid] = lot["tickets"].get(sid, 0) + n
        _log_tx(db, ctx.author.id, f" Lottery Tickets x{n}", -cost)
        _save_economy(db)
        my   = lot["tickets"][sid]
        tot  = sum(lot["tickets"].values())
        odds = (my / tot) * 100 if tot else 0
        nd   = int(datetime.fromisoformat(lot["next_draw"]).timestamp())
        await ctx.send(view=_cv2(C_SUCCESS,
            _td("##  Lottery Tickets Purchased"),
            _sep(),
            _td(f"You bought **{n}** ticket(s) for **{cost:,}** !\n\n"
                f"**Your Tickets:** {my}  ·  **Total Tickets:** {tot}\n"
                f"**Win Odds:** {odds:.1f}%  ·  **Jackpot:** {lot['pot']:,} \n"
                f"**Next Draw:** <t:{nd}:R>"),
        ))
        return
    _save_economy(db)
    my   = lot.get("tickets", {}).get(sid, 0)
    tot  = sum(lot.get("tickets", {}).values())
    odds = (my / tot) * 100 if tot else 0
    nd   = int(datetime.fromisoformat(lot["next_draw"]).timestamp())
    kids = [
        _td("##  Lottery"),
        _sep(),
        _td(f" **Jackpot:** {lot.get('pot',0):,} \n"
            f" **Total Tickets:** {tot}\n"
            f" **Your Tickets:** {my}  ({odds:.1f}% win odds)\n"
            f" **Next Draw:** <t:{nd}:R>\n"
            f" **Ticket Price:** {LOTTERY_TICKET_PRICE:,} \n\n"
            f"Use `!lottery buy <amount>` to enter."),
    ]
    if extra_lines:
        kids.append(_sep())
        kids.append(_td("\n".join(extra_lines)))
    await ctx.send(view=_cv2(C_GOLD, *kids))

# ── :-:shop / :-:buy / :-:inventory ──────────────────────────────────────────

@bot.command(name="shop", aliases=["store"])
async def prefix_shop(ctx: commands.Context):
    lines = []
    for iid, it in _SHOP_ITEMS.items():
        lines.append(f"`{iid}` — {it['name']} — **{it['price']:,}** \n  {it['desc']}")
    await ctx.send(view=_cv2(C_GOLD,
        _td("##  Shop"),
        _sep(),
        _td("\n\n".join(lines)),
        _td("-# Buy with `!buy <item_id>`  ·  View owned with `!inventory`"),
    ))

@bot.command(name="buy", aliases=["purchase"])
async def prefix_buy(ctx: commands.Context, item_id: str = ""):
    item_id = item_id.lower().strip()
    if item_id not in _SHOP_ITEMS:
        await ctx.send(view=cv2_err("Invalid Item",
            f"Unknown item. Use `!shop` to see available items."))
        return
    it = _SHOP_ITEMS[item_id]
    db = _load_economy()
    if _inv_has(db, ctx.author.id, item_id):
        await ctx.send(view=cv2_err("Already Owned", f"You already own **{it['name']}**."))
        return
    if not _deduct_coins(ctx.author.id, it["price"], db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{it['price']:,}**  but have **{bal:,}** ."))
        return
    inv = _inv_get(db, ctx.author.id)
    inv[item_id] = inv.get(item_id, 0) + 1
    _log_tx(db, ctx.author.id, f" Bought {it['name']}", -it["price"])
    _save_economy(db)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Purchase Complete"),
        _sep(),
        _td(f"You bought **{it['name']}**!\n{it['desc']}\n\n"
            f"**Spent:** -{it['price']:,}   ·  **Balance:** {_get_balance(ctx.author.id, db):,} "),
    ))

@bot.command(name="inventory", aliases=["inv", "items"])
async def prefix_inventory(ctx: commands.Context, user: discord.Member = None):
    target = user or ctx.author
    db  = _load_economy()
    inv = _inv_get(db, target.id)
    own = target.id == ctx.author.id
    who = "Your" if own else f"{target.display_name}'s"
    if not inv:
        await ctx.send(view=_cv2(C_INFO,
            _td(f"## {who} Inventory"),
            _sep(),
            _td(f"{'Your' if own else 'Their'} backpack is empty.\nUse `!shop` to buy items."),
        ))
        return
    lines = []
    for iid, qty in inv.items():
        if iid in _SHOP_ITEMS:
            lines.append(f"{_SHOP_ITEMS[iid]['name']} ×{qty}\n  {_SHOP_ITEMS[iid]['desc']}")
        else:
            lines.append(f"`{iid}` ×{qty}")
    await ctx.send(view=_cv2(C_GOLD,
        _td(f"## {who} Inventory"),
        _sep(),
        _td("\n\n".join(lines)),
    ))

# ── :-:crate / :-:lootbox ────────────────────────────────────────────────────

def _roll_crate() -> tuple:
    weights = [r[4] for r in _CRATE_REWARDS]
    return _random.choices(_CRATE_REWARDS, weights=weights, k=1)[0]

@bot.command(name="crate", aliases=["lootbox", "box"])
async def prefix_crate(ctx: commands.Context):
    sid = str(ctx.author.id)
    now = datetime.now(timezone.utc)
    cd  = _crate_cooldowns.get(sid)
    if cd and now < cd:
        await ctx.send(view=cv2_err("Cooldown", f"Next free crate <t:{int(cd.timestamp())}:R>.\nUse `!buycrate` to buy one for 500 ."))
        return
    name, _key, mn, mx, _w = _roll_crate()
    reward = _random.randint(mn, mx)
    db = _load_economy()
    _add_coins(ctx.author.id, reward, db)
    _log_tx(db, ctx.author.id, f" {name} Crate", reward)
    _save_economy(db)
    _crate_cooldowns[sid] = now + timedelta(seconds=CRATE_COOLDOWN_SECONDS)
    await ctx.send(view=_cv2(C_SUCCESS,
        _td("##  Free Crate Opened!"),
        _sep(),
        _td(f"You got a **{name}** crate!\n **Reward:** +{reward:,} \n\n"
            f"**Balance:** {_get_balance(ctx.author.id, db):,}  ·  **Next Free:** <t:{int(_crate_cooldowns[sid].timestamp())}:R>"),
    ))

@bot.command(name="buycrate", aliases=["openbox"])
async def prefix_buycrate(ctx: commands.Context):
    PRICE = 500
    db = _load_economy()
    if not _deduct_coins(ctx.author.id, PRICE, db):
        bal = _get_balance(ctx.author.id, db)
        await ctx.send(view=cv2_err("Insufficient Funds", f"Need **{PRICE:,}**  but have **{bal:,}** ."))
        return
    name, _key, mn, mx, _w = _roll_crate()
    reward = _random.randint(mn, mx)
    _add_coins(ctx.author.id, reward, db)
    _log_tx(db, ctx.author.id, f" Bought {name} Crate", reward - PRICE)
    _save_economy(db)
    net = reward - PRICE
    await ctx.send(view=_cv2(C_SUCCESS if net > 0 else C_WARN,
        _td("##  Crate Opened!"),
        _sep(),
        _td(f"You opened a **{name}** crate!\n"
            f" **Reward:** +{reward:,}   ·   **Cost:** -{PRICE:,} \n"
            f" **Net:** {'+' if net>=0 else ''}{net:,} \n\n"
            f"**Balance:** {_get_balance(ctx.author.id, db):,} "),
    ))

# ── :-:profile ───────────────────────────────────────────────────────────────

@bot.command(name="profile", aliases=["p", "stats"])
async def prefix_profile(ctx: commands.Context, user: discord.Member = None):
    target = user or ctx.author
    db = _load_economy()
    if target.id == ctx.author.id:
        _apply_bank_interest(db, target.id)
        _save_economy(db)
    bal     = _get_balance(target.id, db)
    bank    = _bank_get(db, target.id)
    streak  = db.get("streaks", {}).get(str(target.id), 0)
    inv     = _inv_get(db, target.id)
    items   = ", ".join(_SHOP_ITEMS[i]["name"] for i in inv if i in _SHOP_ITEMS) or "None"
    protect = _has_rob_protection(target.id, db)
    own     = target.id == ctx.author.id
    who     = "Your" if own else f"{target.display_name}'s"
    await ctx.send(view=_cv2(C_BRAND,
        _td(f"## {who} Profile"),
        _sep(),
        _td(f"**User:** {target.mention}\n"
            f" **Wallet:** {bal:,}\n"
            f" **Bank:**   {bank:,}\n"
            f" **Net Worth:** {bal+bank:,}\n"
            f" **Daily Streak:** {streak} days\n"
            f" **Rob Protection:** {'Active' if protect else 'None'}\n"
            f" **Items:** {items}"),
        _td("-# SkyHighEV Economy  ·  !history for transactions"),
    ))

# ── :-:history ───────────────────────────────────────────────────────────────

@bot.command(name="history", aliases=["hist", "tx", "transactions"])
async def prefix_history(ctx: commands.Context):
    db   = _load_economy()
    hist = db.get("history", {}).get(str(ctx.author.id), [])
    if not hist:
        await ctx.send(view=cv2_info("History", "No transactions yet. Earn or spend some coins!"))
        return
    lines = []
    for tx in hist[-15:][::-1]:
        try:
            ts = int(datetime.fromisoformat(tx["ts"]).timestamp())
            tstr = f"<t:{ts}:R>"
        except Exception:
            tstr = ""
        d = tx.get("delta", 0)
        sign = "+" if d > 0 else ""
        lines.append(f"`{sign}{d:,}`  {tx.get('label','?')}  {tstr}")
    await ctx.send(view=_cv2(C_INFO,
        _td("##  Transaction History"),
        _sep(),
        _td("\n".join(lines)),
        _td("-# Last 15 transactions"),
    ))


# ══════════════════════════════════════════════════════════════════════════════
#  BOT EVENTS
# ══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    bot.add_view(PayoutPanelView())   # re-register persistent payout panel button
    bot.add_view(TicketPanelLayout())   # re-register persistent ticket panel button
    bot.add_view(TicketControlLayout()) # re-register open ticket buttons
    bot.add_view(TicketCloseLayout())   # re-register closed ticket delete button
    await bot.tree.sync()
    print(f"[BOT] Online as {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Admin IDs: {ADMIN_IDS}")
    print(f"[BOT] API: {API_BASE_URL}")
    print(f"[BOT] Commands synced")
    if not keep_render_alive.is_running():
        keep_render_alive.start()
        print(f"[BOT] Keep-alive started — pinging every 14 min")

    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="Helping SiyHigh Workers"
        )
    )

# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("[ERROR] BOT_TOKEN is empty")
        raise SystemExit(1)
    if not API_BASE_URL or not WORKER_API_KEY or not TOTP_SECRET or not ADMIN_KEY:
        print("[ERROR] API credentials missing")
        raise SystemExit(1)
    if not ADMIN_IDS:
        print("[WARN] ADMIN_IDS is empty — admin commands inaccessible")
    bot.run(BOT_TOKEN)
