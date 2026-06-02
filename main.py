
import asyncio
from datetime import datetime
import hashlib
import os
import shutil
from pathlib import Path
import platform
import re
import sys
import threading
import time
import json
import random
import string
import signal
import tempfile
from typing import Optional, Dict
import requests
import httpx
import tls_client
from colorama import Fore, Style, init
from pystyle import Center, Colorate, Colors
from rich.console import Console
import warnings
import nodriver as uc
import urllib3
import base64
import pyotp  # for TOTP 2FA

# Try to import psutil for process management (optional)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Initialize colorama
init(autoreset=True)

# Disable SSL warnings and suppress nodriver connection errors
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=ResourceWarning)
warnings.filterwarnings('ignore', message='.*connection.*refused.*')
warnings.filterwarnings('ignore', message='.*Task exception was never retrieved.*')

# Suppress asyncio errors in console
import logging
logging.getLogger('asyncio').setLevel(logging.CRITICAL)
logging.getLogger('websockets').setLevel(logging.CRITICAL)
logging.getLogger('nodriver').setLevel(logging.CRITICAL)

# ============================================================================
# ★  EDIT THESE BEFORE COMPILING YOUR EXE  ★
# These values are baked into the binary. Workers never see them — they
# only need to enter their personal "Worker Key" when the tool starts.
# ============================================================================

# ─── Credentials injected by the launcher at runtime — DO NOT hardcode ────
# These are set automatically when workers run launcher.py.
# To change the server URL, update the CTRL_API_URL secret on your host
# (Replit Secrets tab, or Render environment settings) — no code edits needed.
import os as _os
API_URL     = _os.environ.get("CTRL_API_URL", "")
API_KEY     = _os.environ.get("CTRL_API_KEY", "")
TOTP_SECRET = _os.environ.get("CTRL_TOTP_SECRET", "")

# ─── Zeus-X API key (zeus-x.ru) — leave blank if not using ───────────────
ZEUS_API_KEY = ""

# ============================================================================
# API CLIENT — talks to your own API server with 2FA
# ============================================================================

class WorkerAPIClient:
    """Talks to your private API server with API key + TOTP 2FA headers."""

    def __init__(self, base_url: str, api_key: str, totp_secret: str, worker_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.totp_secret = totp_secret
        self.worker_key = worker_key

    def _headers(self) -> dict:
        totp = pyotp.TOTP(self.totp_secret)
        return {
            "x-api-key": self.api_key,
            "x-totp-code": totp.now(),
            "Content-Type": "application/json",
        }

    def validate_worker_key(self) -> dict:
        try:
            resp = requests.post(
                f"{self.base_url}/api/workers/validate-key",
                json={"workerKey": self.worker_key},
                headers=self._headers(),
                timeout=15,
                verify=False,
            )
            try:
                return resp.json()
            except Exception:
                return {"valid": False, "status": "ERROR", "message": f"Server returned non-JSON (HTTP {resp.status_code}). Raw: {resp.text[:200]}"}
        except requests.exceptions.ConnectionError:
            return {"valid": False, "status": "ERROR", "message": f"Cannot reach server at {self.base_url}. Check your internet connection."}
        except requests.exceptions.Timeout:
            return {"valid": False, "status": "ERROR", "message": "Server timed out. The API may be sleeping — try again in a few seconds."}
        except Exception as e:
            return {"valid": False, "status": "ERROR", "message": str(e)}

    def save_token(self, token: str, email: str = None, account_pass: str = None, status: str = "VALID") -> dict:
        payload = {
            "token": token,
            "email": email,
            "accountPass": account_pass,
            "workerKey": self.worker_key,
            "status": status,
        }
        last_err = None
        for attempt in range(1, 4):  # up to 3 attempts
            try:
                resp = requests.post(
                    f"{self.base_url}/api/tokens/save",
                    json=payload,
                    headers=self._headers(),
                    timeout=15,
                    verify=False,
                )
                data = resp.json()
                # If savedBy is present the server confirmed the DB row was written
                if data.get("savedBy"):
                    return data
                # success=false or duplicate — no retry needed
                return data
            except requests.exceptions.Timeout:
                last_err = f"timeout (attempt {attempt}/3)"
            except requests.exceptions.ConnectionError:
                last_err = f"connection error (attempt {attempt}/3)"
            except Exception as e:
                last_err = str(e)
            if attempt < 3:
                time.sleep(2 * attempt)  # 2s, then 4s backoff
        return {"success": False, "error": last_err}

# Global API client (set after worker key validation)
api_client: Optional[WorkerAPIClient] = None

# ============================================================================
# DISCORD TOKEN FETCH FUNCTION
# ============================================================================

async def fetch_discord_token(email: str, password: str) -> str:
    url = "https://discord.com/api/v9/auth/login"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://discord.com",
        "priority": "u=1, i",
        "referer": "https://discord.com/channels/@me",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "x-discord-timezone": "Asia/Calcutta",
        "x-super-properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEzNC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTM0LjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjM4MDA4NiwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0=",
    }
    payload = {
        "gift_code_sku_id": None,
        "login": email,
        "login_source": None,
        "password": password,
        "undelete": False,
    }
    session = tls_client.Session(client_identifier="chrome_131", random_tls_extension_order=True)
    try:
        response = session.post(url, headers=headers, json=payload)
        print(f"Succesfully Fetched Token -> {email}")
        if response.status_code != 200:
            return ""
        response_data = response.json()
        token = response_data.get("token")
        if not token:
            return ""
        return token
    except:
        return ""

# ============================================================================
# JAVASCRIPT UTILITIES
# ============================================================================

JS_UTILS = '''
(() => {
    if (window.utils) return;
    function setInput(selector, value) {
        const el = document.querySelector(selector);
        if (el) {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
    function clickAllCheckboxes() {
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        let clicked = 0;
        checkboxes.forEach(cb => {
            if (!cb.checked) {
                cb.click();
                cb.checked = true;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
                clicked++;
            }
        });
        return { clicked: clicked, total: checkboxes.length };
    }
    function clickElement(selector) {
        const el = document.querySelector(selector);
        if (el) el.click();
    }
    function setDropdown(label, value) {
        const dropdown = document.querySelector(`div[role="button"][aria-label="${label}"]`);
        if (!dropdown) return;
        dropdown.click();
        setTimeout(() => {
            const options = document.querySelectorAll('div[role="option"]');
            const match = Array.from(options).find(opt => opt.textContent.trim() === value);
            if (match) match.click();
        }, 100);
    }
    function waitForDiscordToken(timeout = 5000) {
        return new Promise((resolve) => {
            const start = Date.now();
            const check = () => {
                const token = localStorage.getItem('token');
                if (token) {
                    resolve(token.replace(/^"|"$/g, ''));
                } else if (Date.now() - start < timeout) {
                    setTimeout(check, 200);
                } else {
                    resolve(null);
                }
            };
            check();
        });
    }
    function findCaptchaFrame() {
        const iframes = document.querySelectorAll('iframe');
        for (let iframe of iframes) {
            const src = iframe.src || '';
            if (src.includes('captcha') || src.includes('hcaptcha') || src.includes('recaptcha')) {
                return iframe;
            }
        }
        return null;
    }
    window.utils = {
        setInput,
        clickAllCheckboxes,
        clickElement,
        setDropdown,
        waitForDiscordToken,
        findCaptchaFrame
    };
})();
'''

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

console = Console()
LOCK = threading.Lock()
SCRIPT_DIR = Path(__file__).parent
MS_CLIENT_ID = "d8fbe69d-15be-43fa-b204-5c5bc5a73ad7"

SESSION_TARGET = 0
SESSION_CREATED = 0
SESSION_STOP = False

# Runtime config — populated from API server after worker key validation
config: Dict = {}


# ============================================================================
# LOGGER
# ============================================================================

class Logger:
    def get_time(self):
        return datetime.now().strftime('%H:%M:%S')
    def info(self, message: str):
        print(Colorate.Horizontal(Colors.cyan_to_blue, f"[{self.get_time()}] [INFO] {message}"))
    def success(self, message: str):
        print(Colorate.Horizontal(Colors.green_to_cyan, f"[{self.get_time()}] [SUCCESS] {message}"))
    def warning(self, message: str):
        self.info(message)
    def error(self, message: str):
        print(Colorate.Horizontal(Colors.blue_to_cyan, f"[{self.get_time()}] [ERROR] {message}"))
    def debug(self, message: str):
        print(Colorate.Horizontal(Colors.blue_to_cyan, f"[{self.get_time()}] [DEBUG] {message}"))

log = Logger()

# ============================================================================
# PROXY HANDLER
# ============================================================================

def load_proxies(config: dict) -> list:
    proxy_enabled = config.get("proxy", {}).get("enabled", False)
    if not proxy_enabled:
        return []
    proxy_file = config.get("proxy", {}).get("file", "input/proxies.txt")
    proxy_path = Path(proxy_file)
    if not proxy_path.exists():
        log.warning(f"Proxy file not found: {proxy_file}")
        return []
    try:
        with open(proxy_path, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            log.success(f"Loaded {len(proxies)} proxies from {proxy_file}")
            return proxies
        else:
            log.warning("Proxy file is empty")
            return []
    except Exception as e:
        log.error(f"Error loading proxies: {e}")
        return []

def get_random_proxy(proxies: list) -> str:
    if not proxies:
        return None
    return random.choice(proxies)

# ============================================================================
# ADB IP ROTATOR — works on ANY PC/laptop, not just Dell
# ============================================================================

class ADBIPRotator:
    """Rotate public IP via mobile data reset on an Android device (via ADB)"""

    def __init__(self, adb_path: str = None):
        self.adb = adb_path or self._find_adb()
        if not self.adb or not os.path.isfile(self.adb):
            raise FileNotFoundError(f"adb.exe not found. Please connect your Android device and ensure adb is installed.")
        log.success(f"ADB path: {self.adb}")

    @staticmethod
    def _find_adb():
        """
        Auto-detect adb.exe or adb binary on any PC/laptop regardless of brand.
        Searches PATH first, then common install locations across all user profiles.
        Works on Windows, macOS, and Linux.
        """
        import subprocess

        # 1) Check PATH first (works if user added platform-tools to PATH)
        found_in_path = shutil.which("adb")
        if found_in_path:
            return found_in_path

        system = platform.system()

        if system == "Windows":
            candidates = []

            # Detect all user home directories dynamically (works for any username)
            users_dir = Path("C:/Users")
            if users_dir.exists():
                for user_dir in users_dir.iterdir():
                    if not user_dir.is_dir():
                        continue
                    # Common download/install locations
                    candidates += [
                        user_dir / "Downloads" / "platform-tools-latest-windows" / "platform-tools" / "adb.exe",
                        user_dir / "Downloads" / "platform-tools" / "adb.exe",
                        user_dir / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
                        user_dir / "AppData" / "Local" / "Android" / "sdk" / "platform-tools" / "adb.exe",
                        user_dir / "platform-tools" / "adb.exe",
                    ]

            # System-level locations
            candidates += [
                Path("C:/platform-tools/adb.exe"),
                Path("C:/Android/platform-tools/adb.exe"),
                Path("C:/android-sdk/platform-tools/adb.exe"),
                Path(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
                Path(os.environ.get("PROGRAMFILES", ""), "Android", "platform-tools", "adb.exe"),
                Path(os.environ.get("PROGRAMFILES(X86)", ""), "Android", "platform-tools", "adb.exe"),
            ]

        elif system == "Darwin":  # macOS
            home = Path.home()
            candidates = [
                home / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
                home / "android-sdk" / "platform-tools" / "adb",
                Path("/usr/local/bin/adb"),
                Path("/opt/homebrew/bin/adb"),
                Path("/Applications/Android Studio.app/Contents/sdk/platform-tools/adb"),
            ]

        else:  # Linux
            home = Path.home()
            candidates = [
                home / "Android" / "Sdk" / "platform-tools" / "adb",
                home / ".android" / "sdk" / "platform-tools" / "adb",
                home / "android-sdk" / "platform-tools" / "adb",
                Path("/usr/bin/adb"),
                Path("/usr/local/bin/adb"),
                Path("/opt/android-sdk/platform-tools/adb"),
                Path("/opt/android/platform-tools/adb"),
            ]

        for p in candidates:
            try:
                if p and Path(p).is_file():
                    return str(p)
            except Exception:
                continue

        return None

    def _run(self, *args, timeout: int = 20) -> str:
        import subprocess
        cmd = [self.adb] + list(args)
        cmd_str = " ".join(str(a) for a in args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = result.stdout.strip()
            if result.returncode != 0 and result.stderr.strip():
                log.debug(f"ADB stderr [{cmd_str}]: {result.stderr.strip()[:120]}")
            return out
        except subprocess.TimeoutExpired:
            log.warning(f"ADB command timed out ({timeout}s): {cmd_str}")
            return ""
        except Exception as e:
            log.error(f"ADB command failed [{cmd_str}]: {e}")
            return ""

    def check_device(self) -> bool:
        output = self._run("devices")
        lines = [l for l in output.splitlines() if "\tdevice" in l]
        if lines:
            serial = lines[0].split("\t")[0]
            log.success(f"ADB device found: {serial}")
            return True
        log.error("No ADB device detected. Make sure USB debugging is enabled.")
        return False

    @staticmethod
    def get_current_ip() -> str:
        endpoints = [
            "https://api.ipify.org?format=json",
            "https://httpbin.org/ip",
            "https://ifconfig.me/ip",
        ]
        for url in endpoints:
            try:
                resp = requests.get(url, timeout=10, verify=False)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return data.get("ip") or data.get("origin") or resp.text.strip()
                    except Exception:
                        return resp.text.strip()
            except Exception:
                continue
        return ""

    def _set_wifi(self, enable: bool):
        state = "enable" if enable else "disable"
        self._run("shell", "svc", "wifi", state)
        log.info(f"[ADB] Wi-Fi → {state.upper()}")
        time.sleep(1)

    def _set_mobile_data(self, enable: bool):
        state = "enable" if enable else "disable"
        self._run("shell", "svc", "data", state)
        log.info(f"[ADB] Mobile data → {state.upper()}")

    def _try_rotate(self, old_ip: str, max_wait: int = 45) -> str:
        log.info("[ADB] Step 1/4 — Disabling Wi-Fi (force mobile data only)...")
        self._set_wifi(False)
        log.info("[ADB] Step 2/4 — Disabling mobile data...")
        self._set_mobile_data(False)
        log.info("[ADB] Waiting 4s for carrier to drop connection...")
        time.sleep(4)
        log.info("[ADB] Step 3/4 — Re-enabling mobile data...")
        self._set_mobile_data(True)
        log.info("[ADB] Waiting 3s for carrier to assign new IP...")
        time.sleep(3)
        log.info(f"[ADB] Step 4/4 — Polling for IP change (up to {max_wait}s)...")
        start = time.time()
        while (time.time() - start) < max_wait:
            new_ip = self.get_current_ip()
            if new_ip and new_ip != old_ip:
                return new_ip
            if new_ip:
                log.debug(f"[ADB] IP still {new_ip}, carrier may need more time...")
            time.sleep(4)
        final_ip = self.get_current_ip()
        return final_ip if (final_ip and final_ip != old_ip) else ""

    def rotate_ip(self, max_retries: int = 3, max_wait: int = 45) -> bool:
        old_ip = self.get_current_ip()
        log.info(f"[ADB] Starting IP rotation. Current IP: {old_ip or '(unknown)'}")
        for attempt in range(1, max_retries + 1):
            log.info(f"[ADB] Rotation attempt {attempt}/{max_retries}")
            new_ip = self._try_rotate(old_ip, max_wait=max_wait)
            if new_ip:
                log.success(f"[ADB] IP rotated: {old_ip} → {new_ip}")
                return True
            if attempt < max_retries:
                log.warning(f"[ADB] IP unchanged on attempt {attempt}. Waiting 5s before retry...")
                time.sleep(5)
        log.warning(f"[ADB] IP did not change after {max_retries} attempt(s).")
        return False

# ============================================================================
# JAVASCRIPT HELPER CLASS
# ============================================================================

class JsHelper:
    _injected = set()

    @staticmethod
    def setup(page):
        page_id = id(page)
        if page_id in JsHelper._injected:
            return
        try:
            page.evaluate(JS_UTILS)
            JsHelper._injected.add(page_id)
        except Exception as e:
            log.warning(f"JS inject error: {e}")

    @staticmethod
    def set_input(page, selector: str, value: str):
        value_escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        selector_escaped = selector.replace('\\', '\\\\').replace('"', '\\"')
        page.evaluate(f'window.utils.setInput("{selector_escaped}", "{value_escaped}")')

    @staticmethod
    def click_all_checkboxes(page):
        return page.evaluate('window.utils.clickAllCheckboxes()')

    @staticmethod
    def click_element(page, selector: str):
        selector_escaped = selector.replace('\\', '\\\\').replace('"', '\\"')
        page.evaluate(f'window.utils.clickElement("{selector_escaped}")')

    @staticmethod
    def find_captcha_frame(page):
        return page.evaluate('window.utils.findCaptchaFrame()')

    @staticmethod
    def wait_for_token(page, timeout: int = 5000):
        try:
            return page.evaluate(f'window.utils.waitForDiscordToken({timeout})')
        except:
            return None

# ============================================================================
# HOTMAIL007 EMAIL API
# ============================================================================

class Hotmail007API:
    def __init__(self, client_key: str):
        self.session = requests.Session()
        self.session.verify = False
        self.client_key = client_key
        self.base_url = "https://api.hotmail007.com"
        self.mail_types = ["outlook", "hotmail"]

    def _fetch_email(self, mail_type: str) -> dict:
        url = f"{self.base_url}/api/mail/getMail"
        params = {"clientKey": self.client_key, "mailType": mail_type, "quantity": 1}
        try:
            resp = self.session.get(url, params=params, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("code") == 0 and "data" in data:
                    accounts = data["data"]
                    if accounts:
                        parts = accounts[0].split(":")
                        if len(parts) >= 4:
                            return {
                                "success": True,
                                "email": parts[0],
                                "password": parts[1],
                                "token": parts[2],
                                "uuid": parts[3] if parts[3] else ""
                            }
        except Exception:
            pass
        return {"success": False}

    def buy_email(self, max_retries: int = 10) -> dict:
        if not self.client_key:
            log.error("Missing hotmail007 client_key in config")
            return {"success": False, "error": "Missing client_key"}
        log.info("Purchasing email from Hotmail007...")
        start_time = time.time()
        timeout = 20
        attempt = 0
        while (time.time() - start_time) < timeout:
            attempt += 1
            for mail_type in self.mail_types:
                log.info(f"Attempt {attempt}: Trying {mail_type}...")
                account = self._fetch_email(mail_type)
                if account.get("success"):
                    email = account.get("email")
                    password = account.get("password")
                    log.success(f"Got {mail_type}: {email}")
                    return {
                        "success": True,
                        "email": email,
                        "password": password,
                        "token": account.get("token", ""),
                        "uuid": account.get("uuid", "")
                    }
            time.sleep(1)
        log.error("Failed to purchase email after 20s")
        return {"success": False, "error": "Timeout after 20s"}

    def check_inbox(self, email: str) -> dict:
        try:
            response = self.session.get(
                f"{self.base_url}/inbox",
                params={"clientKey": self.client_key, "email": email},
                verify=False, timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "messages": data.get("messages", [])}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ============================================================================
# CYBERTEMP EMAIL API
# ============================================================================

def _parse_domains(raw: str) -> list:
    """Parse a comma-separated domain string into a clean list."""
    if not raw:
        return []
    return [d.strip().lstrip("@") for d in raw.replace(";", ",").split(",") if d.strip()]

class CybertempAPI:
    def __init__(self, api_key: str = None, custom_domains: list = None):
        self.api_key       = api_key
        self.custom_domains = [d.strip() for d in (custom_domains or []) if d.strip()]
        self.base_url      = "https://api.cybertemp.xyz"
        self.session       = requests.Session()
        self.session.verify = False
        if api_key:
            self.session.headers.update({"X-API-KEY": api_key})

    def get_discord_domains(self) -> list:
        try:
            resp = self.session.get(f"{self.base_url}/getDomains", params={"type": "discord", "limit": 100}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            log.debug(f"CyberTemp getDomains error: {e}")
        return []

    def _make_address(self, domain: str) -> str:
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        return f"{local}@{domain}"

    def get_email(self) -> dict:
        # ── Custom domains take full priority ──────────────────────
        if self.custom_domains:
            domain = random.choice(self.custom_domains)
            email  = self._make_address(domain)
            log.debug(f"CyberTemp using custom domain: {domain}")
            return {"success": True, "email": email, "inbox_token": None}

        # ── Default: try /email endpoint first ─────────────────────
        try:
            resp = self.session.get(f"{self.base_url}/email", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("email"):
                    return {"success": True, "email": data.get("email"), "inbox_token": data.get("token")}
        except Exception:
            pass

        # ── Fallback: pick from CyberTemp discord domain pool ──────
        domains = self.get_discord_domains()
        if not domains:
            return {"success": False, "error": "No CyberTemp discord domains available"}
        domain = random.choice(domains)
        email  = self._make_address(domain)
        return {"success": True, "email": email, "inbox_token": None}

    def check_inbox(self, email: str) -> dict:
        try:
            params = {"email": email, "limit": 25}
            if self.api_key:
                params["apikey"] = self.api_key
            resp = self.session.get(f"{self.base_url}/getMail", params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                messages = data if isinstance(data, list) else data.get("messages", [])
                return {"success": True, "messages": messages}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# ============================================================================
# DRAXONO MAIL API  (mail.draxono.in — public disposable inboxes, no API key)
# Docs: https://mail.draxono.in/docs
# ============================================================================

class DraxonAPI:
    """
    DraxonMails disposable email provider — fully public, no API key required.
    Updated per the latest docs (mail.draxono.in/docs):
      - GET /api/random-address  → {address, local, domain}  (preferred email source)
      - GET /api/domains         → {"domains": [...]}        (used when custom domains aren't set)
      - GET /api/inbox/{address} → list of messages
    The only header that exists is X-Draxon-Domain-Secret, which is *only* needed
    for inboxes on a verified PRIVATE custom domain (one-time secret returned by
    /api/domain/check). Public addresses need no auth at all.
    """
    def __init__(self, domain_secret: str = None, custom_domains: list = None):
        self.domain_secret  = (domain_secret or "").strip()
        self.custom_domains = [d.strip().lstrip("@") for d in (custom_domains or []) if d.strip()]
        self.base_url       = "https://mail.draxono.in/api"
        self.session        = requests.Session()
        self.session.verify = False
        # Plain UA — no auth headers; the API rate-limits by risk score, not by key
        self.session.headers.update({
            "User-Agent": "SkyHighEV/1.0 (+draxono-client)",
            "Accept":     "application/json",
        })

    def _inbox_headers(self) -> dict:
        # Domain secret only goes out for private custom-domain inboxes
        return {"X-Draxon-Domain-Secret": self.domain_secret} if self.domain_secret else {}

    def get_domains(self) -> list:
        """Return list of currently public domains, or [] on failure."""
        try:
            resp = self.session.get(f"{self.base_url}/domains", timeout=15)
            if resp.status_code == 200:
                data = resp.json() or {}
                return [d for d in (data.get("domains") or []) if isinstance(d, str)]
        except Exception as e:
            log.debug(f"Draxono /domains error: {e}")
        return []

    def get_random_address(self) -> Optional[dict]:
        """Use the official /api/random-address endpoint."""
        try:
            resp = self.session.get(f"{self.base_url}/random-address", timeout=15)
            if resp.status_code == 200:
                data = resp.json() or {}
                if data.get("address"):
                    return {"address": data["address"], "local": data.get("local"), "domain": data.get("domain")}
        except Exception as e:
            log.debug(f"Draxono /random-address error: {e}")
        return None

    def _make_address(self, domain: str) -> str:
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        return f"{local}@{domain}"

    def get_email(self) -> dict:
        # 1. Custom verified domains take priority
        if self.custom_domains:
            domain = random.choice(self.custom_domains)
            return {"success": True, "email": self._make_address(domain), "inbox_token": None}

        # 2. Preferred: ask Draxono for a random address
        rnd = self.get_random_address()
        if rnd and rnd.get("address"):
            return {"success": True, "email": rnd["address"], "inbox_token": None}

        # 3. Fallback: pick one of the listed public domains and roll our own local part
        domains = self.get_domains()
        if domains:
            return {"success": True, "email": self._make_address(random.choice(domains)), "inbox_token": None}

        return {"success": False, "error": "Draxono: no domains available"}

    def check_inbox(self, email: str) -> dict:
        """Public inbox fetch. Returns {'success': bool, 'messages': [...]}"""
        try:
            resp = self.session.get(f"{self.base_url}/inbox/{email}", headers=self._inbox_headers(), timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                messages = data if isinstance(data, list) else data.get("messages", [])
                return {"success": True, "messages": messages or []}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================================
# ZEUS-X EMAIL API  (zeus-x.ru — bulk Outlook/Hotmail accounts)
# ============================================================================

class ZeusXAPI:
    """Fetch bulk Outlook/Hotmail accounts from zeus-x.ru."""

    BASE_URL = "https://api.zeus-x.ru"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.verify = False

    def buy_email(self, mail_type: str = "outlook", quantity: int = 1) -> dict:
        """Purchase one Outlook/Hotmail account from zeus-x.ru.
        
        Correct endpoint per zeus-x.ru docs:
          GET https://api.zeus-x.ru/purchase?apikey=KEY&accountcode=HOTMAIL&quantity=1
        """
        if not self.api_key:
            log.error("Missing Zeus-X API key. Set ZEUS_API_KEY at the top of main.py.")
            return {"success": False, "error": "Missing API key"}

        # Map generic mail_type names to zeus-x.ru accountcode values
        account_code = "HOTMAIL"  # Default — covers both Outlook and Hotmail

        log.info(f"Purchasing {account_code} from Zeus-X...")
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/purchase",
                params={
                    "apikey": self.api_key,
                    "accountcode": account_code,
                    "quantity": quantity,
                },
                timeout=20,
            )
            log.debug(f"Zeus-X /purchase → HTTP {resp.status_code}: {resp.text[:200]}")

            if resp.status_code == 200:
                data = resp.json()
                # Response can be a list of "email:password" strings or a dict with a data/accounts key
                accounts = None
                if isinstance(data, list):
                    accounts = data
                elif isinstance(data, dict):
                    accounts = (
                        data.get("accounts") or
                        data.get("data") or
                        data.get("result") or
                        data.get("items")
                    )

                if accounts:
                    raw = accounts[0] if isinstance(accounts, list) else accounts
                    if isinstance(raw, str) and ":" in raw:
                        parts = raw.split(":")
                        return {"success": True, "email": parts[0], "password": parts[1] if len(parts) > 1 else ""}
                    if isinstance(raw, dict):
                        email = raw.get("email") or raw.get("login") or raw.get("username")
                        password = raw.get("password") or raw.get("pass") or raw.get("pwd")
                        if email:
                            return {"success": True, "email": email, "password": password or ""}

                log.error(f"Zeus-X: Unexpected response format: {data}")
                return {"success": False, "error": f"Unexpected response: {str(data)[:100]}"}

            elif resp.status_code == 401 or resp.status_code == 403:
                log.error("Zeus-X: Invalid API key — check your key on zeus-x.ru")
                return {"success": False, "error": f"Invalid API key (HTTP {resp.status_code})"}
            else:
                log.error(f"Zeus-X: HTTP {resp.status_code} — {resp.text[:100]}")
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:100]}"}

        except Exception as e:
            log.debug(f"Zeus-X /purchase error: {e}")
            return {"success": False, "error": str(e)}

    def check_balance(self) -> dict:
        """Check account balance on zeus-x.ru."""
        if not self.api_key:
            return {"success": False, "error": "Missing API key"}
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/balance",
                params={"apikey": self.api_key},
                timeout=15,
            )
            if resp.status_code == 200:
                return {"success": True, **resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_instock(self) -> dict:
        """Check what account types are currently in stock on zeus-x.ru."""
        try:
            resp = self.session.get(f"{self.BASE_URL}/instock", timeout=15)
            if resp.status_code == 200:
                return {"success": True, "instock": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================================
# BRAVE BROWSER DETECTION
# ============================================================================

def find_brave_executable() -> Optional[str]:
    """Auto-detect the Brave browser executable on Windows / macOS / Linux."""
    system = platform.system()
    candidates = []

    if system == "Windows":
        prog_files   = os.environ.get("PROGRAMFILES",      r"C:\Program Files")
        prog_files86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local_app    = os.environ.get("LOCALAPPDATA",       "")
        candidates = [
            Path(prog_files)   / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(prog_files86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(local_app)    / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            Path.home() / "Applications" / "Brave Browser.app" / "Contents" / "MacOS" / "Brave Browser",
        ]
    else:
        candidates = [
            Path("/usr/bin/brave-browser"),
            Path("/usr/bin/brave"),
            Path("/usr/local/bin/brave-browser"),
            Path("/snap/bin/brave"),
            Path("/opt/brave.com/brave/brave"),
        ]
        found_in_path = shutil.which("brave-browser") or shutil.which("brave")
        if found_in_path:
            return found_in_path

    for p in candidates:
        if p and p.is_file():
            return str(p)
    return None


# ============================================================================
# UTILITY HELPERS
# ============================================================================

def generate_username() -> str:
    adjectives = ['Cool', 'Epic', 'Super', 'Mega', 'Ultra', 'Pro', 'Elite', 'Master', 'Dark', 'Neon']
    nouns      = ['Gamer', 'Player', 'User', 'Hero', 'Legend', 'Champion', 'Warrior', 'Shadow', 'Ghost']
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(100, 9999)}"

def generate_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    pwd = list(random.choices(chars, k=length))
    pwd[0] = random.choice(string.ascii_uppercase)
    pwd[1] = random.choice(string.digits)
    random.shuffle(pwd)
    return "".join(pwd)

def check_token(token: str) -> str:
    """
    Check a Discord token and return VALID, LOCKED, or INVALID.
    Never returns ERROR — retries on rate-limit (429) and network failures
    until a definitive answer is obtained.
    """
    # /users/@me returns 200 even for phone-locked accounts.
    # /users/@me/guilds returns 403 for phone-locked accounts — correct signal.
    url     = "https://discord.com/api/v9/users/@me/guilds"
    headers = {
        "Authorization": token,
        "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type":  "application/json",
    }

    for attempt in range(12):
        try:
            resp = requests.get(url, headers=headers, timeout=20, verify=False)
            code = resp.status_code

            if code == 200:  return "VALID"
            if code == 401:  return "INVALID"
            if code == 403:  return "LOCKED"   # phone-lock or quarantined

            if code == 429:
                try:
                    retry_after = float(resp.json().get("retry_after", 5.0)) + 1.0
                except Exception:
                    retry_after = 6.0
                log.warning(f"check_token: rate-limited — waiting {retry_after:.1f}s (attempt {attempt+1}/12)")
                time.sleep(retry_after)
                continue

            # Any unexpected status (5xx, etc.) — short backoff then retry
            time.sleep(2.0 * (attempt + 1))

        except Exception as exc:
            wait = 2.0 * (attempt + 1)
            log.warning(f"check_token: network error ({exc}) — retrying in {wait:.0f}s (attempt {attempt+1}/12)")
            time.sleep(wait)

    # Exhausted all retries — token genuinely unreachable; treat conservatively
    log.error("check_token: could not determine status after 12 attempts — marking INVALID")
    return "INVALID"

def check_email_verified_api(token: str):
    try:
        sess = tls_client.Session(client_identifier="chrome_131", random_tls_extension_order=True)
        resp = sess.get(
            "https://discord.com/api/v9/users/@me",
            headers={"Authorization": token, "User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("verified", False), data.get("email", "")
        return None, None
    except Exception:
        return None, None



# ============================================================================
# EMAIL VERIFICATION — MS Graph (Hotmail007 / Zeus-X purchased accounts)
# ============================================================================

def _get_ms_access_token(refresh_token: str, client_id: str = None) -> Optional[str]:
    try:
        rt = refresh_token.rstrip("$")
        resp = requests.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": client_id or MS_CLIENT_ID,
                "refresh_token": rt,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30, verify=False,
        )
        return resp.json().get("access_token")
    except Exception as e:
        log.debug(f"MS token refresh error: {e}")
        return None

def _is_valid_verify_url(url: Optional[str]) -> bool:
    """A real Discord verify URL MUST contain `/verify?token=` (or `/verify#token=`).
    Anything else (e.g. plain `https://discord.com`) is garbage and would just
    open the Discord home page instead of consuming the verification token."""
    if not url:
        return False
    return ("discord.com/verify" in url) and ("token=" in url)


def _extract_discord_verify_link(body_html: str) -> Optional[str]:
    # Decode HTML entities first so &amp; becomes & in URLs
    body = (body_html or "").replace("&amp;", "&").replace("&#38;", "&")

    # 1) Direct discord.com/verify link (greediest first)
    direct = re.search(
        r'https://discord\.com/verify\?token=[A-Za-z0-9._\-]+(?:&[A-Za-z0-9._\-=%&]+)*',
        body)
    if direct and _is_valid_verify_url(direct.group(0)):
        return direct.group(0)

    # 2) Tracking / wrapper links — follow to the final URL
    tracker_patterns = [
        r'https://click\.discord\.com/ls/click\?[^"\'\>\s]+',
        r'https://links\.discord\.com[^"\'\>\s]+',
        r'https://email\.discord\.com[^"\'\>\s]+',
    ]
    for pat in tracker_patterns:
        for m in re.finditer(pat, body):
            try:
                r2 = requests.get(m.group(0), allow_redirects=True,
                                  timeout=10, verify=False)
                # Final landing URL after following redirects
                if _is_valid_verify_url(r2.url):
                    return r2.url
                # Or hidden inside the response body
                found = re.search(
                    r'https://discord\.com/verify\?token=[A-Za-z0-9._\-]+',
                    r2.text or "")
                if found and _is_valid_verify_url(found.group(0)):
                    return found.group(0)
            except Exception:
                pass

    return None

def fetch_verification_url_graph(email_data: dict, timeout: int = 120) -> Optional[str]:
    """Poll Outlook inbox via MS Graph API — used for Hotmail007 accounts."""
    refresh_token = email_data.get("token", "")
    if not refresh_token:
        return None
    access_token = _get_ms_access_token(refresh_token, email_data.get("uuid"))
    if not access_token:
        log.error("MS Graph: failed to get access token")
        return None
    log.info("Polling Outlook inbox via MS Graph...")
    start = time.time()
    attempt = 0
    while (time.time() - start) < timeout:
        attempt += 1
        try:
            resp = requests.get(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$top": 5, "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,receivedDateTime"},
                timeout=15, verify=False,
            )
            for email in resp.json().get("value", []):
                subject  = email.get("subject", "").lower()
                from_adr = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                if not (("verify" in subject or "confirm" in subject) and "discord" in from_adr):
                    continue
                link = _extract_discord_verify_link(email.get("body", {}).get("content", ""))
                if link:
                    return link
        except Exception as e:
            log.debug(f"MS Graph poll error: {e}")
        if attempt % 5 == 0:
            log.info(f"Waiting for Outlook verification email... ({int(time.time()-start)}s)")
        time.sleep(3)
    log.warning("Verification email not found in Outlook inbox after timeout")
    return None

def fetch_verification_url_draxono(email: str, domain_secret: str = None, timeout: int = 120) -> Optional[str]:
    """
    Poll DraxonMails inbox until a Discord verification email arrives,
    then extract and return the verify URL.
    The public API needs no auth. `domain_secret` is only used when polling
    an inbox that lives on a verified PRIVATE custom domain — the secret is
    sent via the X-Draxon-Domain-Secret header.
    """
    headers = {
        "User-Agent": "SkyHighEV/1.0 (+draxono-client)",
        "Accept":     "application/json",
    }
    if domain_secret:
        headers["X-Draxon-Domain-Secret"] = domain_secret

    url = f"https://mail.draxono.in/api/inbox/{email}"
    start_time = time.time()
    attempt    = 0
    seen       = set()

    log.info(f"Polling Draxono inbox for: {email}")
    while (time.time() - start_time) < timeout:
        attempt += 1
        try:
            resp = requests.get(url, headers=headers, timeout=20, verify=False)
            if resp.status_code == 429:
                log.warning("Draxono rate-limited (risk score) — backing off 10s")
                time.sleep(10)
                continue
            if resp.status_code in (401, 403):
                log.error(f"Draxono inbox HTTP {resp.status_code} — likely a private domain without the correct X-Draxon-Domain-Secret. Set it in the dashboard.")
                return None
            if resp.status_code != 200:
                log.debug(f"Draxono inbox HTTP {resp.status_code}")
                time.sleep(3)
                continue

            data = resp.json()
            messages = data if isinstance(data, list) else data.get("messages", [])
            if not isinstance(messages, list):
                time.sleep(3)
                continue

            if attempt % 5 == 0:
                elapsed = int(time.time() - start_time)
                log.info(f"Checking Draxono inbox... ({elapsed}s elapsed, {len(messages)} emails found)")

            for msg in messages:
                # Use timestamp as a simple dedupe key (matches the official Python class in the docs)
                uid = hash((msg.get("subject", ""), msg.get("timestamp", 0)))
                if uid in seen:
                    continue
                seen.add(uid)

                subject   = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from")    or "").lower()
                body_html = msg.get("html") or msg.get("body") or ""
                body_html = body_html.replace("&amp;", "&").replace("&#38;", "&")

                is_discord = "discord" in from_addr or "noreply@discord.com" in from_addr
                is_verify  = any(k in subject for k in ("verify", "confirm", "email"))
                if not (is_discord and is_verify):
                    continue

                link = _extract_discord_verify_link(body_html)
                if link:
                    log.success(f"Extracted verify link from Draxono: {link[:60]}...")
                    return link
                log.warning("Draxono: Discord email found but verify link missing or malformed")
        except Exception as e:
            log.debug(f"Draxono poll error: {e}")
        time.sleep(3)

    log.warning("Draxono: verification email not found within timeout")
    return None


def fetch_verification_url_cybertemp(email: str, api_key: str = None, inbox_token: str = None, timeout: int = 120) -> Optional[str]:
    """
    Poll CyberTemp /getMail until a Discord verification email arrives,
    then extract and return the verify URL.
    inbox_token: per-inbox token returned by CyberTemp /email endpoint (used when no account API key is set).
    """
    # Use inbox_token as fallback auth if no account-level API key is configured
    effective_key = api_key or inbox_token
    if effective_key:
        log.info(f"Polling CyberTemp inbox for: {email} (auth: ***{effective_key[-4:]})")
    else:
        log.warning("Polling CyberTemp inbox WITHOUT an API key — this will likely fail. Set your CyberTemp API key in the dashboard Tool Config page.")

    headers = {}
    if effective_key:
        headers["X-API-KEY"] = effective_key

    base_url   = "https://api.cybertemp.xyz/getMail"
    start_time = time.time()
    attempt    = 0
    seen_ids   = set()

    while (time.time() - start_time) < timeout:
        attempt += 1
        try:
            params = {"email": email, "limit": 25}
            if effective_key:
                params["apikey"] = effective_key  # pass as query param too — some CyberTemp versions require this

            resp = requests.get(
                base_url,
                params=params,
                headers=headers,
                timeout=20,
                verify=False
            )

            if resp.status_code == 401:
                log.error("CyberTemp getMail 401 — API key missing or invalid. Set your CyberTemp API key in the dashboard Tool Config page, then restart the tool.")
                return None  # No point retrying — key won't change mid-run
            elif resp.status_code != 200:
                log.debug(f"CyberTemp getMail HTTP {resp.status_code}")
                time.sleep(3)
                continue

            messages = resp.json()
            if not isinstance(messages, list):
                time.sleep(3)
                continue

            if attempt % 5 == 0:
                elapsed = int(time.time() - start_time)
                log.info(f"Checking CyberTemp inbox... ({elapsed}s elapsed, {len(messages)} emails found)")

            for msg in messages:
                msg_id = msg.get("id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                subject   = (msg.get("subject") or "").lower()
                from_addr = (msg.get("from")    or "").lower()
                body_html = msg.get("html") or msg.get("text") or ""

                # Decode HTML entities so &amp; → & in URLs
                body_html = body_html.replace("&amp;", "&").replace("&#38;", "&")

                # Must be from Discord and look like a verify email
                is_discord = "discord" in from_addr or "noreply@discord.com" in from_addr
                is_verify  = any(k in subject for k in ("verify", "confirm", "email"))

                if not (is_discord and is_verify):
                    continue

                link = _extract_discord_verify_link(body_html)
                if link:
                    log.success(f"Extracted verify link from CyberTemp: {link[:60]}...")
                    return link
                log.warning("CyberTemp: Discord email found but verify link missing or malformed")

        except Exception as e:
            log.debug(f"CyberTemp poll error: {e}")

        time.sleep(3)

    log.warning("Verification email not found in CyberTemp inbox after timeout")
    return None


# ============================================================================
# BROWSER HELPERS — safe navigation, form filling, DOB, token wait
# ============================================================================

async def safe_browser_get(browser, url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await browser.get(url)
        except (StopIteration, RuntimeError):
            if attempt < max_retries - 1:
                log.warning(f"Navigation failed (attempt {attempt+1}/{max_retries}), retrying...")
                await asyncio.sleep(2)
            else:
                raise
    return None

async def fill_date_of_birth(page) -> bool:
    """Fill Month/Day/Year using the browser's REAL mouse events via CDP.

    JS-dispatched events (`el.click()` from inside `page.evaluate`) are flagged
    as untrusted by React, so Discord's onClick handlers ignore them — that's
    why the previous attempts didn't open the dropdowns at all. nodriver's
    `Element.mouse_click()` / `Element.click()` go through the DevTools
    Protocol's Input.dispatchMouseEvent, which produces *trusted* events that
    React accepts.

    Strategy:
      1. Find the 3 DOB controls in the DOM (try several layouts).
      2. For each: scroll into view → real click → wait for the listbox to
         actually mount → find the target option element → real click on it.
    """
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    month = random.choice(months)
    day   = str(random.randint(1, 28))
    year  = str(random.randint(1990, 2004))
    targets = [month, day, year]
    labels  = ["Month", "Day", "Year"]
    log.info(f"Filling DOB: {month} {day}, {year}")

    # Tiny wait for the DOB row to render
    await asyncio.sleep(0.05)

    # --- Step 1: locate the 3 dropdown elements ----------------------------
    selector_groups = [
        # Newest Discord layouts use role=combobox
        '[role="combobox"]',
        # Older: aria-labelled buttons
        '[role="button"][aria-label="Month"], [role="button"][aria-label="Day"], [role="button"][aria-label="Year"]',
        # By name attr (some custom inputs)
        'input[name="month"], input[name="day"], input[name="year"]',
        # Native selects
        'select',
    ]
    dropdowns = []
    for sel in selector_groups:
        try:
            els = await page.query_selector_all(sel)
        except Exception:
            els = []
        # Filter to visible ones
        visible = []
        for el in els:
            try:
                visible_check = await el.apply("(el) => !!el.offsetParent")
                if visible_check:
                    visible.append(el)
            except Exception:
                visible.append(el)
        if len(visible) >= 3:
            dropdowns = visible[:3]
            log.debug(f"DOB: found 3 dropdowns via selector '{sel}'")
            break

    if not dropdowns or len(dropdowns) < 3:
        log.warning(f"DOB: couldn't locate 3 dropdowns (found {len(dropdowns)})")
        return False

    # --- Step 2: fill each dropdown ----------------------------------------
    all_ok = True
    for i, (dd, target, label) in enumerate(zip(dropdowns, targets, labels)):
        try:
            # Detect <select> vs custom widget
            tag = (await dd.apply("(el) => el.tagName") or "").upper()

            if tag == "SELECT":
                ok = await dd.apply(f"""(el) => {{
                    const opts = [...el.options];
                    const opt = opts.find(o => o.textContent.trim() === {json.dumps(target)})
                             || opts.find(o => o.value === {json.dumps(target)})
                             || opts.find(o => o.textContent.trim().toLowerCase()
                                              === {json.dumps(target.lower())});
                    if (!opt) return false;
                    const setter = Object.getOwnPropertyDescriptor(
                      window.HTMLSelectElement.prototype, 'value').set;
                    setter.call(el, opt.value);
                    el.dispatchEvent(new Event('input',  {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}""")
                if ok:
                    log.debug(f"DOB {label} = {target} (native select)")
                else:
                    log.warning(f"DOB {label}: option '{target}' not in <select>")
                    all_ok = False
                await asyncio.sleep(0.1)
                continue

            # Custom widget — real click via CDP to open it
            try:
                await dd.scroll_into_view()
            except Exception:
                pass
            await dd.click()
            await asyncio.sleep(0.03)  # listbox mount

            # -------------------------------------------------------------------
            # click_marked: query the element JS tagged with data-dob-pick
            # and click it directly — NO scroll_into_view before the click so
            # the element's position in the viewport is exactly where JS left it.
            # -------------------------------------------------------------------
            async def click_marked():
                try:
                    el = await page.query_selector('[data-dob-pick="1"]')
                    if el:
                        await el.click()
                        # Clean up the marker so it doesn't affect later queries
                        try:
                            await page.evaluate(
                                "document.querySelector('[data-dob-pick]')"
                                "?.removeAttribute('data-dob-pick')")
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass
                return False

            # -------------------------------------------------------------------
            # click_target: text-match scan of all visible options, click directly
            # (no extra scrollIntoView — that shifts layout and breaks the click).
            # -------------------------------------------------------------------
            async def click_target():
                try:
                    opts = await page.query_selector_all('[role="option"]')
                except Exception:
                    opts = []
                if not opts:
                    try:
                        opts = await page.query_selector_all('[role="menuitem"]')
                    except Exception:
                        opts = []
                for opt in opts:
                    try:
                        t = (await opt.text_content() or "").strip()
                    except Exception:
                        continue
                    if t == target or t.lower() == target.lower():
                        await opt.click()
                        return True
                return False

            picked = await click_target()

            if not picked:
                # Virtualised list (Year especially — ~127 rows for 1900→2026).
                # Strategy:
                #   1. Scroll the list container to bring the target row into view.
                #   2. Mark the element with data-dob-pick="1" from JS.
                #   3. Python queries [data-dob-pick="1"] and clicks it directly.
                #      No extra scroll or coordinate calculation — the element is
                #      already visible exactly where JS placed it.
                js_scroll = r"""
                async (targetText) => {
                  const sleep = ms => new Promise(r => setTimeout(r, ms));
                  const norm  = s => (s || '').trim().toLowerCase();
                  const want  = norm(targetText);

                  // Remove any leftover marker from a previous pass
                  document.querySelector('[data-dob-pick]')
                          ?.removeAttribute('data-dob-pick');

                  const findOpt = () => {
                    let opts = document.querySelectorAll('[role="option"]');
                    if (!opts.length) opts = document.querySelectorAll('[role="menuitem"]');
                    for (const o of opts) {
                      if (norm(o.textContent) === want) return o;
                    }
                    return null;
                  };

                  const markAndShow = (el) => {
                    // Scroll the option to the vertical centre of its container
                    // so it is fully visible, then mark it for Python to click.
                    el.scrollIntoView({block: 'nearest', inline: 'nearest'});
                    el.setAttribute('data-dob-pick', '1');
                  };

                  // 1. Already in DOM?
                  let opt = findOpt();
                  if (opt) { markAndShow(opt); await sleep(30); return true; }

                  // 2. Find scrollable containers (the virtualised scroller sits
                  //    outside [role="listbox"] in Discord's DOM).
                  const scrollables = [...document.querySelectorAll('*')].filter(el => {
                    if (!el.offsetParent) return false;
                    if (el.scrollHeight <= el.clientHeight + 4) return false;
                    const s = getComputedStyle(el);
                    return s.overflowY === 'auto' || s.overflowY === 'scroll';
                  });
                  scrollables.sort((a, b) => {
                    const aNear = !!a.querySelector('[role="option"],[role="listbox"],[role="menu"]');
                    const bNear = !!b.querySelector('[role="option"],[role="listbox"],[role="menu"]');
                    return (bNear - aNear);
                  });

                  for (const cont of scrollables) {
                    const total = cont.scrollHeight;

                    // Smart-jump for year values: 1990 ≈ 72%, 2004 ≈ 83%
                    // through the 1900-2026 list — hit those positions first.
                    const asNum = parseInt(want, 10);
                    const smartStops = [];
                    if (!isNaN(asNum) && asNum >= 1900 && asNum <= 2030) {
                      const frac   = (asNum - 1900) / (2026 - 1900);
                      const center = Math.round(total * frac);
                      for (let d = -3; d <= 3; d++) {
                        const p = center + Math.round(total * d / 30);
                        if (p >= 0 && p <= total) smartStops.push(p);
                      }
                    }

                    const fullStops = [0];
                    for (let i = 1; i <= 23; i++) fullStops.push(Math.round(total * i / 23));

                    for (const pos of [...smartStops, ...fullStops]) {
                      cont.scrollTop = pos;
                      cont.dispatchEvent(new Event('scroll', {bubbles: true}));
                      await sleep(30);
                      opt = findOpt();
                      if (opt) {
                        markAndShow(opt);
                        await sleep(40);   // let layout settle before Python clicks
                        return true;
                      }
                    }
                  }
                  return false;
                }
                """
                found = False
                try:
                    found = await page.evaluate(
                        f"({js_scroll})({json.dumps(target)})", await_promise=True)
                except TypeError:
                    found = await page.evaluate(f"({js_scroll})({json.dumps(target)})")
                except Exception as e:
                    log.debug(f"DOB {label}: scroll-search JS error: {e}")

                if found:
                    # JS marked the element — click it by attribute lookup,
                    # no scroll, no coordinate calc.
                    picked = await click_marked()
                    if not picked:
                        # Rare fallback: marker lost, try plain text scan
                        picked = await click_target()

            if picked:
                log.debug(f"DOB {label} = {target}")
            else:
                log.warning(f"DOB {label}: option '{target}' not found in listbox")
                all_ok = False
                try:
                    await page.evaluate("document.body.click()")
                except Exception:
                    pass

            await asyncio.sleep(0.02)  # tiny commit pause before next dropdown

        except Exception as e:
            log.warning(f"DOB {label} error: {e}")
            all_ok = False

    if all_ok:
        log.success(f"DOB set: {month} {day}, {year}")
    else:
        log.warning("DOB: one or more dropdowns failed — registration may be rejected")
    return all_ok

# Older signature used elsewhere; keep a no-op JS leftover removed

async def fill_registration_form(page, email: str, display_name: str, username: str, password: str) -> bool:
    """Fill Discord registration form using native send_keys so React tracks the input."""
    try:
        log.info("Waiting for registration form...")

        # Email
        try:
            el = await page.wait_for('input[name="email"]', timeout=10000)
            await el.send_keys(email)
        except Exception as e:
            log.error(f"Email field error: {e}"); return False

        # Display Name (global_name)
        try:
            el = await page.wait_for('input[name="global_name"]', timeout=3000)
            await el.send_keys(display_name)
        except Exception as e:
            log.debug(f"Display name field not found (may not exist): {e}")

        # Username
        try:
            el = await page.wait_for('input[name="username"]', timeout=3000)
            await el.send_keys(username)
        except Exception as e:
            log.error(f"Username field error: {e}"); return False

        # Password
        try:
            el = await page.wait_for('input[aria-label="Password"]', timeout=3000)
            await el.send_keys(password)
        except Exception:
            try:
                el = await page.wait_for('input[name="password"]', timeout=2000)
                await el.send_keys(password)
            except Exception as e:
                log.error(f"Password field error: {e}"); return False

        # Date of birth dropdowns
        await fill_date_of_birth(page)

        # Checkboxes (Terms of Service etc.)
        try:
            await page.evaluate(JS_UTILS)
            await page.evaluate('window.utils.clickAllCheckboxes()')
        except Exception:
            pass
        await asyncio.sleep(0.05)

        # Submit — try button text match first, then type=submit
        clicked = False
        try:
            buttons = await page.query_selector_all('button')
            for btn in buttons:
                txt = await btn.text_content()
                if txt and any(k in txt for k in ('Continue', 'Create', 'Submit', 'Register')):
                    await btn.click()
                    clicked = True
                    break
        except Exception:
            pass
        if not clicked:
            try:
                sub = await page.query_selector('[type="submit"]')
                if sub:
                    await sub.click()
                    clicked = True
            except Exception:
                pass
        if not clicked:
            try:
                clicked = await page.evaluate('''() => {
                    for (const btn of document.querySelectorAll('button')) {
                        const t = btn.textContent || '';
                        if (t.includes('Continue') || t.includes('Create') || t.includes('Submit')) {
                            btn.click(); return true;
                        }
                    }
                    return false;
                }''')
            except Exception:
                pass

        if clicked:
            log.success("Registration form submitted!")
            return True
        log.error("Could not find submit button")
        return False

    except Exception as e:
        log.error(f"Form fill error: {e}")
        return False

async def _openrouter_ask(api_key: str, model: str, prompt: str) -> str:
    """Send a prompt to OpenRouter and return the text reply."""
    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 60},
            timeout=20,
        ))
        data = resp.json()
        return (data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")).strip()
    except Exception as e:
        log.debug(f"OpenRouter error: {e}")
        return ""


async def _openrouter_vision_ask(api_key: str, model: str, img_b64: str, prompt: str) -> str:
    """Send a screenshot to OpenRouter vision model and return the text reply."""
    try:
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "max_tokens": 120,
        }
        resp = await asyncio.get_event_loop().run_in_executor(None, lambda: requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=25,
        ))
        data = resp.json()
        return (data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")).strip()
    except Exception as e:
        log.debug(f"OpenRouter vision error: {e}")
        return ""


async def _click_at(page, x: float, y: float):
    """Dispatch a real mouse-click at viewport coordinates."""
    try:
        await page.mouse.move(x, y)
        await page.mouse.click()
    except Exception:
        try:
            # Fallback: use CDP Input.dispatchMouseEvent directly
            await page.evaluate(
                f"() => document.elementFromPoint({x},{y})?.click()"
            )
        except Exception:
            pass


async def solve_captcha_accessibility(page, cfg: dict) -> bool:
    """
    Detect hCaptcha and solve it via the 3-dots → Accessibility text challenge.

    Approach:
      - Poll for EITHER the hCaptcha checkbox OR the challenge popup (bframe)
        because Discord sometimes shows the challenge directly, skipping the checkbox.
      - If checkbox appears → click it, then wait for the challenge popup.
      - Once bframe is visible → use JS getBoundingClientRect() to get its real
        viewport position → click ⋮ at bottom-left → screenshot via temp file
        → OpenRouter vision → type answer → submit.
      - Screenshot uses save_screenshot() to a temp file (avoiding nodriver API
        uncertainty that caused indefinite hangs).
      - Mouse clicks use page.mouse.click(x, y) with correct nodriver signature.
    """
    if not cfg.get("captchaSolverEnabled"):
        return False

    api_key   = cfg.get("openRouterApiKey", "")
    model     = cfg.get("openRouterModel", "google/gemini-2.0-flash-001")
    max_tries = int(cfg.get("captchaMaxAttempts", 4))

    if not api_key:
        log.warning("Captcha solver: OpenRouter API key is empty — skipping")
        return False

    # ── helper: take screenshot to temp file, return base64 ─────────────────
    async def _screenshot_b64() -> str:
        tmp = tempfile.mktemp(suffix=".jpg")
        try:
            await asyncio.wait_for(page.save_screenshot(tmp), timeout=10)
            with open(tmp, "rb") as fh:
                return base64.b64encode(fh.read()).decode()
        except Exception as e:
            log.debug(f"Screenshot error: {e}")
            return ""
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    # ── helper: get bounding rect of an iframe via JS ────────────────────────
    async def _iframe_rect(selector: str) -> Optional[dict]:
        """Returns {x, y, width, height} in viewport coords, or None."""
        try:
            r = await page.evaluate(f"""
                () => {{
                    const f = document.querySelector({json.dumps(selector)});
                    if (!f) return null;
                    const r = f.getBoundingClientRect();
                    return {{x: r.left, y: r.top, width: r.width, height: r.height}};
                }}
            """)
            return r if r and r.get("width") else None
        except Exception:
            return None

    # ── helper: real mouse click at viewport (x, y) ─────────────────────────
    async def _mouse_click(x: float, y: float):
        try:
            await page.mouse.click(x, y)
        except Exception as e:
            log.debug(f"mouse.click({x:.0f},{y:.0f}) error: {e}")

    # ── helper: get bframe rect, trying multiple selectors ───────────────────
    BFRAME_SELS = [
        'iframe[src*="hcaptcha.com"][src*="bframe"]',
        'iframe[title*="hCaptcha challenge"]',
        'iframe[src*="hcaptcha.com"][src*="challenge"]',
    ]

    async def _bframe_rect() -> Optional[dict]:
        for sel in BFRAME_SELS:
            r = await _iframe_rect(sel)
            if r:
                return r
        return None

    # ─────────────────────────────────────────────────────────────────────────
    for attempt in range(max_tries):
        if attempt > 0:
            log.info(f"Captcha solver: waiting 15 s before attempt {attempt + 1}...")
            await asyncio.sleep(15)

        log.info(f"Captcha solver: attempt {attempt + 1}/{max_tries}")

        # ── 1. Poll up to 20 s for challenge to appear ───────────────────────
        # Discord may show:
        #   (a) a checkbox first → we click it → bframe mounts
        #   (b) the bframe challenge directly (most common)
        bframe_pos = None
        checkbox_clicked = False

        for tick in range(40):   # 40 × 0.5 s = 20 s
            await asyncio.sleep(0.5)

            # Priority: bframe already visible?
            bframe_pos = await _bframe_rect()
            if bframe_pos:
                log.info(f"Challenge popup detected after {(tick+1)*0.5:.1f}s")
                break

            # Checkbox visible and not yet clicked?
            if not checkbox_clicked:
                cb_rect = await _iframe_rect('iframe[src*="hcaptcha.com"][src*="anchor"]')
                if not cb_rect:
                    cb_rect = await _iframe_rect('iframe[src*="hcaptcha.com"]')
                if cb_rect:
                    cx = cb_rect["x"] + cb_rect["width"] / 2
                    cy = cb_rect["y"] + cb_rect["height"] / 2
                    await _mouse_click(cx, cy)
                    checkbox_clicked = True
                    log.info(f"Clicked checkbox at ({cx:.0f},{cy:.0f}) — waiting for challenge…")

        if not bframe_pos:
            log.debug("No hCaptcha challenge appeared within 20 s — continuing without solve")
            return True   # no challenge = no captcha needed

        # ── 2. Click the ⋮ button at BOTTOM-LEFT of the bframe ───────────────
        dots_x = bframe_pos["x"] + 14
        dots_y = bframe_pos["y"] + bframe_pos["height"] - 22
        await _mouse_click(dots_x, dots_y)
        log.info(f"Clicked ⋮ at ({dots_x:.0f},{dots_y:.0f})")
        await asyncio.sleep(1.2)

        # ── 3. Click "Accessibility Challenge" in the ⋮ menu ────────────────
        # The menu item sits roughly 55 px above the footer
        menu_x = bframe_pos["x"] + bframe_pos["width"] // 2
        menu_y = bframe_pos["y"] + bframe_pos["height"] - 55
        await _mouse_click(menu_x, menu_y)
        log.info(f"Clicked accessibility menu item at ({menu_x:.0f},{menu_y:.0f})")
        await asyncio.sleep(1.8)

        # ── 4. Screenshot → vision model ─────────────────────────────────────
        img_b64 = await _screenshot_b64()
        if not img_b64:
            log.warning("Screenshot failed — skipping attempt")
            continue

        vision_prompt = (
            "This is a screenshot of an hCaptcha challenge popup on a Discord registration page. "
            "Look at the challenge popup carefully.\n"
            "- If it shows a TEXT INPUT BOX where the user must type a word or phrase "
            "(accessibility/audio challenge), reply with ONLY that word or phrase — nothing else.\n"
            "- If it is still a VISUAL PUZZLE (drag tiles, click images), "
            "reply with exactly: VISUAL\n"
            "No explanations. One-word or short-phrase answer only."
        )
        raw_answer = await _openrouter_vision_ask(api_key, model, img_b64, vision_prompt)
        log.info(f"Vision response: {raw_answer!r}")

        # ── 5. If still visual → Skip + retry ⋮ cycle ───────────────────────
        if not raw_answer or raw_answer.strip().upper() == "VISUAL":
            log.info("Still a visual puzzle — clicking Skip and retrying ⋮")
            skip_x = bframe_pos["x"] + bframe_pos["width"] - 48
            skip_y = bframe_pos["y"] + bframe_pos["height"] - 22
            await _mouse_click(skip_x, skip_y)
            log.info(f"Clicked Skip at ({skip_x:.0f},{skip_y:.0f})")
            await asyncio.sleep(2.5)

            # Re-click ⋮ on the fresh challenge
            bframe_pos = await _bframe_rect() or bframe_pos
            dots_x = bframe_pos["x"] + 14
            dots_y = bframe_pos["y"] + bframe_pos["height"] - 22
            await _mouse_click(dots_x, dots_y)
            await asyncio.sleep(1.2)
            menu_y = bframe_pos["y"] + bframe_pos["height"] - 55
            await _mouse_click(bframe_pos["x"] + bframe_pos["width"] // 2, menu_y)
            await asyncio.sleep(1.8)

            img_b64 = await _screenshot_b64()
            if img_b64:
                raw_answer = await _openrouter_vision_ask(
                    api_key, model, img_b64,
                    "hCaptcha accessibility text challenge. "
                    "There is now a text input box. "
                    "Reply with ONLY the exact word or phrase to type. No explanation."
                )
                log.info(f"Post-skip vision response: {raw_answer!r}")

        answer = (raw_answer or "").strip()
        if not answer or answer.upper() == "VISUAL":
            log.warning(f"Could not get text challenge answer on attempt {attempt + 1}")
            continue

        # ── 6. Type the answer ────────────────────────────────────────────────
        typed = False
        for inp_sel in ['input[type="text"]', 'textarea', 'input']:
            try:
                inp_el = await page.select(inp_sel, timeout=3)
                if inp_el:
                    await inp_el.clear_input()
                    await inp_el.send_keys(answer)
                    typed = True
                    log.info(f"Typed answer: {answer!r}")
                    break
            except Exception:
                continue

        if not typed:
            log.warning("Could not find text input in challenge — skipping attempt")
            continue

        await asyncio.sleep(0.5)

        # ── 7. Click Submit ───────────────────────────────────────────────────
        for sub_sel in ['button[type="submit"]', '[class*="submit" i]', '[class*="confirm" i]']:
            try:
                sub = await page.select(sub_sel, timeout=2)
                if sub:
                    await sub.click()
                    log.info("Clicked submit")
                    break
            except Exception:
                continue

        await asyncio.sleep(3)

        # ── 8. Check result ───────────────────────────────────────────────────
        try:
            still_has = await page.evaluate(
                "() => !!document.querySelector('iframe[src*=\"hcaptcha\"]')"
            )
            if not still_has:
                log.success("Captcha solved!")
                return True
            log.info("Captcha still present — will retry")
        except Exception:
            return True   # page navigated → solved

    log.warning(f"Captcha solver: gave up after {max_tries} attempts")
    return False


async def wait_for_account_creation(page, timeout: int = 300) -> bool:
    """Poll URL until Discord redirects to /channels/@me (account created)."""
    start = time.time()
    last_url = ""
    while (time.time() - start) < timeout:
        await asyncio.sleep(0.2)
        try:
            url = ""
            try:
                url = str(page.url) if page.url else ""
            except Exception:
                pass
            if not url:
                try:
                    raw = await page.evaluate('window.location.href')
                    url = str(raw) if raw else ""
                except Exception:
                    pass
            if url and url != last_url:
                last_url = url
            if url and ("discord.com/channels/@me" in url or "channels/%40me" in url or
                        ("discord.com/channels/" in url and "/channels/@me" not in url)):
                return True
        except Exception:
            pass
    log.error("Timeout waiting for account creation")
    return False

async def extract_token_via_api(email: str, password: str) -> Optional[str]:
    """Fetch Discord token by logging in via API — more reliable than localStorage."""
    for attempt in range(5):
        await asyncio.sleep(3)
        token = await fetch_discord_token(email, password)
        if token:
            log.success(f"Token fetched via API (attempt {attempt+1})")
            return token
        log.debug(f"Token attempt {attempt+1} returned empty")
    return None


# ============================================================================
# WORKER
# ============================================================================

DISPLAY_NAMES = [
    'Afham','Arhan','Ahmed','Ali','Hassan','Ibrahim','Karim','Malik','Omar','Rashid',
    'Alex','Jordan','Taylor','Morgan','Casey','Riley','Sam','Blake','Drew','Avery',
    'Henrik','Johan','Magnus','Nils','Pierre','Jean','Claude','Antoine','Benoit',
    'Akira','Kenji','Koji','Satoshi','Takeshi','Wei','Lei','Ming','Jun','Feng',
    'Arjun','Ankit','Aditya','Devesh','Harish','Raj','Vikram','Rohan','Sanjay',
    'Ashton','Bradley','Calvin','Derek','Ethan','Fiona','Graham','Harper','Jackson',
]

async def worker():
    """Account creation worker — launches browser, fills form, verifies email."""
    global SESSION_CREATED, SESSION_STOP

    if SESSION_STOP:
        return
    if SESSION_TARGET > 0 and SESSION_CREATED >= SESSION_TARGET:
        SESSION_STOP = True
        return

    # ADB IP rotation before each account
    adb_rot = config.get("adb_rotator")
    if adb_rot:
        log.info("Rotating IP via ADB...")
        adb_rot.rotate_ip()

    browser = None
    try:
        # ── 1. Get email from configured provider ──────────────────────────
        email_provider = config.get("emailProvider", "cybertemp")
        email_obj      = None

        if email_provider == "zeusx":
            zx_key = config.get("zeusxApiKey") or ZEUS_API_KEY
            if zx_key:
                result = ZeusXAPI(zx_key).buy_email()
                if result.get("success"):
                    email_obj = result
                    log.success(f"Zeus-X email: {result['email']}")
                else:
                    log.warning(f"Zeus-X failed: {result.get('error')} — trying CyberTemp fallback...")
            else:
                log.warning("Zeus-X selected but no API key — falling back to CyberTemp.")

        elif email_provider == "hotmail007":
            hm_key = config.get("hotmail007ClientKey", "")
            if hm_key:
                result = Hotmail007API(hm_key).buy_email()
                if result.get("success"):
                    email_obj = result
                    log.success(f"Hotmail007 email: {result['email']}")
                else:
                    log.error(f"Hotmail007 failed: {result.get('error')}")
            else:
                log.warning("Hotmail007 selected but no client key — falling back to CyberTemp.")

        elif email_provider == "draxono":
            dx_secret  = config.get("draxonoDomainSecret", "") or None
            dx_domains = _parse_domains(config.get("draxonoCustomDomains", ""))
            result = DraxonAPI(dx_secret, custom_domains=dx_domains).get_email()
            if result.get("success"):
                email_obj = result
                log.success(f"Draxono email: {result['email']}")
            else:
                log.warning(f"Draxono failed: {result.get('error')} — trying CyberTemp fallback...")

        if not email_obj:
            ct_key     = config.get("cybertempApiKey") or None
            ct_domains = _parse_domains(config.get("cybertempCustomDomains", ""))
            ct = CybertempAPI(ct_key, custom_domains=ct_domains)
            result = ct.get_email()
            if result.get("success"):
                email_obj = result
                email_provider = "cybertemp"
                log.success(f"CyberTemp email: {result['email']}")
            else:
                log.warning(f"CyberTemp failed: {result.get('error')}")

        if not email_obj or not email_obj.get("email"):
            log.error("Could not obtain an email address — skipping this worker cycle.")
            await asyncio.sleep(2)
            return

        account_email    = email_obj["email"]
        account_password = email_obj.get("password") or generate_password()
        account_username = generate_username()
        display_name     = random.choice(DISPLAY_NAMES)

        log.info(f"Worker starting | email={account_email} | provider={email_provider}")

        # ── 2. Launch browser ──────────────────────────────────────────────
        brave_path = config.get("brave_executable")
        # NOTE: do NOT pass --disable-blink-features=AutomationControlled.
        # Brave shows a yellow "you are using an unsupported command-line flag"
        # banner above the page when this flag is set. That banner shifts the
        # whole layout down and our click coordinates land on the wrong row
        # (e.g. the Year dropdown opens but the listbox click misses).
        # nodriver already removes the webdriver flag at the CDP level, so this
        # arg is redundant anyway.
        start_kw   = {"headless": False, "browser_args": [
            "--no-first-run", "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--no-default-browser-check",
        ]}
        if brave_path:
            start_kw["browser_executable_path"] = brave_path
            log.info(f"Launching Brave: {brave_path}")
        browser = await uc.start(**start_kw)

        page = await safe_browser_get(browser, "https://discord.com/register")
        log.info("Browser opened — navigated to Discord register page.")

        # Wait for email input to confirm page is ready
        page_ready = False
        for _ in range(20):
            try:
                if await page.query_selector('input[name="email"]'):
                    page_ready = True
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        if not page_ready:
            log.warning("Page load timeout — continuing anyway")
        await asyncio.sleep(0.5)

        # ── 3. Fill registration form ──────────────────────────────────────
        success = await fill_registration_form(page, account_email, display_name, account_username, account_password)
        if not success:
            log.error("Form fill failed — skipping")
            return

        # ── 4. Captcha solver + wait for account creation ───────────────────
        log.info("Waiting for captcha solve + account creation...")
        captcha_gave_up = asyncio.Event()

        async def _wait_manual_captcha():
            """Poll until hCaptcha iframe disappears (user solved it manually)."""
            log.info("Manual captcha mode — waiting up to 120s...")
            for _ in range(240):  # 240 × 0.5s = 120s
                await asyncio.sleep(0.5)
                try:
                    has_captcha = await page.evaluate(
                        "() => !!document.querySelector('iframe[src*=\"hcaptcha.com\"]')"
                    )
                    if not has_captcha:
                        log.success("Captcha cleared — continuing!")
                        return
                except Exception:
                    return
            log.warning("Manual captcha wait timed out (120s)")
            captcha_gave_up.set()

        async def _captcha_loop():
            solver_enabled = bool(config.get("captchaSolverEnabled"))
            if solver_enabled:
                solved = await solve_captcha_accessibility(page, config)
                if not solved:
                    # Solver failed — fall back to manual wait
                    await _wait_manual_captcha()
            else:
                # No solver — check if captcha is actually present before waiting
                await asyncio.sleep(1.5)
                try:
                    has_captcha = await page.evaluate(
                        "() => !!document.querySelector('iframe[src*=\"hcaptcha.com\"]')"
                    )
                except Exception:
                    has_captcha = False
                if has_captcha:
                    await _wait_manual_captcha()

        asyncio.ensure_future(_captcha_loop())

        # Wait for account creation (redirect to discord.com/channels/@me)
        # We use a dedicated task reference so we can tell if IT completed vs gave-up
        account_task = asyncio.ensure_future(wait_for_account_creation(page, timeout=300))
        gaveup_task  = asyncio.ensure_future(captcha_gave_up.wait())

        done, pending = await asyncio.wait(
            [account_task, gaveup_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Cancel the remaining task to avoid resource leaks
        for t in pending:
            t.cancel()

        # Only count as created if the account_task itself finished with True
        created = (account_task in done
                   and not account_task.exception()
                   and account_task.result() is True)
        if not created:
            log.error("Account creation failed — captcha not solved or timed out")
            return

        # ── 5. Extract token ───────────────────────────────────────────────
        log.info("Extracting Discord token...")
        token = await extract_token_via_api(account_email, account_password)

        # Fallback: try localStorage
        if not token:
            try:
                await page.evaluate(JS_UTILS)
                token = await page.evaluate('window.utils.waitForDiscordToken(8000)')
            except Exception:
                pass

        if not token:
            log.warning(f"No token captured for {account_email} — captcha or rate-limit")
            return

        # Clean up token format
        m = re.search(r'([A-Za-z0-9_-]{20,})\.([A-Za-z0-9_-]{6})\.([A-Za-z0-9_-]{27,})', token)
        if m:
            token = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"

        log.success(f"Token: {token[:30]}...")

        # ── 6. Email verification ──────────────────────────────────────────
        verified, _ = check_email_verified_api(token)
        if verified:
            log.success("Email already verified!")
        else:
            log.info("Email not verified — fetching verification link...")
            verify_url = None

            if email_provider == "hotmail007" and email_obj.get("token"):
                verify_url = fetch_verification_url_graph({
                    "token": email_obj.get("token", ""),
                    "uuid":  email_obj.get("uuid", ""),
                })
            elif email_provider == "zeusx":
                # Zeus-X accounts are Outlook — open outlook.com in a new tab to get the email
                log.info("Opening Outlook.com to fetch verification email for Zeus-X account...")
                try:
                    verify_url = fetch_verification_url_graph({
                        "token": email_obj.get("token", ""),
                        "uuid":  email_obj.get("uuid", ""),
                    })
                except Exception:
                    pass
                if not verify_url:
                    log.warning("Zeus-X: No Graph token available — manual inbox check required")
            elif email_provider == "cybertemp":
                ct_key       = config.get("cybertempApiKey") or None
                ct_inbox_tok = email_obj.get("inbox_token") or None
                verify_url   = fetch_verification_url_cybertemp(account_email, api_key=ct_key, inbox_token=ct_inbox_tok)
            elif email_provider == "draxono":
                dx_secret  = config.get("draxonoDomainSecret") or None
                verify_url = fetch_verification_url_draxono(account_email, domain_secret=dx_secret)

            if verify_url and not _is_valid_verify_url(verify_url):
                log.error(f"Refusing to navigate — extracted URL is not a valid verify link: {verify_url}")
                verify_url = None

            if verify_url:
                log.success(f"Got verification link — opening: {verify_url[:80]}...")
                try:
                    verify_page = await safe_browser_get(browser, verify_url)
                    await asyncio.sleep(4)
                    # Poll until Discord confirms verified
                    for _ in range(24):  # up to 2 minutes
                        await asyncio.sleep(5)
                        verified, _ = check_email_verified_api(token)
                        if verified:
                            log.success("Email verified successfully!")
                            break
                    if not verified:
                        log.warning("Verification not confirmed after 2 min — may still be processing")
                except Exception as e:
                    log.error(f"Error opening verify URL: {e}")
            else:
                log.warning("Could not retrieve verification email from inbox")

        # ── 7. Check token status and save to database ────────────────────
        log.info("Checking token status...")
        status = check_token(token)
        log.info(f"Token status: {status}")

        if api_client:
            save_result = api_client.save_token(token, email=account_email, account_pass=account_password, status=status)

            saved_by   = save_result.get("savedBy")
            token_id   = save_result.get("tokenId")
            today_total = save_result.get("todayTotal")
            is_dup     = save_result.get("duplicate", False)

            if saved_by:
                # Server confirmed the DB row was physically written
                confirm_msg = f"Saved via {saved_by}"
                if token_id:
                    confirm_msg += f" (DB #{token_id})"
                if today_total is not None:
                    confirm_msg += f" | today: {today_total}"
                log.success(confirm_msg)
            elif is_dup:
                log.warning(f"Duplicate token — already in DB, status refreshed (NOT counted in stats)")
            else:
                err = save_result.get("error") or save_result.get("detail") or "unknown error"
                log.error(f"TOKEN NOT SAVED TO DATABASE — {err}")
                log.error(f"  Token: {token[:30]}...")
        else:
            log.warning("No API client — token was NOT saved (api_client not initialised)")

        with LOCK:
            SESSION_CREATED += 1
            created_num = SESSION_CREATED

        status_icon = "+" if status == "VALID" else ("!" if status == "LOCKED" else "-")
        log.success(f"[{status_icon}] Account #{created_num} done — {status}")
        print(Colorate.Horizontal(Colors.green_to_cyan, f"  Total this session: {created_num}"))

        # ADB rotation after account (for next cycle)
        if adb_rot:
            adb_rot.rotate_ip()

    except Exception as e:
        log.error(f"Worker error: {e}")
        await asyncio.sleep(2)

    finally:
        if browser:
            try:
                await browser.stop()
            except Exception:
                pass

        cooldown = int(config.get("cooldownSeconds", 0))
        if cooldown > 0:
            log.info(f"Cooldown: waiting {cooldown}s before next account...")
            for remaining in range(cooldown, 0, -1):
                print(f"\r  {Fore.CYAN}Next account in {remaining}s...{Fore.RESET}   ", end="", flush=True)
                await asyncio.sleep(1)
            print()
        else:
            await asyncio.sleep(1.5)

# ============================================================================
# MAIN FUNCTION
# ============================================================================

async def main():
    global SESSION_TARGET, SESSION_CREATED, SESSION_STOP, api_client

    banner = f"""{Fore.MAGENTA}
  ███████╗██╗  ██╗██╗   ██╗██╗  ██╗██╗ ██████╗ ██╗  ██╗
  ██╔════╝██║ ██╔╝╚██╗ ██╔╝██║  ██║██║██╔════╝ ██║  ██║
  ███████╗█████╔╝  ╚████╔╝ ███████║██║██║  ███╗███████║
  ╚════██║██╔═██╗   ╚██╔╝  ██╔══██║██║██║   ██║██╔══██║
  ███████║██║  ██╗   ██║   ██║  ██║██║╚██████╔╝██║  ██║
  ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝

{Fore.CYAN}               ★  Discord Account Generator  ★{Fore.RESET}"""
    print(Colorate.Vertical(Colors.purple_to_blue, Center.XCenter(banner)))

    divider = f"{Fore.CYAN}{'━'*60}{Fore.RESET}"

    # ── Resolve API credentials (baked > config.json) ────────────
    api_cfg  = config.get("api", {})
    api_base = API_URL     or api_cfg.get("base_url",    "").strip()
    api_key  = API_KEY     or api_cfg.get("api_key",     "").strip()
    totp_sec = TOTP_SECRET or api_cfg.get("totp_secret", "").strip()

    if not api_base or not api_key or not totp_sec:
        log.error("API credentials not set! Edit API_URL, API_KEY, and TOTP_SECRET at the top of main.py before compiling.")
        sys.exit(1)

    # ── Worker Key Authentication ─────────────────────────────────
    print(f"\n{divider}")
    print(Colorate.Horizontal(Colors.cyan_to_blue, "  Enter your worker key to start"))
    print(f"{divider}\n")

    while True:
        worker_key_input = input(f"{Fore.GREEN}Worker Key: {Fore.RESET}").strip()
        if not worker_key_input:
            log.warning("Worker key cannot be empty")
            continue

        temp_client = WorkerAPIClient(api_base, api_key, totp_sec, worker_key_input)
        result = temp_client.validate_worker_key()

        if result.get("valid"):
            log.success(f"Welcome, {result.get('worker', {}).get('discordUsername', 'Worker')}!")
            api_client = temp_client
            break
        else:
            status = result.get("status", "ERROR")
            msg = result.get("message") or result.get("error") or "Unknown error"
            log.error(f"Key rejected [{status}]: {msg}")
            if status == "LOCKED":
                log.error("Your worker key is locked. Contact an admin.")
                sys.exit(1)
            if status == "EXPIRED":
                log.error("Your worker key has expired. Contact an admin to renew it.")
                sys.exit(1)
            if status == "ERROR":
                log.warning("Connection/server error — check the above message and try again.")
            else:
                log.warning("Wrong key — make sure you copied it exactly. Contact an admin if unsure.")

    print(f"\n{divider}")

    # ── Fetch remote config from API server ───────────────────────
    log.info("Fetching tool config from server...")
    try:
        import pyotp as _pyotp
        _totp_now = _pyotp.TOTP(totp_sec).now()
        _cfg_resp = requests.get(
            f"{api_base.rstrip('/')}/api/config",
            headers={"x-api-key": api_key, "x-totp-code": _totp_now},
            timeout=15,
            verify=False,
        )
        log.debug(f"Config fetch HTTP {_cfg_resp.status_code}")
        if _cfg_resp.status_code == 401:
            log.error("Config fetch rejected (401) — check that API_KEY and TOTP_SECRET in main.py match your server's WORKER_API_KEY and TOTP_SECRET.")
        elif _cfg_resp.status_code == 500:
            log.error(f"Config fetch server error (500): {_cfg_resp.text[:200]}")
        elif not _cfg_resp.ok:
            log.error(f"Config fetch failed (HTTP {_cfg_resp.status_code}): {_cfg_resp.text[:200]}")
        else:
            _cfg_data = _cfg_resp.json()
            remote_cfg = _cfg_data.get("config", {})
            if not isinstance(remote_cfg, dict):
                remote_cfg = {}
            config.update(remote_cfg)
            log.success("Config loaded from server.")
    except Exception as e:
        log.error(f"Could not fetch config from server: {e}")
        log.warning("Using safe defaults — set your config on the dashboard.")

    # ── Fill in any missing defaults ──────────────────────────────
    config.setdefault("emailProvider",          "cybertemp")
    config.setdefault("zeusxApiKey",            ZEUS_API_KEY)
    config.setdefault("hotmail007ClientKey",    "")
    config.setdefault("cybertempApiKey",        "")
    config.setdefault("cybertempCustomDomains", "")
    config.setdefault("draxonoDomainSecret",    "")
    config.setdefault("draxonoCustomDomains",   "")
    # Backward compat: an older field name was used briefly — promote it if present
    if config.get("draxonoApiKey") and not config.get("draxonoDomainSecret"):
        config["draxonoDomainSecret"] = config["draxonoApiKey"]
    config.setdefault("browser",             "chrome")
    config.setdefault("threads",             1)
    config.setdefault("target",              0)
    config.setdefault("proxyEnabled",        False)
    config.setdefault("proxyUrl",            "")
    config.setdefault("adbEnabled",            False)
    config.setdefault("adbPath",               "")
    config.setdefault("cooldownSeconds",       0)
    config.setdefault("captchaSolverEnabled",  False)
    config.setdefault("openRouterApiKey",      "")
    config.setdefault("openRouterModel",       "google/gemini-2.0-flash-001")
    config.setdefault("captchaMaxAttempts",    4)

    # If baked key exists and server didn't supply one, use baked key
    if not config["zeusxApiKey"] and ZEUS_API_KEY:
        config["zeusxApiKey"] = ZEUS_API_KEY

    # ── Auto-detect ADB (silent) ──────────────────────────────────
    config["adb_rotator"] = None
    if config.get("adbEnabled"):
        print(Colorate.Horizontal(Colors.cyan_to_blue, "  ┌─────────────────────────────────────────┐"))
        print(Colorate.Horizontal(Colors.cyan_to_blue, "  │  ADB IP Rotation — Initialising...     │"))
        print(Colorate.Horizontal(Colors.cyan_to_blue, "  └─────────────────────────────────────────┘"))
        try:
            rotator = ADBIPRotator(config.get("adbPath") or None)
            print(Colorate.Horizontal(Colors.green_to_cyan, f"  [ADB] Binary found: {rotator.adb}"))
            if rotator.check_device():
                current_ip = rotator.get_current_ip() or "unknown"
                config["adb_rotator"] = rotator
                print(Colorate.Horizontal(Colors.green_to_cyan, f"  [ADB] ✓ Ready — Current IP: {current_ip}"))
                log.success(f"ADB IP rotation active. IP: {current_ip}")
            else:
                print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB] ✗ No device found."))
                print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB]   → Check: USB cable connected?"))
                print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB]   → Check: USB Debugging enabled in Dev Options?"))
                print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB]   → Check: Phone screen unlocked & 'Allow USB Debugging' tapped?"))
                log.warning("ADB enabled but no device detected — running without IP rotation.")
        except FileNotFoundError as e:
            print(Colorate.Horizontal(Colors.blue_to_cyan, f"  [ADB] ✗ adb.exe not found: {e}"))
            print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB]   → Download platform-tools from developer.android.com"))
            print(Colorate.Horizontal(Colors.blue_to_cyan, "  [ADB]   → Or set ADB Path manually in the dashboard Tool Config"))
            log.warning("ADB init failed — adb binary not found.")
        except Exception as e:
            print(Colorate.Horizontal(Colors.blue_to_cyan, f"  [ADB] ✗ Error: {e}"))
            log.warning(f"ADB init error: {e}")

    # ── Brave browser ─────────────────────────────────────────────
    config["brave_executable"] = None
    if config.get("browser", "chrome").lower() == "brave":
        brave_path = find_brave_executable()
        if brave_path:
            config["brave_executable"] = brave_path
            log.success(f"Brave browser: {brave_path}")
        else:
            log.warning("Brave not found — falling back to Chrome.")

    # ── Log active settings ───────────────────────────────────────
    provider_label = {"zeusx": "Zeus-X", "hotmail007": "Hotmail007", "cybertemp": "CyberTemp", "draxono": "Draxono"}.get(config.get("emailProvider", ""), "CyberTemp")
    proxy_mode     = "ADB rotate" if config.get("adb_rotator") else "Proxy" if config.get("proxyEnabled") else "Direct"
    browser_label  = "Brave" if config.get("brave_executable") else "Chrome"
    thread_count   = int(config.get("threads", 1))
    SESSION_TARGET = int(config.get("target", 0))
    cooldown_val   = int(config.get("cooldownSeconds", 0))

    ct_custom_domains = _parse_domains(config.get("cybertempCustomDomains", ""))

    log.info(f"Provider : {provider_label}")
    if config.get("emailProvider", "cybertemp") == "cybertemp" and ct_custom_domains:
        log.info(f"CT Domains: {', '.join(ct_custom_domains)}  ({len(ct_custom_domains)} custom)")
    elif config.get("emailProvider", "cybertemp") == "cybertemp":
        log.info(f"CT Domains: CyberTemp default pool")
    log.info(f"Network  : {proxy_mode}")
    log.info(f"Browser  : {browser_label}")
    log.info(f"Threads  : {thread_count}")
    log.info(f"Target   : {'infinite' if SESSION_TARGET == 0 else SESSION_TARGET}")
    log.info(f"Cooldown : {'none' if cooldown_val == 0 else f'{cooldown_val}s between accounts'}")
    print(f"{divider}\n")

    SESSION_CREATED = 0
    SESSION_STOP = False

    # ── Start workers ─────────────────────────────────────────────
    log.info(f"Starting {thread_count} worker thread(s)...\n")

    while True:
        if SESSION_STOP:
            break
        tasks = [asyncio.create_task(worker()) for _ in range(thread_count)]
        await asyncio.gather(*tasks)
        if SESSION_STOP:
            break

    print(Colorate.Horizontal(Colors.green_to_cyan, "\n" + "━"*60))
    print(Colorate.Horizontal(Colors.green_to_cyan, f"  Done — {SESSION_CREATED} account(s) saved to database"))
    print(Colorate.Horizontal(Colors.green_to_cyan, "━"*60 + "\n"))


if __name__ == "__main__":
    warnings.filterwarnings('ignore', category=ResourceWarning)
    try:
        uc.loop().run_until_complete(main())
    except KeyboardInterrupt:
        print(Colorate.Horizontal(Colors.cyan_to_blue, "\n[INFO] Stopped by user"))
    except Exception as e:
        print(Colorate.Horizontal(Colors.blue_to_cyan, f"\n[ERROR] {e}"))
