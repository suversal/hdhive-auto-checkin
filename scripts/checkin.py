#!/usr/bin/env python3

import json
import os
import re
import shlex
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playwright.sync_api import Browser, Page, Playwright, TimeoutError, sync_playwright


LOCAL_CONFIG_ENV = "HDHIVE_LOCAL_CONFIG_PATH"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_CONFIG_PATH = PROJECT_ROOT / "local.config.json"
ACCOUNTS_ENV = "HDHIVE_ACCOUNTS_JSON"


def load_local_config() -> tuple[Path, dict[str, Any]]:
    """Load an optional local JSON config file for IDE/local runs.

    The local file is intentionally checked before GitHub Actions env vars so
    local debugging can be done without exporting a long list of variables.
    """
    raw_path = os.getenv(LOCAL_CONFIG_ENV, str(DEFAULT_LOCAL_CONFIG_PATH))
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        return path, {}

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckinError(f"Invalid JSON in local config file {path}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise CheckinError(f"Local config file {path} must contain a JSON object")
    return path, parsed


def get_config_value(env_name: str, default: str = "", local_key: Optional[str] = None) -> str:
    """Read config from local file first, then environment variables, then default."""
    key = local_key or env_name.lower()
    local_value = LOCAL_CONFIG.get(key)
    if local_value is not None:
        return str(local_value).strip()
    return os.getenv(env_name, default).strip()


LOCAL_CONFIG_PATH, LOCAL_CONFIG = load_local_config()

BASE_URL = get_config_value("HDHIVE_BASE_URL", "https://hdhive.com", "base_url").rstrip("/")
LOGIN_URL = f"{BASE_URL}/login"
DEFAULT_SIGN_TYPE = get_config_value("HDHIVE_SIGN_TYPE", "daily", "sign_type").lower()
HEADLESS = get_config_value("HDHIVE_HEADLESS", "true", "headless").lower() != "false"
BROWSER_PATH = get_config_value("HDHIVE_BROWSER_PATH", "", "browser_path") or None
BROWSER_CHANNEL = get_config_value("HDHIVE_BROWSER_CHANNEL", "chrome", "browser_channel") or None
BROWSER_ARGS = shlex.split(get_config_value("HDHIVE_BROWSER_ARGS", "", "browser_args"))
TZ = get_config_value("HDHIVE_TIMEZONE", "Asia/Shanghai", "timezone") or "Asia/Shanghai"
ARTIFACTS_DIR = Path(get_config_value("HDHIVE_ARTIFACTS_DIR", "artifacts", "artifacts_dir"))
TELEGRAM_BOT_TOKEN = get_config_value("TELEGRAM_BOT_TOKEN", "", "telegram_bot_token")
TELEGRAM_CHAT_ID = get_config_value("TELEGRAM_CHAT_ID", "", "telegram_chat_id")

SIGN_TYPE_TO_LABEL = {
    "daily": "每日签到",
    "gamble": "赌狗签到",
}

FINGERPRINT_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
window.chrome = { runtime: {} };

if (navigator.userAgentData) {
  Object.defineProperty(navigator, 'userAgentData', {
    get: () => ({
      brands: [
        { brand: 'Google Chrome', version: '135' },
        { brand: 'Chromium', version: '135' },
        { brand: 'Not.A/Brand', version: '24' }
      ],
      mobile: false,
      platform: 'macOS',
      getHighEntropyValues: async (hints) => {
        const values = {
          architecture: 'x86',
          bitness: '64',
          formFactors: ['Desktop'],
          fullVersionList: [
            { brand: 'Google Chrome', version: '135.0.0.0' },
            { brand: 'Chromium', version: '135.0.0.0' },
            { brand: 'Not.A/Brand', version: '24.0.0.0' }
          ],
          model: '',
          platform: 'macOS',
          platformVersion: '10.15.7',
          uaFullVersion: '135.0.0.0',
          wow64: false
        };
        const out = {};
        for (const hint of hints || []) out[hint] = values[hint];
        return out;
      }
    })
  });
}

const makePluginArray = () => {
  const plugins = [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
  ];
  plugins.item = (index) => plugins[index] || null;
  plugins.namedItem = (name) => plugins.find((p) => p.name === name) || null;
  return plugins;
};
Object.defineProperty(navigator, 'plugins', { get: () => makePluginArray() });

const patchPermissions = () => {
  const originalQuery = navigator.permissions && navigator.permissions.query;
  if (!originalQuery) return;
  navigator.permissions.query = (parameters) => (
    parameters && parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
};
patchPermissions();

const patchWebGL = (prototype) => {
  if (!prototype || prototype.__hdhive_patched__) return;
  const originalGetParameter = prototype.getParameter;
  const originalGetExtension = prototype.getExtension;
  const debugInfo = {
    UNMASKED_VENDOR_WEBGL: 37445,
    UNMASKED_RENDERER_WEBGL: 37446
  };

  prototype.getExtension = function(name) {
    if (name === 'WEBGL_debug_renderer_info') {
      return debugInfo;
    }
    return originalGetExtension.apply(this, arguments);
  };

  prototype.getParameter = function(parameter) {
    if (parameter === debugInfo.UNMASKED_VENDOR_WEBGL) {
      return 'Intel Inc.';
    }
    if (parameter === debugInfo.UNMASKED_RENDERER_WEBGL) {
      return 'Intel(R) Iris OpenGL Engine';
    }
    return originalGetParameter.apply(this, arguments);
  };

  Object.defineProperty(prototype, '__hdhive_patched__', { value: true });
};

patchWebGL(window.WebGLRenderingContext && window.WebGLRenderingContext.prototype);
patchWebGL(window.WebGL2RenderingContext && window.WebGL2RenderingContext.prototype);
"""

DIAGNOSTICS_EVAL_SCRIPT = """() => {
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
  let webglVendor = null;
  let webglRenderer = null;
  if (gl) {
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    if (debugInfo) {
      webglVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
      webglRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
    }
  }
  return {
    location: window.location.href,
    title: document.title,
    navigator: {
      userAgent: navigator.userAgent,
      platform: navigator.platform,
      language: navigator.language,
      languages: navigator.languages,
      vendor: navigator.vendor,
      webdriver: navigator.webdriver,
      hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemory: navigator.deviceMemory || null,
      pluginsLength: navigator.plugins.length
    },
    window: {
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      outerWidth: window.outerWidth,
      outerHeight: window.outerHeight,
      devicePixelRatio: window.devicePixelRatio
    },
    screen: {
      width: window.screen.width,
      height: window.screen.height,
      availWidth: window.screen.availWidth,
      availHeight: window.screen.availHeight,
      colorDepth: window.screen.colorDepth
    },
    webgl: {
      vendor: webglVendor,
      renderer: webglRenderer
    }
  };
}"""


@dataclass
class AccountConfig:
    username: str
    password: str
    sign_type: str = DEFAULT_SIGN_TYPE
    name: Optional[str] = None
    telegram_chat_id: Optional[str] = None


@dataclass
class CheckinResult:
    username: str
    display_name: str
    sign_type: str
    sign_label: str
    status: str
    message: str
    description: str
    response_status: Optional[int] = None
    next_action: Optional[str] = None
    raw_response: Optional[str] = None
    screenshot_path: Optional[str] = None


class CheckinError(Exception):
    pass


def log(message: str) -> None:
    print(message, flush=True)


def normalize_sign_type(value: str) -> str:
    """Normalize user-facing sign type aliases into the two internal modes."""
    sign_type = (value or DEFAULT_SIGN_TYPE).strip().lower()
    aliases = {
        "day": "daily",
        "daily": "daily",
        "每日": "daily",
        "每日签到": "daily",
        "gamble": "gamble",
        "dog": "gamble",
        "bet": "gamble",
        "赌狗": "gamble",
        "赌狗签到": "gamble",
    }
    normalized = aliases.get(sign_type)
    if not normalized:
        raise CheckinError(f"Unsupported sign type: {value}")
    return normalized


def load_accounts() -> list[AccountConfig]:
    """Load accounts from local config first, then GitHub Actions environment."""
    if "accounts" in LOCAL_CONFIG:
        parsed = LOCAL_CONFIG["accounts"]
    else:
        raw = os.getenv(ACCOUNTS_ENV, "").strip()
        if not raw:
            raise CheckinError(
                f"Missing account config. Use {LOCAL_CONFIG_PATH} locally or set {ACCOUNTS_ENV} in CI."
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckinError(f"Invalid JSON in {ACCOUNTS_ENV}: {exc}") from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        raise CheckinError(f"{ACCOUNTS_ENV} must be a JSON array or object")

    accounts: list[AccountConfig] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise CheckinError(f"Each account in {ACCOUNTS_ENV} must be a JSON object")
        username = str(item.get("username", "")).strip()
        password = str(item.get("password", "")).strip()
        if not username or not password:
            raise CheckinError("Each account requires non-empty username and password")
        sign_type = normalize_sign_type(str(item.get("sign_type", DEFAULT_SIGN_TYPE)))
        name = str(item.get("name", "")).strip() or None
        telegram_chat_id = str(item.get("telegram_chat_id", "")).strip() or None
        accounts.append(
            AccountConfig(
                username=username,
                password=password,
                sign_type=sign_type,
                name=name,
                telegram_chat_id=telegram_chat_id,
            )
        )
    return accounts


def build_context(browser: Browser):
    """Create the browser context using the headless settings that previously
    worked in local testing.

    This intentionally mirrors the earlier successful local experiment before
    we started changing CI-specific fingerprint details.
    """
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id=TZ,
        viewport={"width": 1440, "height": 900},
    )
    # Keep the spoofing bundle centralized so local and CI runs share the same
    # browser fingerprint assumptions.
    context.add_init_script(FINGERPRINT_INIT_SCRIPT)
    return context


def launch_browser(playwright: Playwright) -> Browser:
    """Launch the browser using either an explicit path or a named channel.

    GitHub Actions uses a provided Chrome binary path, while local runs can
    usually rely on the default channel without extra configuration.
    """
    launch_kwargs: dict[str, Any] = {"headless": HEADLESS}
    if BROWSER_PATH:
        launch_kwargs["executable_path"] = BROWSER_PATH
    elif BROWSER_CHANNEL:
        launch_kwargs["channel"] = BROWSER_CHANNEL
    if BROWSER_ARGS:
        launch_kwargs["args"] = BROWSER_ARGS
    log(
        "Launching browser with "
        f"headless={HEADLESS}, browser_path={BROWSER_PATH or '-'}, "
        f"channel={BROWSER_CHANNEL or '-'}, args={' '.join(BROWSER_ARGS) or '-'}"
    )
    return playwright.chromium.launch(**launch_kwargs)


def wait_for_login_form(page: Page) -> None:
    """Open the login page and make sure the actual form is present.

    This is the earliest place where we can detect 'site error page' failures
    caused by browser fingerprinting or blocked environments.
    """
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(6_000)
    try:
        page.locator("input").nth(1).wait_for(timeout=15_000)
    except TimeoutError as exc:
        body_text = compact(page.locator("body").inner_text())
        raise CheckinError(f"Login form did not appear: {body_text}") from exc


def compact(text: str) -> str:
    return " ".join(text.split())


def safe_file_stem(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)


def write_browser_diagnostics(page: Page, username: str, stage: str) -> Optional[str]:
    """Persist a lightweight browser fingerprint snapshot for CI debugging."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / f"{safe_file_stem(username)}-{stage}-diagnostics.json"
    try:
        data = page.evaluate(DIAGNOSTICS_EVAL_SCRIPT)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception:
        return None


def dismiss_notice(page: Page) -> None:
    """Close the blocking announcement dialog when it appears.

    The dialog button is disabled for a short countdown, so we poll until the
    button becomes clickable instead of clicking once and failing.
    """
    button = page.get_by_role("button", name=re.compile(r"我知道了"))
    if button.count() == 0:
        return
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            if button.first.is_enabled():
                button.first.click(force=True, timeout=2_000)
                page.wait_for_timeout(800)
                return
        except Exception:
            pass
        page.wait_for_timeout(500)


def login(page: Page, account: AccountConfig) -> None:
    """Complete the interactive login flow and wait for the user menu."""
    wait_for_login_form(page)
    page.locator("input").nth(0).fill(account.username)
    page.locator("input").nth(1).fill(account.password)
    page.get_by_role("button", name="登录").click()
    try:
        page.locator('button[aria-label="用户菜单"]').wait_for(timeout=20_000)
    except TimeoutError as exc:
        body_text = compact(page.locator("body").inner_text())
        raise CheckinError(f"Login failed or user menu not found: {body_text}") from exc
    page.wait_for_timeout(2_000)
    dismiss_notice(page)


def menu_sign_item(page: Page, sign_label: str):
    """Open the user menu and return the desired sign-in menu entry."""
    page.locator('button[aria-label="用户菜单"]').click(force=True)
    page.wait_for_timeout(1_500)
    return page.get_by_text(sign_label, exact=False).first


def decode_response_text(response) -> str:
    """Decode the Next.js server action response body.

    The site sometimes returns mojibake-like text, so we attempt a second pass
    repair when the first UTF-8 decode clearly looks broken.
    """
    try:
        raw = response.body()
    except Exception:
        return ""

    text = raw.decode("utf-8", errors="replace")
    if "签到" not in text and any(ch in text for ch in ("ç", "ä", "å", "ï", "é")):
        try:
            repaired = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if repaired:
                text = repaired
        except Exception:
            pass
    return text


def extract_field(text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}":"([^"]*)"', text)
    if not match:
        return ""
    return match.group(1)


def repair_partial_text(value: str) -> str:
    """Repair a few recurring truncated strings returned by the site."""
    if not value:
        return value
    fixed = value
    if fixed == "签失败":
        fixed = "签到失败"
    if fixed == "签成功":
        fixed = "签到成功"
    if "已经签" in fixed and "天来吧" in fixed:
        fixed = "你已经签到过了，明天再来吧"
    return fixed


def parse_action_result(text: str) -> tuple[str, str, str]:
    normalized = compact(text)
    message = repair_partial_text(extract_field(normalized, "message"))
    description = repair_partial_text(extract_field(normalized, "description"))

    if '"success":true' in normalized and '"error"' not in normalized:
        return "success", message or "签到成功", description
    if (
        "已经签到过了" in normalized
        or "明天再来吧" in normalized
        or "已经签到过了" in description
        or "明天再来吧" in description
        or "再来吧" in description
    ):
        return "already_signed", "今日已签到", description or "你已经签到过了，明天再来吧"
    if '"success":false' in normalized or '"error"' in normalized:
        return "failed", message or "签到失败", description or "站点返回失败"
    return "unknown", message or "未知结果", description or normalized[:200]


def status_emoji(status: str) -> str:
    return {
        "success": "✅",
        "already_signed": "🟡",
        "failed": "❌",
        "unknown": "⚠️",
    }.get(status, "⚠️")


def status_label(status: str) -> str:
    return {
        "success": "签到成功",
        "already_signed": "今日已签到",
        "failed": "执行失败",
        "unknown": "结果未知",
    }.get(status, "结果未知")


def take_screenshot(page: Page, username: str) -> Optional[str]:
    """Capture the current page for later debugging."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = safe_file_stem(username)
    path = ARTIFACTS_DIR / f"{safe_name}-{int(time.time())}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def perform_checkin(page: Page, account: AccountConfig) -> CheckinResult:
    """Click the configured sign-in menu item and parse the server action result."""
    sign_label = SIGN_TYPE_TO_LABEL[account.sign_type]
    item = menu_sign_item(page, sign_label)
    try:
        item.wait_for(timeout=8_000)
    except TimeoutError as exc:
        raise CheckinError(f"Could not find sign-in menu item: {sign_label}") from exc

    with page.expect_response(
        lambda res: res.request.method == "POST"
        and res.url.rstrip("/") == BASE_URL.rstrip("/")
        and bool(res.request.headers.get("next-action")),
        timeout=15_000,
    ) as response_info:
        item.click(force=True)

    response = response_info.value
    page.wait_for_timeout(2_500)

    raw_response = decode_response_text(response)
    status, message, description = parse_action_result(raw_response)
    screenshot_path = None
    if status in {"failed", "unknown"}:
        screenshot_path = take_screenshot(page, account.username)

    return CheckinResult(
        username=account.username,
        display_name=account.name or account.username,
        sign_type=account.sign_type,
        sign_label=sign_label,
        status=status,
        message=message,
        description=description,
        response_status=response.status,
        next_action=response.request.headers.get("next-action"),
        raw_response=raw_response[:1_000],
        screenshot_path=screenshot_path,
    )


def format_result_line(result: CheckinResult) -> str:
    detail = result.message or status_label(result.status)
    if result.description:
        detail = f"{detail} - {result.description}"
    return f"[{result.status}] {result.display_name} ({result.sign_label}) {detail}"


def send_telegram_message(chat_id: str, message: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status >= 400:
            raise CheckinError(f"Telegram API returned status {response.status}")


def build_chat_map(accounts: list[AccountConfig]) -> dict[str, Optional[str]]:
    """Resolve the effective Telegram target for each account."""
    chat_map: dict[str, Optional[str]] = {}
    for account in accounts:
        chat_map[account.username] = account.telegram_chat_id or TELEGRAM_CHAT_ID or None
    return chat_map


def build_telegram_message(chat_results: list[CheckinResult]) -> str:
    """Build a compact but readable Telegram summary message."""
    counts = {
        "success": sum(result.status == "success" for result in chat_results),
        "already_signed": sum(result.status == "already_signed" for result in chat_results),
        "failed": sum(result.status == "failed" for result in chat_results),
        "unknown": sum(result.status == "unknown" for result in chat_results),
    }
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "<b>HDHive 自动签到结果</b>",
        f"🕒 <b>时间</b>：<code>{escape_html(timestamp)}</code>",
        f"🌐 <b>站点</b>：<code>{escape_html(BASE_URL)}</code>",
        (
            "📊 <b>汇总</b>："
            f"成功 {counts['success']} / "
            f"已签 {counts['already_signed']} / "
            f"失败 {counts['failed']} / "
            f"未知 {counts['unknown']}"
        ),
        "",
    ]

    for index, result in enumerate(chat_results, start=1):
        lines.append(f"{index}. {status_emoji(result.status)} <b>{escape_html(result.display_name)}</b>")
        lines.append(f"类型：<code>{escape_html(result.sign_label)}</code>")
        lines.append(f"状态：<b>{escape_html(status_label(result.status))}</b>")
        lines.append(f"结果：{escape_html(result.message or status_label(result.status))}")
        if result.description:
            lines.append(f"说明：{escape_html(result.description)}")
        if result.screenshot_path:
            lines.append(f"截图：<code>{escape_html(result.screenshot_path)}</code>")
        lines.append("")

    return "\n".join(lines).strip()


def notify(results: list[CheckinResult], accounts: list[AccountConfig]) -> None:
    """Send grouped Telegram notifications after all accounts finish."""
    if not TELEGRAM_BOT_TOKEN:
        log("Telegram disabled: TELEGRAM_BOT_TOKEN is not set")
        return

    grouped: dict[str, list[CheckinResult]] = {}
    chat_map = build_chat_map(accounts)
    for result in results:
        chat_id = chat_map.get(result.username) or TELEGRAM_CHAT_ID or None
        if not chat_id:
            continue
        grouped.setdefault(chat_id, []).append(result)

    for chat_id, chat_results in grouped.items():
        message = build_telegram_message(chat_results)
        send_telegram_message(chat_id, message)
        log(f"Telegram notification sent to chat_id={chat_id}")


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def write_results(results: list[CheckinResult]) -> Path:
    """Write the latest machine-readable run result to artifacts/latest-results.json."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / "latest-results.json"
    payload = {
        "base_url": BASE_URL,
        "timestamp": int(time.time()),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_github_summary(results: list[CheckinResult]) -> None:
    """Write a short markdown summary for the GitHub Actions run page."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [
        "## HDHive Check-in Results",
        "",
        f"- Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- Site: `{BASE_URL}`",
        "",
        "| Account | Sign Type | Status | Message |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| {result.display_name} | {result.sign_label} | {status_label(result.status)} | "
            f"{result.message} {result.description}".strip()
            + " |"
        )
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Entry point used by both local IDE runs and GitHub Actions."""
    try:
        accounts = load_accounts()
    except CheckinError as exc:
        log(f"Configuration error: {exc}")
        return 2

    results: list[CheckinResult] = []

    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                for account in accounts:
                    log(f"Processing {account.username} with sign_type={account.sign_type}")
                    context = build_context(browser)
                    page = context.new_page()
                    try:
                        login(page, account)
                        result = perform_checkin(page, account)
                    except Exception as exc:
                        screenshot_path = take_screenshot(page, account.username)
                        write_browser_diagnostics(page, account.username, "failure")
                        result = CheckinResult(
                            username=account.username,
                            display_name=account.name or account.username,
                            sign_type=account.sign_type,
                            sign_label=SIGN_TYPE_TO_LABEL[account.sign_type],
                            status="failed",
                            message="执行失败",
                            description=str(exc),
                            screenshot_path=screenshot_path,
                        )
                    finally:
                        context.close()

                    results.append(result)
                    log(format_result_line(result))
            finally:
                browser.close()
    except Exception as exc:
        log(f"Fatal error: {exc}")
        return 1

    try:
        notify(results, accounts)
    except (CheckinError, HTTPError, URLError) as exc:
        log(f"Telegram notification failed: {exc}")

    results_path = write_results(results)
    write_github_summary(results)
    log(f"Results written to {results_path}")

    has_failures = any(result.status in {"failed", "unknown"} for result in results)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
