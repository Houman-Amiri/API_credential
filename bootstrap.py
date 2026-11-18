"""One-click bootstrap used by start.bat.

Verifies, in order, that an isolated Python environment exists, tkinter is
available, playwright is installed and a Chromium-based browser can be
launched. Anything missing is installed; nothing is re-downloaded when it is
already present. Finally the Tkinter GUI is started.

Playwright's browser CDN is blocked in some countries ("Access denied ...
not available in your location"). When the download fails, the bootstrap falls
back to the Google Chrome / Microsoft Edge already installed on the PC, so the
app still runs without downloading anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "PSN Checker.py"
VENV = HERE / ".venv"
VPY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

REQUIRED_PACKAGES = ["playwright>=1.40"]

# Remember a geo-blocked download so later launches do not retry it every time.
BLOCKED_MARKER = HERE / ".browser_blocked"

# Alternative hosts for the Chromium build (used only if the default CDN fails).
DOWNLOAD_MIRRORS = [
    "https://cdn.npmmirror.com/binaries/playwright",
    "https://playwright.azureedge.net",
]


def run(cmd, env=None):
    """Run a visible command from the project directory."""
    print("    > " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=str(HERE), env=env)


def quiet(cmd):
    """Run a command without printing its output."""
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(HERE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def can_import(py, module):
    return quiet([py, "-c", "import " + module]).returncode == 0


def has_pip(py):
    return quiet([py, "-m", "pip", "--version"]).returncode == 0


def ensure_env():
    """Return (python executable, extra pip flags)."""
    if VPY.is_file() and has_pip(str(VPY)):
        print("[=] Reusing existing .venv")
        return str(VPY), []
    print("[*] Creating an isolated environment in .venv ...")
    rc = run([sys.executable, "-m", "venv", str(VENV)]).returncode
    if rc == 0 and VPY.is_file() and has_pip(str(VPY)):
        return str(VPY), []
    print("[!] venv unavailable - falling back to per-user installs.")
    return sys.executable, ["--user"]


def ensure_playwright(py, pip_flags):
    if can_import(py, "playwright"):
        print("[=] playwright is already installed")
        return True
    print("[*] Installing playwright from PyPI ...")
    cmd = [py, "-m", "pip", "install", *pip_flags, *REQUIRED_PACKAGES]
    if run(cmd).returncode != 0:
        print("[!] pip reported a problem; retrying after upgrading pip ...")
        run([py, "-m", "pip", "install", *pip_flags, "--upgrade", "pip"])
        if run(cmd).returncode != 0:
            return False
    return can_import(py, "playwright")


def chromium_executable(py):
    """Ask Playwright where Chromium should live (no download involved)."""
    code = (
        "from playwright.sync_api import sync_playwright\n"
        "p = sync_playwright().start()\n"
        "print(p.chromium.executable_path)\n"
        "p.stop()\n"
    )
    result = subprocess.run(
        [str(py), "-c", code],
        cwd=str(HERE),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    lines = (result.stdout or "").strip().splitlines()
    return lines[-1] if lines else None


def bundled_chromium(py):
    exe = chromium_executable(py)
    return exe if exe and Path(exe).is_file() else None


def system_browser():
    """Return (name, path) of an installed Chrome/Edge, or None."""
    candidates = []
    if os.name == "nt":
        roots = [os.environ.get(k) for k in
                 ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432")]
        rels = (("Google Chrome", os.path.join("Google", "Chrome", "Application", "chrome.exe")),
                ("Microsoft Edge", os.path.join("Microsoft", "Edge", "Application", "msedge.exe")))
        for rel_name, rel in rels:
            for root in roots:
                if not root:
                    continue
                path = Path(root) / rel
                if path.is_file():
                    candidates.append((rel_name, str(path)))
    elif sys.platform == "darwin":
        for name, path in (
            ("Google Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ("Microsoft Edge", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ):
            if Path(path).is_file():
                candidates.append((name, path))
    else:
        for name, cmd in (("Google Chrome", "google-chrome"), ("Chromium", "chromium"),
                          ("Chromium", "chromium-browser"), ("Microsoft Edge", "microsoft-edge")):
            found = quiet(["sh", "-c", f"command -v {cmd}"]).returncode == 0
            if found:
                candidates.append((name, cmd))
        return candidates[0] if candidates else None
    return candidates[0] if candidates else None


def download_chromium(py):
    """Try the default CDN, then mirrors. Returns True on success."""
    hosts = [(None, "the Playwright CDN")] + [(m, m) for m in DOWNLOAD_MIRRORS]
    for host, label in hosts:
        env = os.environ.copy()
        if host:
            env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
        print(f"[*] Downloading Playwright Chromium from {label} ...")
        rc = run([py, "-m", "playwright", "install", "chromium"], env=env).returncode
        if rc == 0 and bundled_chromium(py):
            return True
        print(f"[!] That source did not work.")
    return False


def ensure_browser(py):
    """Make sure some Chromium-based browser can be launched."""
    if bundled_chromium(py):
        print("[=] Chromium is already installed")
        BLOCKED_MARKER.unlink(missing_ok=True)
        return True

    fallback = system_browser()
    if fallback and BLOCKED_MARKER.is_file():
        print(f"[=] Using {fallback[0]} (the Chromium download was blocked before)")
        return True

    if download_chromium(py):
        print("[=] Chromium installed")
        BLOCKED_MARKER.unlink(missing_ok=True)
        return True

    if fallback:
        print("[!] Playwright's browser CDN is not reachable from here")
        print("    (the server answered: not available in your location).")
        print(f"[=] Falling back to {fallback[0]} which is already installed:")
        print(f"    {fallback[1]}")
        print("    No download is needed - the app will drive that browser instead.")
        try:
            BLOCKED_MARKER.write_text(fallback[0] + "\n", encoding="utf-8")
        except OSError:
            pass
        return True

    return False


def main():
    if not APP.is_file():
        print(f"[X] {APP.name} is missing next to start.bat")
        return 1

    py, pip_flags = ensure_env()
    print(f"[*] Python: {py}")

    if not can_import(py, "tkinter"):
        print("[X] This Python has no tkinter/Tcl-Tk, so the GUI cannot open.")
        print("    Re-run the Python installer, choose Modify, enable")
        print('    "tcl/tk and IDLE", then run start.bat again.')
        return 1

    if not ensure_playwright(py, pip_flags):
        print("[X] Could not install playwright. Check the internet connection")
        print("    or run manually:  python -m pip install playwright")
        return 1

    if not ensure_browser(py):
        print("[X] Chromium could not be downloaded and Chrome/Edge was not found.")
        print("    Install Google Chrome or Microsoft Edge, then run start.bat again.")
        print("    On a network where the CDN works you can also run:")
        print("      python -m playwright install chromium")
        return 1

    print("[*] All dependencies ready. Starting PSN Checker ...")
    return subprocess.call([str(py), str(APP)], cwd=str(HERE))


if __name__ == "__main__":
    sys.exit(main())
