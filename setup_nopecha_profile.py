"""
NopeCHA Profile Setup v6 - Chrome Web Store Install Method
- Opens Chrome Web Store page for NopeCHA
- Clicks "Add to Chrome" automatically
- Confirms the "Add Extension" dialog via keyboard
- Injects the API key into the extension storage via CDP
"""
import asyncio
import os
import sys
import json
import time
import platform
import shutil
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

import nodriver as uc
from nodriver import cdp

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROFILE_DIR = os.path.join(BASE_DIR, "nopecha_profile")
NOPECHA_WEBSTORE_URL = "https://chromewebstore.google.com/detail/nopecha-captcha-solver/dknlfmjaanfblgfdfebhijalfmhmjjjo?hl=en"
NOPECHA_EXT_ID = "dknlfmjaanfblgfdfebhijalfmhmjjjo"


def find_brave_executable() -> str:
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
        found = shutil.which("brave-browser") or shutil.which("brave")
        if found:
            return found
        candidates = [
            Path("/usr/bin/brave-browser"),
            Path("/usr/bin/brave"),
            Path("/usr/local/bin/brave-browser"),
            Path("/snap/bin/brave"),
        ]
    for p in candidates:
        if p and Path(p).is_file():
            return str(p)
    return ""


def resolve_browser_path(user_input: str) -> str:
    """
    Resolve whatever the user typed into an actual executable path.
    If they typed a real path that exists — use it.
    If they typed nothing, 'Brave', 'brave', 'chrome', or any non-path word — auto-detect.
    """
    inp = (user_input or "").strip()

    # If it looks like a real file path and it exists, use it directly
    if inp and os.path.isfile(inp):
        return inp

    # If they typed a known keyword or left it blank, auto-detect
    keywords = {"brave", "chrome", "browser", ""}
    if inp.lower() in keywords or not os.path.sep in inp:
        detected = find_brave_executable()
        if detected:
            print(f"  Auto-detected: {detected}")
            return detected
        # Nothing found — let nodriver try its own detection
        return ""

    # They typed a path but it doesn't exist — warn them
    print(f"  WARNING: '{inp}' not found. Trying auto-detect...")
    detected = find_brave_executable()
    if detected:
        print(f"  Auto-detected: {detected}")
        return detected
    return ""


async def run_setup(nopecha_key: str, brave_input: str = ""):
    if not nopecha_key:
        print("Error: API key cannot be empty.")
        return False

    print("=" * 60)
    print("  NOPECHA SETUP v6 - Web Store Installer")
    print("=" * 60)

    brave_path = resolve_browser_path(brave_input)

    os.makedirs(PROFILE_DIR, exist_ok=True)

    config = uc.Config()
    config.user_data_dir = PROFILE_DIR
    config.headless = False
    config.add_argument("--no-first-run")
    config.add_argument("--disable-default-apps")
    config.add_argument("--window-size=1200,800")
    if brave_path:
        config.browser_executable_path = brave_path
        print(f"  Using browser: {brave_path}")
    else:
        print("  Using system default browser (Chrome/Chromium)")

    print("[1/5] Launching browser with persistent profile...")
    browser = await uc.start(config=config)
    await asyncio.sleep(3)

    # ------------------------------------------------------------------ #
    # STEP 1 - Navigate to Web Store and click Add to Chrome
    # ------------------------------------------------------------------ #
    print("[2/5] Opening Chrome Web Store page...")
    page = await browser.get(NOPECHA_WEBSTORE_URL)
    await asyncio.sleep(6)

    already_installed = await page.evaluate('''
        (() => {
            const buttons = Array.from(document.querySelectorAll("button"));
            return !!buttons.find(b => b.innerText.includes("Remove from Chrome"));
        })()
    ''')

    if already_installed:
        print("[2/5] NopeCHA already installed! Skipping install step.")
    else:
        print("[2/5] Clicking 'Add to Chrome'...")
        clicked = await page.evaluate('''
            (() => {
                const buttons = Array.from(document.querySelectorAll("button"));
                const addBtn = buttons.find(b =>
                    b.innerText.trim() === "Add to Chrome" ||
                    b.innerText.includes("Add to Chrome")
                );
                if (addBtn) {
                    addBtn.click();
                    return true;
                }
                return false;
            })()
        ''')

        if not clicked:
            print("    WARNING: Could not find 'Add to Chrome' button automatically.")
            print("    Please manually click 'Add to Chrome' in the browser window.")
            print("    Waiting 20 seconds for you to do this...")
            await asyncio.sleep(20)
        else:
            print("    Clicked 'Add to Chrome'!")
            print("    Waiting for install dialog to pop up...")
            await asyncio.sleep(2)

            print("\n" + "=" * 60)
            print("    >>> ACTION REQUIRED: PLEASE CLICK 'Add extension' IN THE BROWSER <<<")
            print("=" * 60 + "\n")

            print("    The script has paused. Waiting 20 seconds for you to click it...")
            await asyncio.sleep(20)

    # ------------------------------------------------------------------ #
    # STEP 2 - Find the extension's service worker target via CDP
    # ------------------------------------------------------------------ #
    print("[3/5] Finding NopeCHA extension service worker...")
    ext_id = None
    sw_target_id = None

    for attempt in range(6):
        targets = await browser.connection.send(cdp.target.get_targets())
        if targets:
            for t in targets:
                url = str(t.url) if t.url else ""
                if f"chrome-extension://{NOPECHA_EXT_ID}" in url:
                    ext_id = NOPECHA_EXT_ID
                    sw_target_id = t.target_id
                    print(f"    Found! Target: {sw_target_id}")
                    break
                elif "chrome-extension://" in url and ("background" in url or "worker" in url.lower()):
                    parts = url.split("/")
                    if len(parts) >= 3 and len(parts[2]) == 32:
                        ext_id = parts[2]
                        sw_target_id = t.target_id
                        print(f"    Found via scan! ID: {ext_id}, Target: {sw_target_id}")
                        break
        if sw_target_id:
            break
        print(f"    Not found yet (attempt {attempt + 1}/6), waiting 3s...")
        await asyncio.sleep(3)

    if not sw_target_id:
        print("    ERROR: Could not find NopeCHA extension service worker!")
        print("    The extension may not have been installed correctly.")
        browser.stop()
        return False

    # ------------------------------------------------------------------ #
    # STEP 3 - Inject the API key by navigating to extension popup page
    # ------------------------------------------------------------------ #
    print(f"[4/5] Injecting API key via Extension UI...")
    key_injected = False

    try:
        ext_page = await browser.get(f"chrome-extension://{ext_id}/popup.html")
        await asyncio.sleep(4)

        try:
            print("    Physically clicking the 'Enter your key' button using nodriver CDP...")
            elem = await ext_page.find("Enter your key")
            if elem:
                await elem.click()
        except Exception as find_err:
            pass

        print("    Running robust UI automation script...")
        ui_res = await ext_page.evaluate(f'''
            (async () => {{
                let targetInput = null;

                for (let step = 0; step < 10; step++) {{
                    let inputs = Array.from(document.querySelectorAll('input'));
                    let visible = inputs.find(i => i.getBoundingClientRect().width > 0);

                    if (visible && visible.type !== 'checkbox') {{
                        targetInput = visible;
                        break;
                    }}

                    let all = Array.from(document.querySelectorAll('*'));
                    let texts = all.filter(e => e.textContent && e.textContent.includes('Enter your key') && e.children.length === 0);

                    if (texts.length > 0) {{
                        const triggerClick = (el) => {{
                            el.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                            el.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
                            el.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true}}));
                            el.click();
                        }};
                        triggerClick(texts[0]);
                        if (texts[0].parentElement) triggerClick(texts[0].parentElement);
                    }}

                    await new Promise(r => setTimeout(r, 500));
                }}

                if (!targetInput) return "Error: Input field never appeared.";

                let nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                if (nativeSetter) {{
                    nativeSetter.call(targetInput, '{nopecha_key}');
                }} else {{
                    targetInput.value = '{nopecha_key}';
                }}
                targetInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                targetInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

                await new Promise(r => setTimeout(r, 200));

                let all = Array.from(document.querySelectorAll('*'));
                let saveBtns = all.filter(e => e.textContent &&
                    (e.textContent.trim().toLowerCase() === 'save' || e.textContent.trim().toLowerCase() === 'submit') &&
                    e.getBoundingClientRect().width > 0 && e.tagName !== 'SCRIPT' && e.tagName !== 'STYLE'
                );

                if (saveBtns.length > 0) {{
                    saveBtns[saveBtns.length - 1].click();
                    return "Success: Found input, typed key, and clicked Save!";
                }}

                targetInput.focus();
                targetInput.dispatchEvent(new KeyboardEvent('keydown', {{'key': 'Enter', 'code': 'Enter', 'keyCode': 13, 'which': 13, 'bubbles': true}}));
                targetInput.dispatchEvent(new KeyboardEvent('keypress', {{'key': 'Enter', 'code': 'Enter', 'keyCode': 13, 'which': 13, 'bubbles': true}}));
                targetInput.dispatchEvent(new KeyboardEvent('keyup', {{'key': 'Enter', 'code': 'Enter', 'keyCode': 13, 'which': 13, 'bubbles': true}}));
                return "Success: Typed key and pressed Enter!";
            }})();
        ''')

        print(f"    UI Action result: {ui_res}")
        await asyncio.sleep(3)
        key_injected = True

    except Exception as e:
        print(f"    Injection error via popup UI: {e}")

    # ------------------------------------------------------------------ #
    # STEP 4 - Save profile and close
    # ------------------------------------------------------------------ #
    print("[5/5] Saving profile and closing browser...")
    await asyncio.sleep(2)

    try:
        browser.stop()
    except:
        pass

    print()
    if key_injected:
        print("=" * 60)
        print("  SUCCESS! NopeCHA is ready.")
        print(f"  Profile saved to: {PROFILE_DIR}")
        print(f"  Key: {nopecha_key[:8]}{'*' * (len(nopecha_key) - 8)}")
        print()
        print("  NEXT STEP: In your SkyHighEV dashboard, enable")
        print("  'NoPeCHA Auto-Solve' and it will use this profile.")
        print("=" * 60)
        return True
    else:
        print("=" * 60)
        print("  WARNING: Setup may not have completed fully.")
        print("  Delete 'nopecha_profile' folder and run again.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  SkyHighEV — NoPeCHA Profile Setup")
    print("=" * 60)

    if len(sys.argv) > 1:
        key = sys.argv[1].strip()
    else:
        key = input("  Enter your NoPeCHA API key: ").strip()

    brave = ""
    if len(sys.argv) > 2:
        brave = sys.argv[2].strip()
    else:
        brave_input = input("  Brave/Chrome path (press Enter to auto-detect): ").strip()
        if brave_input:
            brave = brave_input

    if key:
        asyncio.run(run_setup(key, brave))
    else:
        print("No key provided — exiting.")
