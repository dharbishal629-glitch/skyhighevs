import { Router, type IRouter, type Request, type Response } from "express";
import { getEnvSetting } from "./envSettings";

const router: IRouter = Router();

router.get("/tool/launcher", async (req: Request, res: Response) => {
  // Derive the public URL from DB → env var → request origin (in that priority order).
  const proto = (req.headers["x-forwarded-proto"] as string | undefined)?.split(",")[0]?.trim() || req.protocol || "https";
  const host  = (req.headers["x-forwarded-host"] as string | undefined)?.split(",")[0]?.trim() || req.get("host") || "";
  const requestBase = `${proto}://${host}`;

  const dbUrl = await getEnvSetting("CTRL_API_URL");
  const apiBase = (dbUrl || process.env.CTRL_API_URL || requestBase).replace(/\/+$/, "");

  const script = `#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════╗
# ║              CTRL.PNL  —  Secure Tool Launcher                  ║
# ║      Streams & executes tool 100% in-memory  •  HMAC verified   ║
# ╚══════════════════════════════════════════════════════════════════╝

import sys, os, subprocess, importlib

# ── Step 1: auto-install deps ────────────────────────────────────────────────
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

# ── Step 2: imports ──────────────────────────────────────────────────────────
import hmac as _hmac, hashlib, uuid, platform
import colorama
from colorama import Style
colorama.init(autoreset=True)

PUR  = "\\033[38;5;141m"
CYN  = "\\033[38;5;51m"
GRN  = "\\033[38;5;82m"
RED  = "\\033[38;5;196m"
YLW  = "\\033[38;5;220m"
GRY  = "\\033[38;5;240m"
WHT  = "\\033[97m"
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

# ── Step 3: machine fingerprint (for admin audit logs) ───────────────────────
def _machine_id() -> str:
    try:
        import uuid as _uuid
        node = _uuid.getnode()
        raw  = f"{platform.node()}-{platform.machine()}-{node}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except Exception:
        return "unknown"

MACHINE_ID = _machine_id()

# ── Step 4: only the server URL is embedded — credentials are fetched live ───
os.environ.setdefault("CTRL_API_URL", "${apiBase}")

def main():
    import requests

    banner()

    # ── 4a. Get worker key ────────────────────────────────────────────────────
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

    # ── 4b. Fetch worker-safe env vars from server ────────────────────────────
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

    # Apply all server-provided env vars (setdefault so local overrides are kept)
    for k, v in server_env.items():
        if k and isinstance(v, str):
            os.environ.setdefault(k, v)

    # Always set CTRL_API_URL and WORKER_KEY so main.py can use them directly
    os.environ["CTRL_API_URL"] = api_url
    os.environ["WORKER_KEY"]   = worker_key

    ok(f"Configuration loaded  ({len(server_env)} env var(s) from server)")

    # ── 4c. Download tool ─────────────────────────────────────────────────────
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
        warn("No tool available yet. Contact your admin.")
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

    # ── 4d. Verify HMAC signature ─────────────────────────────────────────────
    # The server signs the payload with the worker key as the HMAC secret.
    # If this check fails, the payload was tampered with in transit.
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
        warn(f"No HMAC received — skipping integrity check  |  {p(CYN, filename)}")

    del server_hmac  # wipe from namespace
    print()
    print(p(PUR, "  " + "-" * 50))
    print()

    # ── 4e. Execute in-memory ─────────────────────────────────────────────────
    if filename.endswith(".py"):
        try:
            code_str = payload.decode("utf-8")
            del payload  # wipe raw bytes immediately after decode
        except UnicodeDecodeError:
            err("Payload is not valid UTF-8 Python source.")
            sys.exit(1)

        # Compile to bytecode first, then erase the source string so it is
        # never present as a readable variable while the tool is running.
        # optimize=2 strips docstrings and assert statements.
        try:
            code_obj = compile(code_str, "<secure-memory>", "exec", optimize=2)
        except SyntaxError as exc:
            err(f"Tool syntax error: {exc}")
            sys.exit(1)
        finally:
            del code_str  # erase source whether compile succeeded or not

        ns = {
            "__name__": "__main__",
            "__file__": "<secure-memory>",
        }
        try:
            exec(code_obj, ns)
        except SystemExit as e:
            sys.exit(e.code)
        except Exception as exc:
            err(f"Tool error: {type(exc).__name__}: {exc}")
            sys.exit(1)

    else:
        import tempfile, stat, random, string

        tmp_dir  = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
        rand_name = "".join(random.choices(string.ascii_lowercase, k=14))
        suffix   = os.path.splitext(filename)[1] or ""
        tmp_path = os.path.join(tmp_dir, rand_name + suffix)

        with open(tmp_path, "wb") as f:
            f.write(payload)
        del payload

        try:
            os.chmod(tmp_path, stat.S_IRWXU)
            proc = subprocess.Popen(
                [tmp_path], shell=(sys.platform == "win32")
            )
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
`;

  res.setHeader("Content-Type", "text/x-python");
  res.setHeader("Content-Disposition", 'attachment; filename="launcher.py"');
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate");
  res.setHeader("Pragma", "no-cache");
  res.send(script);
});

export default router;
