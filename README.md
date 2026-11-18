# API_credential

`PSN Checker.py` is a Tkinter GUI that drives headless Chromium via Playwright to
test email/password pairs against a login page. Use it only on accounts and
systems you own or are explicitly authorised to test.

## Requirements

- Python 3.9+
- `tkinter` — bundled with Python on Windows/macOS; on Debian/Ubuntu:
  `sudo apt install python3-tk`
- Playwright + its Chromium browser:

```bash
pip install playwright
playwright install chromium
```

## Run (Windows, one click)

Double-click **`start.bat`** — that's it. It will:

1. Find Python 3.9+ with `tkinter`, or install it (winget, falling back to the
   official python.org installer) if missing.
2. Create an isolated `.venv` in this folder.
3. `pip install playwright` and `playwright install chromium` **only if** they
   are not already present.
4. Launch the GUI.

The first run needs an internet connection (Chromium is ~150 MB); later runs
start immediately. Everything is kept inside this folder (`.venv/`) and is
git-ignored.

## Run (manual)

The filename contains a space, so it must be quoted:

```bash
python "PSN Checker.py"
```

or run `python bootstrap.py` to perform the same dependency checks first.

Enter the login URL, proxy list and combo file in the تنظیمات (Settings) tab and
click ذخیره تنظیمات (Save settings); the values are stored in `config.json`.
Results are written to `good.txt`, `bad.txt` and `unknown.txt`, and the گزارش
(Log) tab shows live progress.
