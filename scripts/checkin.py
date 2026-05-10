#!/usr/bin/env python3

import json
import os
import re
import shlex
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, Iterator, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playwright.sync_api import Browser, Page, Playwright, TimeoutError, sync_playwright

# --- 全局常量与路径配置 ---
LOCAL_CONFIG_ENV = "HDHIVE_LOCAL_CONFIG_PATH"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_CONFIG_PATH = PROJECT_ROOT / "local.config.json"
ACCOUNTS_ENV = "HDHIVE_ACCOUNTS_JSON"

class CheckinError(Exception):
    """自定义异常类"""
    pass

def log(message: str) -> None:
    """标准日志打印函数"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)

@dataclass
class AccountConfig:
    """账号配置信息类"""
    username: str
    password: str
    sign_type: str = "daily"
    telegram_chat_id: Optional[str] = None

def load_local_config() -> tuple[Path, dict[str, Any]]:
    """
    加载本地 JSON 配置文件（local.config.json）。
    优先级说明：本地配置文件优于环境变量，方便本地调试。
    """
    raw_path = os.getenv(LOCAL_CONFIG_ENV, str(DEFAULT_LOCAL_CONFIG_PATH))
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    
    if not path.exists():
        return path, {}

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        log(f"成功加载本地配置: {path}")
    except json.JSONDecodeError as exc:
        raise CheckinError(f"本地配置文件 JSON 格式错误 {path}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise CheckinError(f"本地配置文件 {path} 必须是 JSON 对象格式")
    return path, parsed

def get_config_value(env_name: str, default: str = "", local_key: Optional[str] = None) -> str:
    """
    配置读取助手：
    1. 优先读取 local.config.json
    2. 其次读取环境变量
    3. 最后返回默认值
    """
    key = local_key or env_name.lower()
    local_value = LOCAL_CONFIG.get(key)
    if local_value is not None:
        return str(local_value).strip()
    return os.getenv(env_name, default).strip()

# 初始化配置
LOCAL_CONFIG_PATH, LOCAL_CONFIG = load_local_config()

# 读取各项运行参数
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
RESPONSE_BODY_TIMEOUT_SECONDS = float(
    get_config_value("HDHIVE_RESPONSE_BODY_TIMEOUT_SECONDS", "15", "response_body_timeout_seconds")
)
MAX_CHECKIN_ATTEMPTS = max(1, int(get_config_value("HDHIVE_MAX_ATTEMPTS", "5", "max_attempts")))
RETRY_BASE_DELAY_SECONDS = float(
    get_config_value("HDHIVE_RETRY_BASE_DELAY_SECONDS", "5", "retry_base_delay_seconds")
)

SIGN_TYPE_TO_LABEL = {
    "daily": "每日签到",
    "gamble": "赌狗签到",
}

# --- 浏览器指纹伪装脚本 ---
# 用于绕过站点的自动化检测（反爬虫/反指纹）
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

// 模拟 UserAgentData
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

// 模拟插件列表
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

// 修复权限查询
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

// 伪装 WebGL 渲染器信息
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

# 浏览器诊断脚本：提取当前页面的指纹信息，用于排错
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
class CheckinResult:
    """签到结果信息类"""
    username: str
    sign_type: str
    sign_label: str
    status: str
    response_success: Optional[bool]
    message: str
    description: str
    result_source: str = ""
    response_status: Optional[int] = None
    next_action: Optional[str] = None
    raw_response: Optional[str] = None
    screenshot_path: Optional[str] = None
    attempt: int = 1
    elapsed_seconds: Optional[float] = None


@dataclass
class ResponseBodyReadResult:
    """Detailed response-body read outcome for retry diagnostics."""
    decoded_text: str
    raw_text_preview: str
    raw_bytes_len: int
    read_status: str
    exception_type: str = ""
    exception_message: str = ""
    header_content_type: str = ""
    header_content_length: str = ""
    header_transfer_encoding: str = ""


class ResponseBodyTimeout(Exception):
    """Raised when Playwright waits too long for a response body to finish."""


@contextmanager
def response_body_deadline(timeout_seconds: float) -> Iterator[None]:
    """Bound response.body(), which can otherwise wait forever on a stalled stream."""
    if timeout_seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def handle_timeout(_signum: int, _frame: Optional[FrameType]) -> None:
        raise ResponseBodyTimeout(f"读取响应 body 超过 {timeout_seconds:g} 秒")

    signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def normalize_sign_type(value: str) -> str:
    """将用户输入的签到类型归一化为 internal 模式（daily/gamble）"""
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
        raise CheckinError(f"不支持的签到类型: {value}")
    return normalized


def load_accounts() -> list[AccountConfig]:
    """
    加载账号列表：
    优先从 LOCAL_CONFIG 加载，否则读取环境变量 HDHIVE_ACCOUNTS_JSON。
    """
    if "accounts" in LOCAL_CONFIG:
        parsed = LOCAL_CONFIG["accounts"]
    else:
        raw = os.getenv(ACCOUNTS_ENV, "").strip()
        if not raw:
            raise CheckinError(
                f"未配置账号信息。请在 {LOCAL_CONFIG_PATH} 或环境变量 {ACCOUNTS_ENV} 中进行配置。"
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckinError(f"环境变量 {ACCOUNTS_ENV} JSON 格式错误: {exc}") from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        raise CheckinError(f"{ACCOUNTS_ENV} 必须是 JSON 数组或对象")

    accounts: list[AccountConfig] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise CheckinError(f"每个账号配置必须是 JSON 对象")
        username = str(item.get("username", "")).strip()
        password = str(item.get("password", "")).strip()
        if not username or not password:
            raise CheckinError("账号和密码不能为空")
        sign_type = normalize_sign_type(str(item.get("sign_type", DEFAULT_SIGN_TYPE)))
        telegram_chat_id = str(item.get("telegram_chat_id", "")).strip() or None
        accounts.append(
            AccountConfig(
                username=username,
                password=password,
                sign_type=sign_type,
                telegram_chat_id=telegram_chat_id,
            )
        )
    log(f"成功加载 {len(accounts)} 个账号")
    return accounts


def build_context(browser: Browser):
    """创建浏览器上下文，注入指纹伪装脚本"""
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id=TZ,
        viewport={"width": 1440, "height": 900},
    )
    # 注入防侦测脚本
    context.add_init_script(FINGERPRINT_INIT_SCRIPT)
    return context


def launch_browser(playwright: Playwright) -> Browser:
    """启动浏览器实例"""
    launch_kwargs: dict[str, Any] = {"headless": HEADLESS}
    if BROWSER_PATH:
        launch_kwargs["executable_path"] = BROWSER_PATH
    elif BROWSER_CHANNEL:
        launch_kwargs["channel"] = BROWSER_CHANNEL
    if BROWSER_ARGS:
        launch_kwargs["args"] = BROWSER_ARGS
    
    log(f"正在启动浏览器... Headless: {HEADLESS}, 渠道: {BROWSER_CHANNEL or '默认'}")
    if BROWSER_PATH:
        log(f"自定义执行路径: {BROWSER_PATH}")
        
    return playwright.chromium.launch(**launch_kwargs)


def wait_for_login_form(page: Page) -> None:
    """访问登录页面并等待表单渲染"""
    log(f"正在访问登录页面: {LOGIN_URL}")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    
    # 预留一定时间等待前端渲染
    page.wait_for_timeout(6_000)
    
    try:
        # 等待密码输入框出现
        page.locator("input").nth(1).wait_for(timeout=15_000)
    except TimeoutError as exc:
        body_text = compact(page.locator("body").inner_text())
        log(f"登录页面加载超时，页面内容摘要: {body_text[:200]}...")
        raise CheckinError(f"未能在页面上找到登录表单，可能被防火墙拦截。") from exc


def compact(text: str) -> str:
    """去除文本中的多余空白"""
    return " ".join(text.split())


def safe_file_stem(value: str) -> str:
    """将字符串转换为安全的文件名"""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)


def write_browser_diagnostics(page: Page, username: str, stage: str) -> Optional[str]:
    """保存浏览器诊断信息 JSON 文件"""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / f"{safe_file_stem(username)}-{stage}-diagnostics.json"
    try:
        data = page.evaluate(DIAGNOSTICS_EVAL_SCRIPT)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception as e:
        log(f"无法保存诊断信息: {e}")
        return None


def dismiss_notice(page: Page) -> None:
    """尝试关闭首页的公告/通知弹窗"""
    button = page.get_by_role("button", name=re.compile(r"我知道了"))
    if button.count() == 0:
        return
    
    log("发现公告弹窗，正在尝试关闭...")
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            if button.first.is_enabled():
                button.first.click(force=True, timeout=2_000)
                log("成功关闭公告")
                page.wait_for_timeout(800)
                return
        except Exception:
            pass
        page.wait_for_timeout(500)


def login(page: Page, account: AccountConfig) -> None:
    """执行登录流程"""
    wait_for_login_form(page)
    
    log(f"正在输入账号: {account.username}")
    page.locator("input").nth(0).fill(account.username)
    page.locator("input").nth(1).fill(account.password)
    
    log("点击登录按钮...")
    page.get_by_role("button", name="登录").click()
    
    try:
        # 登录成功的标志是出现用户菜单
        page.locator('button[aria-label="用户菜单"]').wait_for(timeout=40_000)
        log("登录成功！")
    except TimeoutError as exc:
        body_text = compact(page.locator("body").inner_text())
        log(f"登录失败，页面内容: {body_text[:200]}...")
        raise CheckinError(f"登录超时或失败，未进入主界面。") from exc
    
    page.wait_for_timeout(2_000)
    dismiss_notice(page)


def menu_sign_item(page: Page, sign_label: str):
    """在用户菜单中寻找对应的签到项"""
    log("打开用户菜单...")
    page.locator('button[aria-label="用户菜单"]').click(force=True)
    page.wait_for_timeout(1_500)
    return page.get_by_text(sign_label, exact=False).first


def open_user_menu(page: Page, *, timeout_ms: int = 5_000, quiet: bool = False) -> bool:
    """Open the user menu and wait until menu content becomes visible."""
    if not quiet:
        log("打开用户菜单...")
    try:
        page.locator('button[aria-label="用户菜单"]').click(force=True, timeout=timeout_ms)
        page.get_by_text("个人中心", exact=False).first.wait_for(timeout=timeout_ms)
        return True
    except Exception:
        return False


def click_first_visible(locator, *, timeout_ms: int = 2_000) -> bool:
    """Click the first visible match from a locator collection."""
    try:
        count = locator.count()
    except Exception:
        return False

    for index in range(count):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible():
                candidate.click(force=True, timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def extract_today_checkin_remark(body_text: str, target_date: Optional[str] = None) -> Optional[str]:
    """Parse the points-record page text and return today's check-in remark when present."""
    date_prefix = target_date or datetime.now().strftime("%Y-%m-%d")
    lines = [compact(line) for line in body_text.splitlines() if compact(line)]

    for index, line in enumerate(lines):
        if not line.startswith(date_prefix):
            continue
        window = lines[max(0, index - 4): index + 1]
        if "签到" not in window:
            continue
        for candidate in reversed(window[:-1]):
            if "签到成功" in candidate:
                return candidate
        if "签到" in window:
            return "签到成功"
    return None


def confirm_checkin_from_points_records(page: Page, attempt: int) -> Optional[str]:
    """When the Server Action result is unknown, confirm success via today's points records."""
    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 未拿到明确响应，开始前往积分记录页核验...")

    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 重新打开用户菜单，准备进入个人中心...")
    if not open_user_menu(page, quiet=True):
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 未能重新打开用户菜单，无法核验积分记录。")
        return None

    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 进入个人中心...")
    if not click_first_visible(page.get_by_text("个人中心", exact=False), timeout_ms=5_000):
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 未找到个人中心入口，无法核验积分记录。")
        return None
    page.wait_for_timeout(2_000)

    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 打开积分记录页...")
    if not click_first_visible(page.get_by_text("积分记录", exact=False), timeout_ms=5_000):
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 未找到积分记录入口，无法核验签到结果。")
        return None
    page.wait_for_timeout(2_000)

    try:
        page.get_by_text("积分记录", exact=False).first.wait_for(timeout=10_000)
    except TimeoutError:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 积分记录页面加载超时。")
        return None

    body_text = page.locator("body").inner_text(timeout=5_000)
    remark = extract_today_checkin_remark(body_text)
    if remark:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 积分记录确认签到成功: {remark}")
    else:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 积分记录未发现今天的签到记录。")
    return remark


def repair_mojibake_text(value: str) -> str:
    """
    修复常见的 UTF-8 / Latin-1 串码。
    站点的 Server Action 响应里，JSON 字符串字段偶尔会以乱码形式出现，
    例如 “ç­¾å°å¤±è´¥”，这里统一尝试修复一次。
    """
    if not isinstance(value, str) or not value:
        return value

    suspicious_chars = ("ç", "ä", "å", "ï", "é", "â", "Ã", "Â")
    if not any(ch in value for ch in suspicious_chars):
        return value

    raw_bytes = bytearray()
    try:
        for char in value:
            codepoint = ord(char)
            if codepoint <= 0xFF:
                raw_bytes.append(codepoint)
            else:
                raw_bytes.extend(char.encode("cp1252"))
        return raw_bytes.decode("utf-8")
    except Exception:
        return value


def normalize_response_payload(value: Any) -> Any:
    """递归修复响应 JSON 中的乱码字符串。"""
    if isinstance(value, dict):
        return {key: normalize_response_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_response_payload(item) for item in value]
    if isinstance(value, str):
        return repair_mojibake_text(value)
    return value


def read_response_body_result(
    response, timeout_seconds: float = RESPONSE_BODY_TIMEOUT_SECONDS
) -> ResponseBodyReadResult:
    """Read and decode a response body while preserving diagnostics for empty bodies."""
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type", ""))
    content_length = str(headers.get("content-length", ""))
    transfer_encoding = str(headers.get("transfer-encoding", ""))

    try:
        with response_body_deadline(timeout_seconds):
            raw = response.body()
    except ResponseBodyTimeout as exc:
        log(str(exc))
        return ResponseBodyReadResult(
            decoded_text="",
            raw_text_preview="",
            raw_bytes_len=0,
            read_status="timeout",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            header_content_type=content_type,
            header_content_length=content_length,
            header_transfer_encoding=transfer_encoding,
        )
    except Exception as exc:
        log(f"读取响应 body 异常: {type(exc).__name__}: {exc}")
        return ResponseBodyReadResult(
            decoded_text="",
            raw_text_preview="",
            raw_bytes_len=0,
            read_status="exception",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            header_content_type=content_type,
            header_content_length=content_length,
            header_transfer_encoding=transfer_encoding,
        )

    raw_text = raw.decode("utf-8", errors="replace")
    chunks: list[Any] = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^\d+:(.*)$", line)
        payload_text = match.group(1) if match else line
        payload_text = payload_text.strip()
        if not payload_text:
            continue

        try:
            parsed = json.loads(payload_text)
            chunks.append(normalize_response_payload(parsed))
        except json.JSONDecodeError:
            chunks.append(repair_mojibake_text(payload_text))

    decoded_text = json.dumps(chunks, ensure_ascii=False) if chunks else repair_mojibake_text(raw_text)
    return ResponseBodyReadResult(
        decoded_text=decoded_text,
        raw_text_preview=raw_text[:300],
        raw_bytes_len=len(raw),
        read_status="ok",
        header_content_type=content_type,
        header_content_length=content_length,
        header_transfer_encoding=transfer_encoding,
    )


def decode_response_text(response, timeout_seconds: float = RESPONSE_BODY_TIMEOUT_SECONDS) -> str:
    """
    解析 Next.js Server Action 的分片响应。
    原始格式通常是：
      0:{...}\n
      1:{...}\n
    这里会把每个分片解析成 JSON 对象，并修复对象中的乱码字段，
    最终返回一个标准 JSON 数组字符串，便于后续统一解析。
    """
    return read_response_body_result(response, timeout_seconds=timeout_seconds).decoded_text


def is_checkin_action_response(response) -> bool:
    """判断响应是否为签到相关的 Server Action 响应。"""
    return (
        response.request.method == "POST"
        and response.url.rstrip("/") == BASE_URL.rstrip("/")
        and bool(response.request.headers.get("next-action"))
    )


def select_action_response(
    responses: list[Any],
) -> tuple[Any, ResponseBodyReadResult, Optional[bool], str, str]:
    """从捕获到的 Server Action 响应中选择包含业务结果的响应。"""
    fallback: tuple[Any, ResponseBodyReadResult, Optional[bool], str, str] | None = None

    for response in responses:
        body_result = read_response_body_result(response)
        response_success, message, description = extract_action_fields(body_result.decoded_text)
        current = (response, body_result, response_success, message, description)

        if fallback is None:
            fallback = current
        if body_result.decoded_text and (response_success is not None or message or description):
            return current

    if fallback is not None:
        return fallback
    raise CheckinError("未捕获到签到接口响应")


def extract_action_fields(text: str) -> tuple[Optional[bool], str, str]:
    """从 Server Action 返回 JSON 中提取 success / message / description。"""
    normalized = compact(text)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None, "", normalized[:200]

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return None, "", normalized[:200]

    message = ""
    description = ""
    success: Optional[bool] = None

    for chunk in payload:
        if not isinstance(chunk, dict):
            continue
        if isinstance(chunk.get("response"), dict):
            current = chunk["response"]
        elif isinstance(chunk.get("error"), dict):
            current = chunk["error"]
        else:
            current = chunk
        if not isinstance(current, dict):
            continue

        if "success" in current and isinstance(current["success"], bool):
            success = current["success"]
        if not message and isinstance(current.get("message"), str):
            message = current["message"]
        if not description and isinstance(current.get("description"), str):
            description = current["description"]

    return success, message, description


def status_emoji(status: str) -> str:
    """状态对应的表情符号"""
    return {
        "success": "✅",
        "failed": "❌",
        "unknown": "⚠️",
    }.get(status, "⚠️")


def status_label(status: str) -> str:
    """状态对应的中文描述"""
    return {
        "success": "签到成功",
        "failed": "签到失败",
        "unknown": "结果未知",
    }.get(status, "结果未知")


def result_text(result: CheckinResult) -> str:
    """直接按接口原始返回拼接结果文案。"""
    if result.message and result.description:
        return f"{result.message}，{result.description}"
    return result.description or result.message or ""


def result_source_label(result_source: str) -> str:
    """签到结果来源的中文标签。"""
    return {
        "response": "接口响应",
        "points_record": "积分记录核验",
    }.get(result_source, "")


def should_retry_result(result: CheckinResult) -> bool:
    """Only retry when we could not parse a definitive business result."""
    return result.response_success is None


def choose_retry_delay(attempt: int, base_delay_seconds: float = RETRY_BASE_DELAY_SECONDS) -> float:
    """Use simple linear backoff so retry timing is easy to read in logs."""
    return max(0.0, base_delay_seconds * attempt)


def take_screenshot(page: Page, username: str, stage: str = "failure") -> Optional[str]:
    """截图当前页面，主要用于失败时的证据留存"""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = safe_file_stem(username)
    path = ARTIFACTS_DIR / f"{safe_name}-{safe_file_stem(stage)}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        log(f"截图已保存: {path}")
        return str(path)
    except Exception as e:
        log(f"截图失败: {e}")
        return None


def perform_checkin(page: Page, account: AccountConfig, attempt: int = 1) -> CheckinResult:
    """执行点击签到并捕获网络响应"""
    sign_label = SIGN_TYPE_TO_LABEL[account.sign_type]
    item = menu_sign_item(page, sign_label)
    
    try:
        item.wait_for(timeout=20_000)
    except TimeoutError:
        raise CheckinError(f"在菜单中未找到 '{sign_label}' 选项")

    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 触发动作: {sign_label}...")

    action_responses: list[Any] = []

    def collect_response(response) -> None:
        if is_checkin_action_response(response):
            action_responses.append(response)
            next_action = response.request.headers.get("next-action", "")
            log(
                f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 捕获候选响应: "
                f"status={response.status}, next-action={next_action[:10]}..., url={response.url}"
            )

    page.on("response", collect_response)
    try:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 等待签到 Server Action 响应...")
        try:
            with page.expect_response(is_checkin_action_response, timeout=60_000) as response_info:
                item.click(force=True)
        except TimeoutError as exc:
            body_text = compact(page.locator("body").inner_text(timeout=3_000))
            raise CheckinError(
                "等待签到接口响应超时；"
                f"当前 URL={page.url}；页面摘要={body_text[:200]}"
            ) from exc

        first_response = response_info.value
        if first_response not in action_responses:
            action_responses.append(first_response)
        page.wait_for_timeout(5_000)
    finally:
        page.remove_listener("response", collect_response)

    response, body_result, response_success, message, description = select_action_response(action_responses)
    raw_response = body_result.decoded_text
    log(
        f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 捕获到 {len(action_responses)} 个服务器响应，"
        f"选用 HTTP 状态码: {response.status}"
    )
    log(
        f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] body_read_status={body_result.read_status}, "
        f"raw_bytes_len={body_result.raw_bytes_len}, "
        f"content_type={body_result.header_content_type or '-'}, "
        f"content_length={body_result.header_content_length or '-'}, "
        f"transfer_encoding={body_result.header_transfer_encoding or '-'}"
    )
    if body_result.exception_type:
        log(
            f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] body_read_exception="
            f"{body_result.exception_type}: {body_result.exception_message}"
        )
    if body_result.raw_text_preview:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] raw_text_preview: {body_result.raw_text_preview}")
    log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] raw_response: {raw_response}")

    if response_success is True:
        status = "success"
    elif response_success is False:
        status = "failed"
    else:
        status = "unknown"
    
    screenshot_path = None
    if response_success is None:
        confirmed_remark = confirm_checkin_from_points_records(page, attempt)
        if confirmed_remark:
            return CheckinResult(
                username=account.username,
                sign_type=account.sign_type,
                sign_label=sign_label,
                status="success",
                response_success=True,
                message="",
                description=confirmed_remark,
                result_source="points_record",
                response_status=response.status,
                next_action=response.request.headers.get("next-action"),
                raw_response=raw_response[:1_000],
                attempt=attempt,
            )
        screenshot_path = take_screenshot(page, account.username, f"attempt-{attempt}-unknown")

    return CheckinResult(
        username=account.username,
        sign_type=account.sign_type,
        sign_label=sign_label,
        status=status,
        response_success=response_success,
        message=message,
        description=description,
        result_source="response" if response_success is not None else "",
        response_status=response.status,
        next_action=response.request.headers.get("next-action"),
        raw_response=raw_response[:1_000],
        screenshot_path=screenshot_path,
        attempt=attempt,
    )


def format_result_line(result: CheckinResult) -> str:
    """格式化打印到控制台的结果行"""
    detail = result_text(result) or status_label(result.status)
    emoji = status_emoji(result.status)
    elapsed = f", 耗时 {result.elapsed_seconds:.1f}s" if result.elapsed_seconds is not None else ""
    return (
        f"{emoji} [{result.status.upper()}] {result.username} ({result.sign_label}) "
        f"attempt={result.attempt}{elapsed} -> {detail}"
    )


def run_account_once(browser: Browser, account: AccountConfig, attempt: int) -> CheckinResult:
    """Run one isolated browser-context attempt for an account."""
    start = time.monotonic()
    context = build_context(browser)
    page = context.new_page()
    try:
        log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 新建浏览器上下文，开始登录: {account.username}")
        login(page, account)
        result = perform_checkin(page, account, attempt)
    except Exception as exc:
        elapsed = time.monotonic() - start
        log(
            f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 处理账号时发生异常: "
            f"{type(exc).__name__}: {exc}，耗时 {elapsed:.1f}s，当前 URL={page.url}"
        )
        screenshot_path = take_screenshot(page, account.username, f"attempt-{attempt}-failure")
        write_browser_diagnostics(page, account.username, f"attempt-{attempt}-failure")
        result = CheckinResult(
            username=account.username,
            sign_type=account.sign_type,
            sign_label=SIGN_TYPE_TO_LABEL[account.sign_type],
            status="failed",
            response_success=None,
            message="执行失败",
            description=str(exc),
            result_source="",
            screenshot_path=screenshot_path,
            attempt=attempt,
            elapsed_seconds=elapsed,
        )
    finally:
        try:
            context.close()
            log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 浏览器上下文已关闭")
        except Exception as exc:
            log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 关闭浏览器上下文失败: {exc}")

    if result.elapsed_seconds is None:
        result.elapsed_seconds = time.monotonic() - start
    return result


def run_account_with_retries(browser: Browser, account: AccountConfig) -> CheckinResult:
    """Retry transient/unknown automation failures while avoiding business-result retries."""
    last_result: Optional[CheckinResult] = None
    for attempt in range(1, MAX_CHECKIN_ATTEMPTS + 1):
        result = run_account_once(browser, account, attempt)
        last_result = result
        log(format_result_line(result))

        if not should_retry_result(result):
            log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 已获得明确业务结果，不再重试。")
            return result

        if attempt >= MAX_CHECKIN_ATTEMPTS:
            log(f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 已达到最大尝试次数，停止重试。")
            return result

        delay = choose_retry_delay(attempt, RETRY_BASE_DELAY_SECONDS)
        log(
            f"[尝试 {attempt}/{MAX_CHECKIN_ATTEMPTS}] 结果未知，将在 {delay:g}s 后重试；"
            f"原因: {result_text(result) or status_label(result.status)}"
        )
        if delay:
            time.sleep(delay)

    if last_result is None:
        raise CheckinError("未执行任何签到尝试")
    return last_result


def send_telegram_message(chat_id: str, message: str) -> None:
    """通过 Telegram Bot API 发送消息"""
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
            raise CheckinError(f"Telegram API 响应错误，状态码: {response.status}")


def build_chat_map(accounts: list[AccountConfig]) -> dict[str, Optional[str]]:
    """确定每个账号的消息推送目标 Chat ID"""
    chat_map: dict[str, Optional[str]] = {}
    for account in accounts:
        chat_map[account.username] = account.telegram_chat_id or TELEGRAM_CHAT_ID or None
    return chat_map


def build_telegram_message(chat_results: list[CheckinResult]) -> str:
    """构建 Telegram 推送消息的 HTML 内容"""
    counts = {
        "success": sum(result.status == "success" for result in chat_results),
        "failed": sum(result.status == "failed" for result in chat_results),
        "unknown": sum(result.status == "unknown" for result in chat_results),
    }
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "<b>🧩 HDHive 自动签到</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🕒 <b>执行时间</b>：<code>{escape_html(timestamp)}</code>",
        f"🌐 <b>目标站点</b>：<code>{escape_html(BASE_URL)}</code>",
        (
            "📊 <b>统计汇总</b>："
            f"成功 {counts['success']}  "
            f"/失败 {counts['failed']}  "
            f"/未知 {counts['unknown']}"
        ),
        "",
    ]

    for index, result in enumerate(chat_results, start=1):
        lines.append(f"<b>👥 </b>")
        lines.append(f"⎡ 📧 账号：<code>{escape_html(result.username)}</code>")
        lines.append(f"├ 🏷️ 类型：<code>{escape_html(result.sign_label)}</code>")
        lines.append(f"├ 🔁 尝试：<code>{result.attempt}</code>")
        lines.append(f"├ 📌 状态：<b>{escape_html(status_label(result.status))}</b>")
        if result.result_source:
            lines.append(f"├ 🔎 来源：<code>{escape_html(result_source_label(result.result_source) or result.result_source)}</code>")
        lines.append(f"⎣ 📝 结果：{escape_html(result_text(result) or status_label(result.status))}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines).strip()


def notify(results: list[CheckinResult], accounts: list[AccountConfig]) -> None:
    """推送通知主逻辑（按 Chat ID 分组发送）"""
    if not TELEGRAM_BOT_TOKEN:
        log("未配置 TELEGRAM_BOT_TOKEN，跳过推送通知。")
        return

    grouped: dict[str, list[CheckinResult]] = {}
    chat_map = build_chat_map(accounts)
    for result in results:
        chat_id = chat_map.get(result.username) or TELEGRAM_CHAT_ID or None
        if not chat_id:
            continue
        grouped.setdefault(chat_id, []).append(result)

    for chat_id, chat_results in grouped.items():
        try:
            message = build_telegram_message(chat_results)
            send_telegram_message(chat_id, message)
            log(f"成功将签到结果推送到 Telegram Chat: {chat_id}")
        except Exception as e:
            log(f"推送 Telegram 失败 (ID: {chat_id}): {e}")


def escape_html(value: str) -> str:
    """转义 HTML 特殊字符"""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def write_results(results: list[CheckinResult]) -> Path:
    """将运行结果持久化到 JSON 文件中"""
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
    """生成 GitHub Actions 的 Job Summary 表格"""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_path:
        return
    lines = [
        "## HDHive Check-in Results",
        "",
        f"- Generated at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- Site: `{BASE_URL}`",
        "",
        "| Account | Sign Type | Attempt | Duration | Status | Message |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for result in results:
        duration = f"{result.elapsed_seconds:.1f}s" if result.elapsed_seconds is not None else ""
        lines.append(
            f"| {result.username} | {result.sign_label} | {result.attempt} | {duration} | "
            f"{status_label(result.status)} | "
            f"{result_text(result)}".strip()
            + " |"
        )
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """主入口"""
    log("=== HDHive 自动化签到工具启动 ===")
    
    try:
        accounts = load_accounts()
    except CheckinError as exc:
        log(f"配置文件错误: {exc}")
        return 2

    results: list[CheckinResult] = []

    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            try:
                for idx, account in enumerate(accounts, start=1):
                    log(f"[{idx}/{len(accounts)}] 正在处理账号: {account.username} (模式: {account.sign_type})")
                    result = run_account_with_retries(browser, account)
                    results.append(result)
                    
                    # 账号之间预留一点间隔
                    if idx < len(accounts):
                        time.sleep(2)
            finally:
                browser.close()
    except Exception as exc:
        log(f"严重错误: {exc}")
        return 1

    # 执行结果持久化与通知
    try:
        notify(results, accounts)
    except Exception as exc:
        log(f"通知环节发生错误: {exc}")

    results_path = write_results(results)
    write_github_summary(results)
    log(f"任务结束报告已保存至: {results_path}")

    # 接口明确返回 success=false 属于业务结果，脚本仍视为执行成功。
    # 只有未解析到签到结果或脚本异常时才让 GitHub Actions 失败。
    has_failures = any(result.response_success is None for result in results)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
