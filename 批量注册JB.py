#!/usr/bin/env python3
"""
JetBrains 批量注册工具 v3.0
- 所有可配置项从同目录 settings.json 读取
- 同目录自动查找指纹浏览器 chrome.exe
- 基于 dialog[open] 检测 reCAPTCHA 完成
- fingerprint-chromium 独立指纹
- 三重 Cookie 守护
- 6位 OTP 逐位键入
- 随机真人英文名
- tokens 页自动选国家 + 点 Add credit card
"""

import asyncio
import json
import os
import random
import re
import ssl
import string
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

# ==================== 路径基准 ====================
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv[0] else __file__)))
SETTINGS_FILE = SCRIPT_DIR / "settings.json"


# ==================== 加载配置 ====================
def load_settings():
    """加载同目录下的 settings.json，不存在则自动生成默认配置"""
    defaults = {
        "password": "hajimi123",
        "country_code": "JP",
        "country_name": "Japan",
        "concurrent_count": 5,
        "final_url": "https://account.jetbrains.com/licenses/tokens",
        "email_provider": {
            "api_base": "https://www.nimail.cn",
            "domain": "nimail.cn",
            "username_length": 10
        },
        "browser": {
            "chrome_exe": "auto",
            "headless": False,
            "profile_root": "auto",
            "start_maximized": True
        },
        "registration": {
            "auto_select_country": True,
            "auto_click_add_credit_card": True,
            "accept_all_checkboxes": True
        },
        "fingerprint": {
            "platforms": [
                ["windows", "10.0.0"], ["windows", "11.0.0"],
                ["macos", "14.5.0"], ["macos", "15.2.0"], ["linux", None]
            ],
            "brands": [
                ["Chrome", None], ["Edge", None], ["Opera", None], ["Vivaldi", None]
            ],
            "timezones": [
                "Asia/Shanghai", "Asia/Tokyo", "Asia/Singapore",
                "America/Los_Angeles", "America/New_York",
                "Europe/London", "Europe/Berlin"
            ],
            "cpu_cores": [2, 4, 6, 8, 12, 16],
            "lang": "en-US"
        },
        "timeouts": {
            "email_wait_seconds": 240,
            "recaptcha_click_seconds": 25,
            "recaptcha_dialog_seconds": 300,
            "page_load_seconds": 60
        },
        "output_file": "jb_accounts.txt"
    }

    if not SETTINGS_FILE.exists():
        print(f"⚙️ 未找到配置文件，自动生成默认配置: {SETTINGS_FILE}")
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4, ensure_ascii=False)
        return defaults

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        # 深度合并：用户配置覆盖默认配置
        merged = _deep_merge(defaults, user_cfg)
        return merged
    except Exception as e:
        print(f"⚠️ 配置文件解析失败: {e}")
        print(f"   使用默认配置继续运行")
        return defaults


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    result = base.copy()
    for k, v in override.items():
        if k.startswith("_"):  # 跳过注释字段
            continue
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ==================== 加载配置到全局 ====================
CFG = load_settings()

UNIFIED_PASSWORD = CFG["password"]
COUNTRY_CODE = CFG["country_code"]
COUNTRY_NAME = CFG["country_name"]
DEFAULT_CONCURRENT = CFG["concurrent_count"]
FINAL_URL = CFG["final_url"]

NIMAIL_API = CFG["email_provider"]["api_base"]
EMAIL_DOMAIN = CFG["email_provider"]["domain"]
EMAIL_USER_LEN = CFG["email_provider"]["username_length"]

HEADLESS = CFG["browser"]["headless"]
START_MAXIMIZED = CFG["browser"]["start_maximized"]

AUTO_SELECT_COUNTRY = CFG["registration"]["auto_select_country"]
AUTO_CLICK_ADD_CARD = CFG["registration"]["auto_click_add_credit_card"]
ACCEPT_ALL_CHECKBOXES = CFG["registration"]["accept_all_checkboxes"]

FP_PLATFORMS = [tuple(p) for p in CFG["fingerprint"]["platforms"]]
FP_BRANDS = [tuple(b) for b in CFG["fingerprint"]["brands"]]
FP_TIMEZONES = CFG["fingerprint"]["timezones"]
FP_CPU_CORES = CFG["fingerprint"]["cpu_cores"]
FP_LANG = CFG["fingerprint"]["lang"]

TIMEOUT_EMAIL = CFG["timeouts"]["email_wait_seconds"]
TIMEOUT_RECAPTCHA_CLICK = CFG["timeouts"]["recaptcha_click_seconds"]
TIMEOUT_RECAPTCHA_DIALOG = CFG["timeouts"]["recaptcha_dialog_seconds"]
TIMEOUT_PAGE_LOAD = CFG["timeouts"]["page_load_seconds"]

OUTPUT_FILE = Path(CFG["output_file"])

JB_SIGNUP = "https://account.jetbrains.com/signup"


# ==================== 浏览器路径 ====================
def _find_chrome():
    """在脚本所在目录及其子目录中查找 chrome.exe"""
    candidates = [
        SCRIPT_DIR / "chromium" / "Application" / "chrome.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    for depth1 in SCRIPT_DIR.iterdir():
        if depth1.is_dir():
            candidate = depth1 / "chrome.exe"
            if candidate.exists():
                return str(candidate)
            for depth2 in depth1.iterdir():
                if depth2.is_dir():
                    candidate = depth2 / "chrome.exe"
                    if candidate.exists():
                        return str(candidate)
    return None


def _resolve_chrome_path():
    """根据配置解析浏览器路径"""
    cfg_exe = CFG["browser"]["chrome_exe"]
    if cfg_exe == "auto":
        return _find_chrome()
    # 支持相对路径（相对于脚本目录）
    p = Path(cfg_exe)
    if not p.is_absolute():
        p = SCRIPT_DIR / p
    if p.exists():
        return str(p)
    # 绝对路径直接返回
    if Path(cfg_exe).exists():
        return cfg_exe
    return None


CHROME_PATH = _resolve_chrome_path()


def _resolve_profile_root():
    """根据配置解析 profile 目录"""
    cfg_root = CFG["browser"]["profile_root"]
    if cfg_root == "auto":
        return Path.home() / "jb_fingerprint_profiles"
    p = Path(cfg_root)
    if not p.is_absolute():
        return SCRIPT_DIR / p
    return p


PROFILE_ROOT = _resolve_profile_root()


# ==================== 姓名库 ====================
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Barbara", "William", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Margaret", "Anthony", "Betty", "Donald", "Sandra", "Mark", "Ashley",
    "Paul", "Dorothy", "Steven", "Kimberly", "Andrew", "Emily", "Kenneth", "Donna",
    "Joshua", "Michelle", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Laura",
    "Jeffrey", "Helen", "Ryan", "Sharon", "Jacob", "Cynthia", "Gary", "Kathleen",
    "Nicholas", "Amy", "Eric", "Shirley", "Jonathan", "Angela", "Stephen", "Anna",
    "Larry", "Ruth", "Justin", "Brenda", "Scott", "Pamela", "Brandon", "Nicole",
    "Frank", "Katherine", "Benjamin", "Virginia", "Gregory", "Catherine", "Samuel",
    "Christine", "Raymond", "Samantha", "Patrick", "Debra", "Alexander", "Janet",
    "Jack", "Rachel", "Dennis", "Carolyn", "Jerry", "Emma", "Tyler", "Maria",
    "Aaron", "Heather", "Henry", "Diane", "Douglas", "Julie", "Adam", "Joyce",
    "Peter", "Victoria", "Nathan", "Kelly", "Zachary", "Christina", "Walter", "Joan",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
    "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales",
    "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson",
    "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward",
    "Richardson", "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray",
    "Mendoza", "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel",
    "Myers", "Long", "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry",
]


def random_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


# ==================== NiMail ====================
def _req(url, post=None):
    headers = {"Origin": NIMAIL_API, "Referer": NIMAIL_API + "/",
               "User-Agent": "Mozilla/5.0 Chrome/131.0.0.0"}
    if post is not None:
        data = urllib.parse.urlencode(post).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        data = None
    req = urllib.request.Request(url, data=data, headers=headers,
                                method="POST" if post else "GET")
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(),
                                    timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def rnd_mail():
    c = string.ascii_lowercase + string.digits
    return "".join(random.choice(c) for _ in range(EMAIL_USER_LEN)) + f"@{EMAIL_DOMAIN}"


def apply_mail(addr):
    s, b = _req(NIMAIL_API + "/api/applymail", {"mail": addr})
    try:
        return json.loads(b).get("success") == "true"
    except:
        return False


def get_mails(addr, since=0):
    s, b = _req(NIMAIL_API + "/api/getmails",
                {"mail": addr, "time": str(since),
                 "_": str(int(time.time() * 1000))})
    try:
        return json.loads(b)
    except:
        return {"success": "false"}


def get_mail_body(addr, mid):
    s, b = _req(f"{NIMAIL_API}/api/raw-html/{addr}/{mid}")
    return b if s == 200 else ""


def extract_jb_link(html):
    link_patterns = [
        r'href="(https://account\.jetbrains\.com/[^"]*(?:confirm|verify|signup|activate|reg|token)[^"]*)"',
        r'href="(https://[^"]*jetbrains[^"]*(?:confirm|verify|token|activate)[^"]*)"',
    ]
    for p in link_patterns:
        m = re.search(p, html, re.I)
        if m:
            return ("LINK", m.group(1).replace("&", "&"))
    span_patterns = [
        r'<span[^>]*font-size:\s*2[0-9]px[^>]*font-weight:\s*bold[^>]*>\s*(\d{6})\s*</span>',
        r'<span[^>]*font-weight:\s*bold[^>]*font-size:\s*2[0-9]px[^>]*>\s*(\d{6})\s*</span>',
        r'<(?:b|strong)[^>]*>\s*(\d{6})\s*</(?:b|strong)>',
        r'<span[^>]*font-size:\s*(?:2[0-9]|3[0-9])px[^>]*>\s*(\d{6})\s*</span>',
    ]
    for p in span_patterns:
        m = re.search(p, html, re.I)
        if m:
            return ("CODE", m.group(1))
    text = re.sub(r'<[^>]+>', ' ', html)
    for p in [r'(?:confirmation|verification|your|one[- ]time|security)\s*code[^\d]{0,60}(\d{6})',
              r'code\s*[:：]\s*(\d{6})', r'(\d{6})\s*(?:is your|is the)']:
        m = re.search(p, text, re.I)
        if m:
            return ("CODE", m.group(1))
    six = re.findall(r'(?<!\d)(\d{6})(?!\d)', text)
    filtered = [c for c in six if not c.startswith('20') and not c.startswith('19')]
    if filtered:
        return ("CODE", filtered[0])
    m = re.search(r'(?:code|verification|verify)[^\d]{0,40}(\d{4,8})', html, re.I)
    if m:
        return ("CODE", m.group(1))
    return None


def log(tag, msg):
    print(f"[{tag}] {msg}", flush=True)


async def wait_email(addr, tag, timeout=None):
    if timeout is None:
        timeout = TIMEOUT_EMAIL
    log(tag, f"📬 等待 {addr} 的验证邮件...")
    start = time.time()
    seen = set()
    since = 0
    while time.time() - start < timeout:
        r = get_mails(addr, since)
        if r.get("success") == "true":
            since = r.get("time", since)
            for m in r.get("mail", []):
                mid = m.get("id")
                if mid in seen:
                    continue
                seen.add(mid)
                frm = (m.get("from") or "").lower()
                subj = (m.get("subject") or "").lower()
                if "jetbrains" in frm or "jetbrains" in subj or "noreply" in frm:
                    html = get_mail_body(addr, mid)
                    res = extract_jb_link(html)
                    if res:
                        log(tag, f"✅ 已收到邮件 ({res[0]}: {str(res[1])[:60]})")
                        return res
        await asyncio.sleep(4)
    return None


# ==================== Cookie 守护 ====================
COOKIE_KILLER_SCRIPT = """
(function() {
    if (window.__cookieKillerInit) return;
    window.__cookieKillerInit = true;
    const tryKill = () => {
        try {
            if (window.cookiehub && typeof window.cookiehub.allow === 'function') window.cookiehub.allow();
            const btn = document.querySelector('button.ch2-allow-all-btn, .ch2-btn-primary');
            if (btn) btn.click();
            document.querySelectorAll('button').forEach(b => {
                const t = (b.textContent||'').trim().toLowerCase();
                if (t === 'accept all' || t === 'accept all cookies') b.click();
            });
        } catch(e) {}
    };
    const activate = () => {
        tryKill();
        try { const obs = new MutationObserver(() => tryKill());
              obs.observe(document.documentElement, {childList:true, subtree:true}); } catch(e) {}
        let c=0; const iv=setInterval(()=>{tryKill();c++;if(c>120)clearInterval(iv);},500);
    };
    if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',activate);
    else activate();
})();
"""


async def dismiss_cookie_banner(page, tag):
    try:
        r = await page.evaluate("""() => {
            try { if (window.cookiehub && typeof window.cookiehub.allow==='function'){window.cookiehub.allow();return 'api';}} catch(e){}
            const b=document.querySelector('button.ch2-allow-all-btn,.ch2-btn-primary');if(b){b.click();return 'dom';}
            for(const x of document.querySelectorAll('button')){const t=(x.textContent||'').trim().toLowerCase();
            if(t==='accept all'){x.click();return 'txt';}} return null;}""")
        if r:
            return True
    except:
        pass
    for sel in ['button.ch2-allow-all-btn', '.ch2-btn-primary',
                'button:has-text("Accept All")']:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=1500, force=True)
                return True
        except:
            pass
    return False


async def inject_cookie_killer(page, tag):
    try:
        await page.evaluate(COOKIE_KILLER_SCRIPT)
    except:
        pass


async def cookie_guard_loop(page, tag, stop_event):
    while not stop_event.is_set():
        try:
            await dismiss_cookie_banner(page, tag)
        except:
            pass
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            break


# ==================== reCAPTCHA ====================
async def try_click_recaptcha(page, tag, max_wait=None):
    if max_wait is None:
        max_wait = TIMEOUT_RECAPTCHA_CLICK
    log(tag, "🤖 查找 reCAPTCHA...")
    start = time.time()
    while time.time() - start < max_wait:
        try:
            for f in page.frames:
                url = f.url or ''
                if 'recaptcha' in url and 'anchor' in url:
                    try:
                        cb = f.locator('#recaptcha-anchor')
                        if await cb.count() > 0:
                            await cb.wait_for(state="visible", timeout=3000)
                            await cb.click(timeout=3000)
                            log(tag, "🤖 ✅ 已点击 reCAPTCHA 复选框")
                            return True
                    except:
                        pass
                    try:
                        cb2 = f.locator('.recaptcha-checkbox-border')
                        if await cb2.count() > 0:
                            await cb2.first.click(timeout=3000, force=True)
                            log(tag, "🤖 ✅ 已点击 reCAPTCHA（备用）")
                            return True
                    except:
                        pass
        except:
            pass
        await asyncio.sleep(1)
    log(tag, "⚠️ 未能自动点击 reCAPTCHA，请手动")
    return False


async def wait_dialog_closed(page, tag, timeout=None, check_interval=1.0):
    if timeout is None:
        timeout = TIMEOUT_RECAPTCHA_DIALOG
    log(tag, "⏳ 等待 reCAPTCHA 对话框关闭（检测 dialog[open] 消失）...")
    start = time.time()

    initial_dialog = await page.evaluate("""() => {
        const dialog = document.querySelector('dialog[open]');
        return !!dialog;
    }""")
    log(tag, f"🔍 初始 dialog 状态: {'存在' if initial_dialog else '不存在'}")

    while time.time() - start < timeout:
        dialog_exists = await page.evaluate("""() => {
            const dialog = document.querySelector('dialog[open]');
            return !!dialog;
        }""")

        if not dialog_exists:
            await asyncio.sleep(0.5)
            dialog_exists_again = await page.evaluate("""() => {
                const dialog = document.querySelector('dialog[open]');
                return !!dialog;
            }""")
            if not dialog_exists_again:
                elapsed = time.time() - start
                log(tag, f"✅ reCAPTCHA 对话框已关闭（耗时 {elapsed:.1f}s）")
                await page.wait_for_timeout(1000)
                return True

        if await _check_left_email_page(page):
            log(tag, "✅ 已离开邮箱页，视为完成")
            return True

        if int(time.time() - start) % 15 == 0 and int(time.time() - start) > 0:
            log(tag, f"⏳ 等待 dialog 关闭... ({time.time() - start:.0f}s)")

        await asyncio.sleep(check_interval)

    log(tag, f"⚠️ 等待超时（{timeout}s），dialog 仍然存在")
    return False


async def _check_left_email_page(page):
    try:
        if await page.locator('input[name="otp-1"]').count() > 0:
            return True
    except:
        pass
    try:
        loc = page.locator('text=/confirm your email|enter the code|check your|we.*sent/i')
        if await loc.count() > 0 and await loc.first.is_visible(timeout=300):
            return True
    except:
        pass
    try:
        if await page.locator('input[name="firstName"]').count() > 0:
            return True
    except:
        pass
    try:
        url = page.url
        if 'authSessionId' not in url and '/signup' not in url:
            return True
    except:
        pass
    return False


# ==================== Continue 按钮强化 ====================
async def click_continue_react(page, tag, max_attempts=20, interval=1.0):
    log(tag, "🖱️ 等待 Continue 按钮可点击...")

    for wait_i in range(30):
        dialog_exists = await page.evaluate("""() => {
            const dialog = document.querySelector('dialog[open]');
            return !!dialog;
        }""")
        if not dialog_exists:
            log(tag, f"✅ dialog 已关闭，准备点击 Continue（等待 {wait_i}s）")
            await page.wait_for_timeout(800)
            break
        if wait_i % 5 == 0 and wait_i > 0:
            log(tag, f"⏳ 等待 dialog 关闭... ({wait_i}s)")
        await asyncio.sleep(1)
    else:
        log(tag, "⚠️ dialog 仍然存在，强制尝试点击")

    try:
        btn = page.locator('button[type="submit"]').first
        await btn.scroll_into_view_if_needed(timeout=3000)
        await page.wait_for_timeout(500)
    except:
        pass

    for attempt in range(max_attempts):
        if await _check_left_email_page(page):
            log(tag, f"✅ 已离开邮箱页（第 {attempt + 1} 次检查）")
            return True

        try:
            is_disabled = await page.evaluate("""() => {
                const btn = document.querySelector('button[type="submit"]');
                if (!btn) return false;
                return btn.disabled === true || btn.getAttribute('aria-disabled') === 'true';
            }""")
            if is_disabled:
                log(tag, "⏳ 按钮禁用中，等待...")
                await asyncio.sleep(1)
                continue
        except:
            pass

        clicked = False

        try:
            result = await page.evaluate("""() => {
                const form = document.querySelector('form');
                if (!form) return 'no_form';
                const dialog = document.querySelector('dialog[open]');
                if (dialog) return 'dialog_still_open';
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                    return 'requestSubmit';
                }
                return 'no_requestSubmit';
            }""")
            if result == 'requestSubmit':
                clicked = True
                if attempt == 0:
                    log(tag, "🖱️ requestSubmit 提交")
        except:
            pass

        if not clicked:
            try:
                btn = page.locator('button[type="submit"]').first
                if await btn.count() > 0 and await btn.is_visible(timeout=500):
                    await btn.click(timeout=3000)
                    clicked = True
                    if attempt == 0:
                        log(tag, "🖱️ Playwright 点击 Continue")
            except:
                pass

        if not clicked:
            try:
                email_input = page.locator('input[name="email"]')
                if await email_input.count() > 0 and await email_input.is_visible(timeout=500):
                    await email_input.focus()
                    await page.keyboard.press("Enter")
                    clicked = True
                    if attempt == 0:
                        log(tag, "🖱️ 键盘 Enter 提交")
            except:
                pass

        if not clicked:
            try:
                await page.evaluate("""() => {
                    const btn = document.querySelector('button[type="submit"]');
                    if (btn) {
                        const dialog = document.querySelector('dialog[open]');
                        if (dialog) dialog.removeAttribute('open');
                        btn.click();
                    }
                }""")
                clicked = True
                if attempt == 0:
                    log(tag, "🖱️ JS 点击 Continue")
            except:
                pass

        if clicked:
            await page.wait_for_timeout(500)
            if await _check_left_email_page(page):
                log(tag, "✅ 提交成功，进入下一步")
                return True

        if attempt > 0 and attempt % 5 == 0:
            log(tag, f"🔄 Continue 第 {attempt + 1} 次尝试...")

        await asyncio.sleep(interval)

    log(tag, "⚠️ Continue 轮询超时")
    return False


# ==================== OTP ====================
async def fill_otp_code(page, code, tag):
    code = str(code).strip()
    try:
        first = page.locator('input[name="otp-1"]')
        if await first.count() > 0:
            log(tag, f"📝 拆分式 OTP（{len(code)}位）")
            for i in range(1, 7):
                try:
                    inp = page.locator(f'input[name="otp-{i}"]')
                    if await inp.count() > 0:
                        await inp.fill("")
                except:
                    pass
            await first.click()
            await page.wait_for_timeout(200)
            for ch in code:
                await page.keyboard.type(ch, delay=100)
                await page.wait_for_timeout(100)
            await page.wait_for_timeout(500)
            filled = ""
            for i in range(1, 7):
                try:
                    inp = page.locator(f'input[name="otp-{i}"]')
                    if await inp.count() > 0:
                        filled += (await inp.input_value() or "")
                except:
                    pass
            if filled == code:
                log(tag, f"✅ OTP: {filled}")
                return True
            log(tag, f"⚠️ 键盘填入 '{filled}'，降级 fill")
            for idx, ch in enumerate(code):
                if idx >= 6:
                    break
                try:
                    inp = page.locator(f'input[name="otp-{idx + 1}"]')
                    if await inp.count() > 0:
                        await inp.fill(ch)
                        await inp.evaluate(
                            "(el)=>{el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}")
                        await page.wait_for_timeout(120)
                except:
                    pass
            return True
    except Exception as e:
        log(tag, f"⚠️ OTP 异常: {e}")
    try:
        single = page.locator(
            'input[inputmode="numeric"], input[autocomplete="one-time-code"]').first
        if await single.count() > 0:
            await single.fill(code)
            return True
    except:
        pass
    try:
        await page.keyboard.type(code, delay=100)
        return True
    except:
        pass
    return False


# ==================== 注册表单 ====================
async def fill_registration_form(page, first_name, last_name, password, tag):
    log(tag, f"📝 填写: {first_name} {last_name}")
    try:
        await page.wait_for_selector('input[name="firstName"]', timeout=15000)
    except:
        log(tag, "⚠️ 未检测到注册表单，可能已跳过")
        return False

    for name, val in [("firstName", first_name), ("lastName", last_name),
                      ("password", password)]:
        try:
            el = page.locator(f'input[name="{name}"]').first
            await el.fill("")
            await el.click()
            await el.type(val, delay=50)
            await el.dispatch_event('input')
            await el.dispatch_event('change')
            await page.wait_for_timeout(200)
        except Exception as e:
            log(tag, f"⚠️ {name} 失败: {e}")

    try:
        pwds = page.locator('input[type="password"]')
        for i in range(await pwds.count()):
            el = pwds.nth(i)
            try:
                if await el.is_visible(timeout=500) and not (await el.input_value()):
                    await el.fill(password)
            except:
                pass
    except:
        pass
    return True


async def submit_create_account(page, tag):
    for sel in ['button:has-text("Create account")', 'button:has-text("Sign up")',
                'button:has-text("Register")', 'button[type="submit"]']:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible(timeout=1000):
                await btn.click(force=True)
                log(tag, "✅ 点击 Create account")
                return True
        except:
            pass
    try:
        await page.locator('button[type="submit"]').last.click(force=True)
        return True
    except:
        pass
    return False


# ==================== tokens 页面：选国家 + Add credit card ====================
async def setup_tokens_page(page, tag):
    if not AUTO_SELECT_COUNTRY and not AUTO_CLICK_ADD_CARD:
        log(tag, "⏭️ 跳过国家选择和信用卡设置（配置已关闭）")
        return True

    log(tag, f"🌏 开始设置国家({COUNTRY_NAME})和支付方式...")
    await page.wait_for_timeout(2000)

    if AUTO_SELECT_COUNTRY:
        # 第一步：点击 "Select country" 链接
        try:
            select_link = page.locator(
                'a:has-text("Select country"), a.btn.link:has-text("Select")')
            if await select_link.count() > 0:
                await select_link.first.click(force=True)
                log(tag, "🖱️ 已点击 Select country")
                await page.wait_for_timeout(1500)
            else:
                log(tag, "⚠️ 未找到 Select country 链接，可能已设置")
        except Exception as e:
            log(tag, f"⚠️ 点击 Select country 失败: {e}")

        # 第二步：选国家（使用配置中的 country_code 和 country_name）
        try:
            js_select = f"""() => {{
                const sel = document.querySelector('select[name="country"]');
                if (!sel) return 'no_select';
                sel.value = '{COUNTRY_CODE}';
                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                const chosenSpan = document.querySelector('.chosen-single span');
                if (chosenSpan) chosenSpan.textContent = '{COUNTRY_NAME}';
                try {{
                    if (window.jQuery) {{
                        jQuery('select[name="country"]').val('{COUNTRY_CODE}').trigger('chosen:updated').trigger('change');
                    }}
                }} catch(e) {{}}
                return sel.value;
            }}"""
            selected = await page.evaluate(js_select)
            log(tag, f"🌏 国家选择结果: {selected}")

            if selected != COUNTRY_CODE:
                log(tag, "📌 尝试通过 Chosen UI 选择...")
                try:
                    chosen = page.locator('.chosen-container .chosen-single').first
                    await chosen.click()
                    await page.wait_for_timeout(500)
                    search_input = page.locator(
                        '.chosen-container .chosen-search input').first
                    await search_input.fill(COUNTRY_NAME)
                    await page.wait_for_timeout(500)
                    result = page.locator(
                        f'.chosen-results li:has-text("{COUNTRY_NAME}")').first
                    if await result.count() > 0:
                        await result.click()
                        log(tag, f"🌏 ✅ 通过 Chosen UI 选择了 {COUNTRY_NAME}")
                        await page.wait_for_timeout(500)
                except Exception as e:
                    log(tag, f"⚠️ Chosen UI 操作失败: {e}")
        except Exception as e:
            log(tag, f"⚠️ 国家选择失败: {e}")

        # 第三步：点击 Save
        try:
            save_btn = page.locator(
                '.modal[style*="display: block"] button.btn-primary:has-text("Save"), '
                '.modal.fade.in button.btn-primary:has-text("Save")')
            if await save_btn.count() > 0:
                await save_btn.first.click(force=True)
                log(tag, "💾 已点击 Save")
                await page.wait_for_timeout(3000)
            else:
                await page.evaluate("""() => {
                    const modals = document.querySelectorAll('.modal');
                    for (const m of modals) {
                        if (m.classList.contains('in') || m.style.display === 'block' || getComputedStyle(m).display !== 'none') {
                            const btn = m.querySelector('button.btn-primary');
                            if (btn && btn.textContent.trim() === 'Save') { btn.click(); return; }
                        }
                    }
                    const allSave = document.querySelectorAll('button.btn-primary');
                    for (const b of allSave) {
                        if (b.textContent.trim() === 'Save' && b.offsetParent !== null) { b.click(); return; }
                    }
                }""")
                log(tag, "💾 JS 兜底点击 Save")
                await page.wait_for_timeout(3000)
        except Exception as e:
            log(tag, f"⚠️ 点击 Save 失败: {e}")

        await page.wait_for_timeout(3000)

    if AUTO_CLICK_ADD_CARD:
        # 第四步：点击 "Add credit card"
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            add_card = page.locator(
                'a:has-text("Add credit card"), button:has-text("Add credit card")')
            for attempt in range(10):
                if await add_card.count() > 0 and await add_card.first.is_visible(
                        timeout=1000):
                    await add_card.first.click(force=True)
                    log(tag, "💳 ✅ 已点击 Add credit card")
                    await page.wait_for_timeout(2000)
                    return True
                await page.wait_for_timeout(1500)

            await page.evaluate("""() => {
                const links = document.querySelectorAll('a, button');
                for (const l of links) {
                    if ((l.textContent||'').trim().includes('Add credit card')) { l.click(); return; }
                }
            }""")
            log(tag, "💳 JS 兜底点击 Add credit card")
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            log(tag, f"⚠️ 点击 Add credit card 失败: {e}")
            return False

    return True


# ==================== 指纹 ====================
def make_fp_args(seed):
    rnd = random.Random(seed)
    plat, plat_ver = rnd.choice(FP_PLATFORMS)
    brand, brand_ver = rnd.choice(FP_BRANDS)
    tz = rnd.choice(FP_TIMEZONES)
    cpu = rnd.choice(FP_CPU_CORES)
    args = [
        f"--fingerprint={seed}", f"--fingerprint-platform={plat}",
        f"--fingerprint-brand={brand}",
        f"--fingerprint-hardware-concurrency={cpu}",
        f"--timezone={tz}", f"--lang={FP_LANG}", f"--accept-lang={FP_LANG},{FP_LANG.split('-')[0]}",
    ]
    if START_MAXIMIZED:
        args.append("--start-maximized")
    args.extend([
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars", "--test-type", "--no-default-browser-check",
        "--no-first-run",
        "--disable-features=Translate,OptimizationHints,MediaRouter",
        "--disable-session-crashed-bubble", "--disable-save-password-bubble",
    ])
    if plat_ver:
        args.append(f"--fingerprint-platform-version={plat_ver}")
    if brand_ver:
        args.append(f"--fingerprint-brand-version={brand_ver}")
    return args, {"seed": seed, "platform": plat, "brand": brand,
                  "timezone": tz, "cpu": cpu}


# ==================== 注册主流程 ====================
async def register_task(pw, idx):
    tag = f"#{idx:02d}"
    stop_guard = None
    guard_task = None
    try:
        addr = rnd_mail()
        if not apply_mail(addr):
            log(tag, "❌ 邮箱申请失败")
            return None
        log(tag, f"📧 邮箱 = {addr}")

        first_name, last_name = random_name()
        log(tag, f"👤 姓名 = {first_name} {last_name}")

        seed = random.randint(10_000_000, 2_000_000_000)
        profile_dir = PROFILE_ROOT / f"profile_{idx}_{seed}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        args, fp_info = make_fp_args(seed)
        log(tag, f"🎭 指纹 seed={seed} "
                 f"{fp_info['platform']}/{fp_info['brand']}/{fp_info['timezone']}")

        log(tag, "🌐 启动浏览器...")
        try:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), executable_path=CHROME_PATH,
                headless=HEADLESS, args=args, viewport=None, no_viewport=True,
                accept_downloads=True,
                ignore_default_args=["--enable-automation",
                                     "--disable-component-update",
                                     "--disable-default-apps"],
            )
        except Exception as e:
            log(tag, f"❌ 启动失败: {e}")
            log(tag, traceback.format_exc())
            return None

        log(tag, "✅ 浏览器已启动")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        try:
            await ctx.add_init_script(COOKIE_KILLER_SCRIPT)
        except:
            pass

        async def _cg(p):
            try:
                await p.wait_for_load_state("domcontentloaded", timeout=15000)
                await inject_cookie_killer(p, tag)
                for _ in range(3):
                    if await dismiss_cookie_banner(p, tag):
                        break
                    await p.wait_for_timeout(800)
            except:
                pass

        page.on("load", lambda p: asyncio.create_task(_cg(p)))
        ctx.on("page", lambda p: asyncio.create_task(_cg(p)))
        stop_guard = asyncio.Event()
        guard_task = asyncio.create_task(cookie_guard_loop(page, tag, stop_guard))

        try:
            await page.goto(JB_SIGNUP, wait_until="domcontentloaded",
                            timeout=TIMEOUT_PAGE_LOAD * 1000)
            await page.wait_for_timeout(2500)
            await inject_cookie_killer(page, tag)
            await dismiss_cookie_banner(page, tag)

            try:
                await page.get_by_role("button", name=re.compile(
                    r"Continue with email", re.I)).click(timeout=15000)
            except:
                await page.locator(
                    'button:has-text("Continue with email")').click()
            await page.wait_for_timeout(1000)

            email_input = page.locator('input[name="email"]')
            await email_input.wait_for(timeout=15000)
            await email_input.fill(addr)
            await page.wait_for_timeout(400)

            log(tag, "🖱️ 第一次 Continue（触发 reCAPTCHA 加载）")

            await email_input.focus()
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)

            try:
                email_still = page.locator('input[name="email"]')
                if await email_still.count() > 0 and await email_still.is_visible(timeout=500):
                    btn = page.locator('button[type="submit"]').first
                    if await btn.count() > 0:
                        await btn.scroll_into_view_if_needed(timeout=2000)
                        await btn.click(timeout=3000)
                        log(tag, "🖱️ 备用按钮点击")
            except:
                pass

            await page.wait_for_timeout(1500)

            try:
                await page.evaluate(
                    f'document.title = "#{idx:02d} 👉 人机验证"')
            except:
                pass

            await try_click_recaptcha(page, tag)

            log(tag, "👤 请手动完成 reCAPTCHA 图形挑战（如需帮助请右键图片）...")

            dialog_closed = await wait_dialog_closed(page, tag)

            if dialog_closed:
                log(tag, "✅ reCAPTCHA 已完成，对话框已关闭")
                await page.wait_for_timeout(1500)

                submitted = await click_continue_react(page, tag, max_attempts=30, interval=1.0)
                if not submitted:
                    log(tag, "⚠️ 自动提交失败，请手动点击 Continue")
                else:
                    log(tag, "✅ 表单已提交")
            else:
                log(tag, "⚠️ 等待超时，尝试继续")
                await click_continue_react(page, tag, max_attempts=10, interval=1.0)

            log(tag, "⏳ 等待 OTP 页面...")
            for wait_i in range(60):
                if await _check_left_email_page(page):
                    log(tag, "✅ 已进入下一步")
                    break
                if wait_i > 0 and wait_i % 10 == 0:
                    log(tag, f"⏳ 仍在等待... ({wait_i}s)")
                await page.wait_for_timeout(1000)

            await page.wait_for_timeout(2000)

            mail_res = await wait_email(addr, tag)
            if not mail_res:
                log(tag, "❌ 未收到邮件")
                return None
            kind, payload = mail_res

            if kind == "LINK":
                log(tag, "🔗 验证链接")
                await page.goto(payload, wait_until="domcontentloaded",
                                timeout=TIMEOUT_PAGE_LOAD * 1000)
            else:
                log(tag, f"🔑 OTP {payload}")
                try:
                    await page.wait_for_selector('input[name="otp-1"]',
                                                 timeout=10000)
                except:
                    log(tag, "⚠️ OTP 输入框未找到，尝试继续")
                await fill_otp_code(page, payload, tag)
                await page.wait_for_timeout(800)
                try:
                    await page.locator(
                        'button[type="submit"]').first.click(force=True)
                except:
                    pass

            await page.wait_for_timeout(3500)

            await fill_registration_form(page, first_name, last_name,
                                         UNIFIED_PASSWORD, tag)
            await page.wait_for_timeout(500)

            if ACCEPT_ALL_CHECKBOXES:
                try:
                    cbs = page.locator('input[type="checkbox"]')
                    for i in range(await cbs.count()):
                        cb = cbs.nth(i)
                        try:
                            if await cb.is_visible() and not await cb.is_checked():
                                await cb.check()
                        except:
                            pass
                except:
                    pass

            await submit_create_account(page, tag)
            await page.wait_for_timeout(5000)

            log(tag, f"➡️ 跳转到 {FINAL_URL}")
            try:
                await page.goto(FINAL_URL, wait_until="domcontentloaded",
                                timeout=30000)
            except:
                pass
            await page.wait_for_timeout(2000)

            await setup_tokens_page(page, tag)

            try:
                await page.evaluate(
                    f'document.title = "#{idx:02d} ✅ 完成 - 请员工填写信用卡信息"')
            except:
                pass

            log(tag, "🎉 注册完成，等待员工填写信用卡")

            if stop_guard:
                stop_guard.set()
            if guard_task:
                try:
                    await asyncio.wait_for(guard_task, timeout=2)
                except:
                    pass

            return {
                "idx": idx, "email": addr, "password": UNIFIED_PASSWORD,
                "first_name": first_name, "last_name": last_name,
                "fingerprint_seed": seed,
            }

        except Exception as e:
            log(tag, f"❌ 流程异常: {e}")
            log(tag, traceback.format_exc())
            if stop_guard:
                stop_guard.set()
            if guard_task:
                try:
                    guard_task.cancel()
                except:
                    pass
            return None

    except Exception as e:
        log(tag, f"❌ 任务异常: {e}")
        log(tag, traceback.format_exc())
        if stop_guard:
            stop_guard.set()
        if guard_task:
            try:
                guard_task.cancel()
            except:
                pass
        return None


# ==================== 主入口 ====================
async def main():
    print("=" * 66)
    print("  🚀 JetBrains 批量注册工具 v3.0 (settings.json 配置版)")
    print("=" * 66)

    # 显示配置文件状态
    if SETTINGS_FILE.exists():
        print(f"\n⚙️  配置文件: {SETTINGS_FILE}")
    else:
        print(f"\n⚙️  配置文件: {SETTINGS_FILE}（已自动生成默认配置）")

    # 检查浏览器
    if CHROME_PATH is None:
        print(f"\n❌ 未找到指纹浏览器 chrome.exe")
        chrome_cfg = CFG["browser"]["chrome_exe"]
        if chrome_cfg == "auto":
            print(f"   脚本目录: {SCRIPT_DIR}")
            print(f"\n   请将指纹浏览器放到以下任一位置:")
            print(f"   • {SCRIPT_DIR / 'chrome.exe'}")
            print(f"   • {SCRIPT_DIR / 'chrome' / 'chrome.exe'}")
            print(f"   • {SCRIPT_DIR / 'chrome-win' / 'chrome.exe'}")
        else:
            print(f"   配置路径: {chrome_cfg}")
        print(f"\n   或在 settings.json 中设置 browser.chrome_exe 为正确路径")
        return

    print(f"🌐 浏览器: {CHROME_PATH}")
    print(f"🔑 密码: {UNIFIED_PASSWORD}")
    print(f"🌏 国家: {COUNTRY_NAME} ({COUNTRY_CODE})")
    print(f"📧 邮箱: {NIMAIL_API} (@{EMAIL_DOMAIN})")

    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)

    raw = input(f"\n请输入要并发注册的数量 [默认 {DEFAULT_CONCURRENT}]: ").strip()
    n = int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_CONCURRENT

    print(f"\n📦 同时打开 {n} 个独立指纹浏览器")
    print(f"👤 姓名: 随机真人英文名")
    print(f"📁 数据: {PROFILE_ROOT}")
    print(f"📄 结果: {OUTPUT_FILE.absolute()}")
    print(f"\n流程：填邮箱 → 触发 reCAPTCHA → 自动点复选框 → 等人工过图形挑战")
    print(f"      → 检测 dialog 关闭 → 提交 → 自动填 OTP → 填姓名密码")
    print(f"      → Create account → 自动选{COUNTRY_NAME}", end="")
    if AUTO_CLICK_ADD_CARD:
        print(f" → 弹出 Add credit card 对话框")
    else:
        print()
    input("\n按回车开始... ")

    async with async_playwright() as pw:
        async def delayed(i):
            await asyncio.sleep(i * 1.5)
            return await register_task(pw, i + 1)

        tasks = [delayed(i) for i in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    ok = [r for r in results if isinstance(r, dict)]
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"\n# === Batch @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        for r in ok:
            f.write(
                f"{r['email']}\t{r['password']}\t{r['first_name']} {r['last_name']}\tfp={r['fingerprint_seed']}\n")

    print("\n" + "=" * 66)
    print(f"✨ 完成: 成功 {len(ok)} / {n}")
    for r in ok:
        print(
            f"   ✓ {r['email']}  |  {r['first_name']} {r['last_name']}  |  {r['password']}")
    print("=" * 66)
    if AUTO_CLICK_ADD_CARD:
        print("💡 浏览器保持打开，员工在 Add credit card 对话框中填写信用卡信息")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 中断")
