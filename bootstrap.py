"""One-click bootstrap used by start.bat.

Verifies, in order, that an isolated Python environment exists, tkinter is
available, playwright is installed and Playwright's Chromium browser has been
downloaded. Anything missing is installed; nothing is re-downloaded when it is
already present. Finally the Tkinter GUI is started.
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


def run(cmd):
    """Run a visible command from the project directory."""
    print("    > " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=str(HERE))


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


def ensure_chromium(py):
    exe = chromium_executable(py)
    if exe and Path(exe).is_file():
        print("[=] Chromium is already installed")
        return True
    print("[*] Downloading Playwright Chromium (first run only, ~150 MB) ...")
    if run([py, "-m", "playwright", "install", "chromium"]).returncode != 0:
        return False
    exe = chromium_executable(py)
    return bool(exe and Path(exe).is_file())


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

    if not ensure_chromium(py):
        print("[X] Could not download Chromium. Check the internet connection")
        print("    or run manually:  python -m playwright install chromium")
        return 1

    print("[*] All dependencies ready. Starting PSN Checker ...")
    return subprocess.call([str(py), str(APP)], cwd=str(HERE))


if __name__ == "__main__":
    sys.exit(main())
