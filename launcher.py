#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════╗
# ║              CTRL.PNL  —  Secure Tool Launcher                  ║
# ║      Streams & executes tool 100% in-memory  •  HMAC verified   ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# HOW IT WORKS:
#   1. Worker enters their key (or set WORKER_KEY env var)
#   2. Launcher authenticates to the CTRL.PNL API server
#   3. Server streams main.py encrypted + HMAC-signed
#   4. Launcher verifies integrity, then runs main.py in-memory
#      (nothing written to disk — source never visible on filesystem)
#
# CONFIGURE: Set CTRL_API_URL below to your Vercel deployment URL
#            after you deploy.  You can also set it as an env var.
# ─────────────────────────────────────────────────────────────────

import sys, os, subprocess, importlib

# ── YOUR VERCEL URL — update this after deploying ────────────────
_CTRL_API_URL = os.environ.get("CTRL_API_URL", "YOUR_VERCEL_URL_HERE")
# ─────────────────────────────────────────────────────────────────

# ── Step 1: auto-install deps ────────────────────────────────────
REQUIRED = ["requests", "colorama"]

def _installed(pkg):
    try:
        importlib.import_module(pkg.split("[")[0].replace("-", "_"))
        return True
    except ImportError:
        return False

def ensure_deps():
    missing = [p for p in REQUIRED if not _installed(p)]
    if not missing:
        return
    print(f"[*] Auto-installing: {', '.join(missing)} ...")
    for flags in ([], ["--user"]):
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", *flags, *missing],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            print("[+] Installed. Restarting launcher...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except subprocess.CalledProcessError:
            continue
    print(f"[!] Auto-install failed. Run: pip install {' '.join(missing)}")
    sys.exit(1)

ensure_deps()

# ── Step 2: imports ──────────────────────────────────────────────
import hmac as _hmac, hashlib, uuid, platform
import colorama
from colorama import Style
colorama.init(autoreset=True)

PUR  = "\033[38;5;141m"
CYN  = "\033[38;5;51m"
GRN  = "\033[38;5;82m"
RED  = "\033[38;5;196m"
YLW  = "\033[38;5;220m"
GRY  = "\033[38;5;240m"
WHT  = "\033[97m"
RST  = Style.RESET_ALL
BLD  = Style.BRIGHT
DIM  = Style.DIM

def p(col, txt):    return f"{col}{txt}{RST}"
def info(m):        print(p(CYN,  "  [*] ") + p(WHT, m))
def ok(m):          print(p(GRN,  "  [+] ") + p(WHT, m))
def warn(m):        print(p(YLW,  "  [!] ") + p(WHT, m))
def err(m):         print(p(RED,  "  [x] ") + p(WHT, m))
def dim_line(m):    print(p(GRY,  "      ") + p(GRY, m))

def banner():
    print()
    print(p(PUR, "  +--------------------------------------------------+"))
    print(p(PUR, "  |") + p(BLD + WHT, "          C T R L . P N L   L A U N C H E R        ") + p(PUR, "|"))
    print(p(PUR, "  |") + p(DIM + CYN, "       In-Memory  .  Authenticated  .  Verified     ") + p(PUR, "|"))
    print(p(PUR, "  +--------------------------------------------------+"))
    print()

# ── Step 3: machine fingerprint (for admin audit logs) ───────────
def _machine_id() -> str:
    try:
        node = uuid.getnode()
        raw  = f"{platform.node()}-{platform.machine()}-{node}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"

MACHINE_ID = _machine_id()

# ── Step 4: validate URL is configured ───────────────────────────
os.environ.setdefault("CTRL_API_URL", _CTRL_API_URL)

if _CTRL_API_URL == "YOUR_VERCEL_URL_HERE":
    print()
    print(p(RED, "  [!] CTRL_API_URL is not configured!"))
    print(p(YLW, "      Set your Vercel URL in launcher.py or via the CTRL_API_URL env var."))
    print()
    sys.exit(1)

def main():
    import requests

    banner()

    # ── 4a. Get worker key ────────────────────────────────────────
    worker_key = os.environ.get("WORKER_KEY", "").strip()
    if not worker_key:
        print(p(PUR, "  +--------------------------------------------------+"))
        print(p(PUR, "  |") + p(DIM + WHT, "  Enter your worker credentials below             ") + p(PUR, "|"))
        print(p(PUR, "  +--------------------------------------------------+"))
        print()
        worker_key = input(p(CYN, "  Worker Key > ")).strip()
        print()

    if not worker_key:
        err("Worker key is required.")
        sys.exit(1)

    api_url = os.environ["CTRL_API_URL"].rstrip("/")
    headers = {"x-api-key": worker_key, "X-Machine-ID": MACHINE_ID}

    # ── 4b. Fetch worker-safe env vars from server ────────────────
    info("Fetching configuration from server...")
    try:
        env_r = requests.get(
            f"{api_url}/api/tool/worker-env",
            headers=headers,
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        err(f"Cannot reach server: {api_url}")
        dim_line("Check your internet connection or contact your admin.")
        sys.exit(1)
    except requests.exceptions.Timeout:
        err("Server timed out fetching config. Try again.")
        sys.exit(1)

    if env_r.status_code == 401:
        err("Invalid worker key. Contact your admin.")
        sys.exit(1)
    elif env_r.status_code == 403:
        err("Your key has been revoked or expired. Contact your admin.")
        sys.exit(1)
    elif env_r.status_code != 200:
        err(f"Config fetch failed: HTTP {env_r.status_code}")
        sys.exit(1)

    try:
        server_env: dict = env_r.json().get("env", {})
    except Exception:
        server_env = {}

    # Apply all server-provided env vars
    for k, v in server_env.items():
        if k and isinstance(v, str):
            os.environ.setdefault(k, v)

    os.environ["CTRL_API_URL"] = api_url
    os.environ["WORKER_KEY"]   = worker_key

    ok(f"Configuration loaded  ({len(server_env)} env var(s) from server)")

    # ── 4c. Download tool from server ────────────────────────────
    info("Authenticating and downloading tool...")
    try:
        r = requests.get(
            f"{api_url}/api/tool/download",
            headers=headers,
            stream=True,
            timeout=60,
        )
    except requests.exceptions.ConnectionError:
        err(f"Cannot reach server: {api_url}")
        sys.exit(1)
    except requests.exceptions.Timeout:
        err("Server timed out. Try again.")
        sys.exit(1)

    if r.status_code == 401:
        err("Invalid worker key.")
        sys.exit(1)
    elif r.status_code == 403:
        err("Key revoked or expired. Contact your admin.")
        sys.exit(1)
    elif r.status_code == 404:
        warn("No tool uploaded yet. Ask your admin to upload main.py via the dashboard.")
        sys.exit(1)
    elif r.status_code == 429:
        warn("Too many downloads. Please wait a few minutes.")
        sys.exit(1)
    elif r.status_code != 200:
        err(f"Server error: HTTP {r.status_code}")
        try:    dim_line(r.json().get("error", "Unknown"))
        except: pass
        sys.exit(1)

    cd = r.headers.get("Content-Disposition", "")
    filename = "tool.py"
    if 'filename="' in cd:
        filename = cd.split('filename="')[1].rstrip('"')

    server_hmac = r.headers.get("X-Payload-HMAC", "")

    # Pull entire response into RAM — nothing written to disk
    chunks = []
    for chunk in r.iter_content(chunk_size=65536):
        if chunk:
            chunks.append(chunk)
    payload = b"".join(chunks)
    del chunks

    # ── 4d. Verify HMAC signature ─────────────────────────────────
    if server_hmac:
        expected = _hmac.new(
            worker_key.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not _hmac.compare_digest(expected, server_hmac):
            err("Payload integrity check FAILED — download may be tampered.")
            dim_line("Contact your admin immediately.")
            sys.exit(1)
        ok(f"Integrity verified  |  {p(CYN, filename)}  {p(GRY, f'({len(payload)//1024} KB)')}")
    else:
        warn(f"No HMAC — skipping integrity check  |  {p(CYN, filename)}")

    del server_hmac
    print()
    print(p(PUR, "  " + "-" * 50))
    print()

    # ── 4e. Execute in-memory (source never touches disk) ─────────
    if filename.endswith(".py"):
        try:
            code_str = payload.decode("utf-8")
            del payload
        except UnicodeDecodeError:
            err("Payload is not valid UTF-8 Python source.")
            sys.exit(1)

        try:
            code_obj = compile(code_str, "<secure-memory>", "exec", optimize=2)
        except SyntaxError as exc:
            err(f"Tool syntax error: {exc}")
            sys.exit(1)
        finally:
            del code_str  # erase source whether compile succeeded or not

        ns = {"__name__": "__main__", "__file__": "<secure-memory>"}
        try:
            exec(code_obj, ns)
        except SystemExit as e:
            sys.exit(e.code)
        except Exception as exc:
            err(f"Tool error: {type(exc).__name__}: {exc}")
            sys.exit(1)

    else:
        import tempfile, stat, random, string

        tmp_dir   = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
        rand_name = "".join(random.choices(string.ascii_lowercase, k=14))
        suffix    = os.path.splitext(filename)[1] or ""
        tmp_path  = os.path.join(tmp_dir, rand_name + suffix)

        with open(tmp_path, "wb") as f:
            f.write(payload)
        del payload

        try:
            os.chmod(tmp_path, stat.S_IRWXU)
            proc = subprocess.Popen([tmp_path], shell=(sys.platform == "win32"))
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            sys.exit(proc.wait())
        except Exception as exc:
            err(f"Launch failed: {exc}")
            try: os.unlink(tmp_path)
            except: pass
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("Interrupted.")
        sys.exit(0)
