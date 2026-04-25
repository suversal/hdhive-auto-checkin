#!/usr/bin/env python3

import json
import os
import re
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


BASE_URL = os.getenv("HDHIVE_BASE_URL", "https://hdhive.com").rstrip("/")
LOGIN_URL = f"{BASE_URL}/login"
DEFAULT_SIGN_TYPE = os.getenv("HDHIVE_SIGN_TYPE", "daily").strip().lower()
HEADLESS = os.getenv("HDHIVE_HEADLESS", "true").strip().lower() != "false"
BROWSER_PATH = os.getenv("HDHIVE_BROWSER_PATH", "").strip() or None
BROWSER_CHANNEL = os.getenv("HDHIVE_BROWSER_CHANNEL", "chrome").strip() or None
TZ = os.getenv("HDHIVE_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
ARTIFACTS_DIR = Path(os.getenv("HDHIVE_ARTIFACTS_DIR", "artifacts"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ACCOUNTS_ENV = "HDHIVE_ACCOUNTS_JSON"

SIGN_TYPE_TO_LABEL = {
    "daily": "每日签到",
    "gamble": "赌狗签到",
}


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
    raw = os.getenv(ACCOUNTS_ENV, "").strip()
    if not raw:
        raise CheckinError(f"Missing required environment variable: {ACCOUNTS_ENV}")

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
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id=TZ,
        viewport={"width": 1440, "height": 900},
    )
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
        Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
        """
    )
    return context


def launch_browser(playwright: Playwright) -> Browser:
    launch_kwargs: dict[str, Any] = {"headless": HEADLESS}
    if BROWSER_PATH:
        launch_kwargs["executable_path"] = BROWSER_PATH
    elif BROWSER_CHANNEL:
        launch_kwargs["channel"] = BROWSER_CHANNEL
    log(f"Launching browser with headless={HEADLESS}, browser_path={BROWSER_PATH or '-'}, channel={BROWSER_CHANNEL or '-'}")
    return playwright.chromium.launch(**launch_kwargs)


def wait_for_login_form(page: Page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(6_000)
    try:
        page.locator("input").nth(1).wait_for(timeout=15_000)
    except TimeoutError as exc:
        body_text = compact(page.locator("body").inner_text())
        raise CheckinError(f"Login form did not appear: {body_text}") from exc


def compact(text: str) -> str:
    return " ".join(text.split())


def dismiss_notice(page: Page) -> None:
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
    page.locator('button[aria-label="用户菜单"]').click(force=True)
    page.wait_for_timeout(1_500)
    return page.get_by_text(sign_label, exact=False).first


def decode_response_text(response) -> str:
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
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", username)
    path = ARTIFACTS_DIR / f"{safe_name}-{int(time.time())}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def perform_checkin(page: Page, account: AccountConfig) -> CheckinResult:
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
    chat_map: dict[str, Optional[str]] = {}
    for account in accounts:
        chat_map[account.username] = account.telegram_chat_id or TELEGRAM_CHAT_ID or None
    return chat_map


def build_telegram_message(chat_results: list[CheckinResult]) -> str:
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
