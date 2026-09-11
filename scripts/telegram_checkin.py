#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    TelegramClient = None  # type: ignore[assignment]
    StringSession = None  # type: ignore[assignment]

try:
    import socks
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    socks = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_ENV = "TELEGRAM_LOCAL_CONFIG_PATH"
LEGACY_LOCAL_CONFIG_ENV = "HDHIVE_LOCAL_CONFIG_PATH"
DEFAULT_LOCAL_CONFIG_PATH = PROJECT_ROOT / "local.config.json"
DEFAULT_TASK_MESSAGE = "赌狗签到"
DEFAULT_PROJECT_NAME = "Telegram 自动任务"
PROXY_TYPE_ATTRS = {
    "socks5": "SOCKS5",
    "socks4": "SOCKS4",
    "http": "HTTP",
}


class CheckinError(Exception):
    """Raised when required configuration or Telegram execution fails."""


@dataclass
class TelegramTaskConfig:
    name: str
    type: str
    target_account: str
    bot_username: str
    message: str


@dataclass
class TelegramAccountConfig:
    name: str
    session: str
    tasks: list[TelegramTaskConfig]
    notify_chat_id: str = ""


@dataclass
class TelegramRuntimeConfig:
    api_id: int
    api_hash: str
    response_timeout_seconds: float
    artifacts_dir: Path
    accounts: list[TelegramAccountConfig]
    project_name: str = DEFAULT_PROJECT_NAME
    proxy: Optional[tuple[Any, ...]] = None
    proxy_label: str = ""


@dataclass
class TelegramTaskResult:
    telegram_account_name: str
    task_name: str
    task_type: str
    target_account: str
    bot_username: str
    sent_message: str
    status: str
    reply_text: str
    error: str = ""
    elapsed_seconds: Optional[float] = None


@dataclass
class LegacyTelegramTaskConfig:
    api_id: int
    api_hash: str
    session: str
    bot_username: str
    command: str
    response_timeout_seconds: float
    artifacts_dir: Path
    name: str = "default"
    notify_chat_id: str = ""
    proxy: Optional[tuple[Any, ...]] = None
    proxy_label: str = ""


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def compact(text: str) -> str:
    return " ".join((text or "").split())


def load_local_config() -> dict[str, Any]:
    config_path = os.getenv(LOCAL_CONFIG_ENV) or os.getenv(LEGACY_LOCAL_CONFIG_ENV) or str(DEFAULT_LOCAL_CONFIG_PATH)
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckinError(f"本地配置文件 JSON 格式错误 {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CheckinError(f"本地配置文件 {path} 必须是 JSON 对象")
    log(f"成功加载本地配置: {path}")
    return parsed


LOCAL_CONFIG = load_local_config()


def get_mapping_value(mapping: dict[str, Any], env_name: str, default: str = "", local_key: Optional[str] = None) -> str:
    key = local_key or env_name.lower()
    value = mapping.get(key)
    if value is not None and str(value).strip():
        return str(value).strip()
    value = mapping.get(env_name)
    if value is not None and str(value).strip():
        return str(value).strip()
    return default.strip()


def parse_api_id(api_id_raw: str) -> int:
    try:
        return int(api_id_raw)
    except ValueError as exc:
        raise CheckinError("TELEGRAM_API_ID 必须是数字") from exc


def parse_response_timeout(timeout_raw: str) -> float:
    try:
        return max(1, float(timeout_raw))
    except ValueError as exc:
        raise CheckinError("TELEGRAM_RESPONSE_TIMEOUT_SECONDS 必须是数字") from exc


def parse_telegram_proxy(proxy_value: Any) -> tuple[Optional[tuple[Any, ...]], str]:
    if proxy_value is None or proxy_value == "":
        return None, ""

    if socks is None:
        raise CheckinError("已配置 Telegram 代理，但未安装 PySocks，请先执行: python -m pip install -r requirements.txt")

    username: Optional[str] = None
    password: Optional[str] = None
    rdns = True

    if isinstance(proxy_value, str):
        raw_value = proxy_value.strip()
        if not raw_value:
            return None, ""
        parsed = urlparse(raw_value)
        proxy_type = parsed.scheme.lower()
        host = parsed.hostname or ""
        port = parsed.port or 0
        username = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password else None
    elif isinstance(proxy_value, dict):
        proxy_type = str(proxy_value.get("type", "socks5")).strip().lower()
        host = str(proxy_value.get("host", "")).strip()
        try:
            port = int(proxy_value.get("port", 0))
        except (TypeError, ValueError) as exc:
            raise CheckinError("telegram_proxy.port 必须是数字") from exc
        username = str(proxy_value.get("username", "")).strip() or None
        password = str(proxy_value.get("password", "")).strip() or None
        rdns = bool(proxy_value.get("rdns", True))
    else:
        raise CheckinError("telegram_proxy / TELEGRAM_PROXY_URL 必须是字符串或 JSON 对象")

    if proxy_type not in PROXY_TYPE_ATTRS:
        raise CheckinError("Telegram 代理类型只支持 socks5、socks4、http")
    if not host or not port:
        raise CheckinError("Telegram 代理必须包含 host 和 port")

    proxy_type_value = getattr(socks, PROXY_TYPE_ATTRS[proxy_type])
    label = f"{proxy_type}://{host}:{port}"
    if username or password:
        return (proxy_type_value, host, port, rdns, username, password), label
    return (proxy_type_value, host, port, rdns), label


def load_runtime_config_from_mapping(mapping: dict[str, Any]) -> TelegramRuntimeConfig:
    api_id_raw = get_mapping_value(mapping, "TELEGRAM_API_ID", "", "telegram_api_id")
    api_hash = get_mapping_value(mapping, "TELEGRAM_API_HASH", "", "telegram_api_hash")
    timeout_raw = get_mapping_value(
        mapping,
        "TELEGRAM_RESPONSE_TIMEOUT_SECONDS",
        "60",
        "telegram_response_timeout_seconds",
    )
    artifacts_dir_raw = get_mapping_value(mapping, "TELEGRAM_ARTIFACTS_DIR", "", "artifacts_dir")
    if not artifacts_dir_raw:
        artifacts_dir_raw = get_mapping_value(mapping, "HDHIVE_ARTIFACTS_DIR", "artifacts")
    artifacts_dir = Path(artifacts_dir_raw)
    project_name = get_mapping_value(mapping, "TELEGRAM_PROJECT_NAME", DEFAULT_PROJECT_NAME, "project_name")
    proxy_value = mapping.get("telegram_proxy")
    if proxy_value is None:
        proxy_value = get_mapping_value(mapping, "TELEGRAM_PROXY_URL", "", "telegram_proxy_url")
    accounts_value = mapping.get("telegram_accounts")
    if accounts_value is None:
        accounts_value = mapping.get("TELEGRAM_ACCOUNTS_JSON", "")
    legacy_accounts_value = mapping.get("hdhive_telegram_accounts_json")
    if legacy_accounts_value is None:
        legacy_accounts_value = mapping.get("HDHIVE_TELEGRAM_ACCOUNTS_JSON", "")

    missing = [
        name
        for name, value in {
            "TELEGRAM_API_ID": api_id_raw,
            "TELEGRAM_API_HASH": api_hash,
        }.items()
        if not value
    ]
    if missing:
        raise CheckinError(f"缺少必要配置: {', '.join(missing)}")

    api_id = parse_api_id(api_id_raw)
    response_timeout_seconds = parse_response_timeout(timeout_raw)
    proxy, proxy_label = parse_telegram_proxy(proxy_value)

    if accounts_value:
        accounts = parse_telegram_accounts(accounts_value)
    elif legacy_accounts_value:
        accounts = parse_legacy_telegram_accounts(legacy_accounts_value)
    else:
        raise CheckinError("缺少必要配置: TELEGRAM_ACCOUNTS_JSON / telegram_accounts")

    return TelegramRuntimeConfig(
        api_id=api_id,
        api_hash=api_hash,
        response_timeout_seconds=response_timeout_seconds,
        artifacts_dir=artifacts_dir,
        accounts=accounts,
        project_name=project_name,
        proxy=proxy,
        proxy_label=proxy_label,
    )


def parse_json_array(value: Any, config_name: str) -> list[Any]:
    if isinstance(value, str):
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CheckinError(f"{config_name} JSON 格式错误: {exc}") from exc
    else:
        parsed_value = value
    if not isinstance(parsed_value, list) or not parsed_value:
        raise CheckinError(f"{config_name} 必须是非空 JSON 数组")
    return parsed_value


def parse_telegram_accounts(accounts_value: Any) -> list[TelegramAccountConfig]:
    parsed_accounts = parse_json_array(accounts_value, "TELEGRAM_ACCOUNTS_JSON / telegram_accounts")
    accounts: list[TelegramAccountConfig] = []
    for account_index, item in enumerate(parsed_accounts, start=1):
        if not isinstance(item, dict):
            raise CheckinError("telegram_accounts 中每个账号必须是 JSON 对象")
        account_name = str(item.get("name", f"telegram-account-{account_index}")).strip() or f"telegram-account-{account_index}"
        session = str(item.get("session", "")).strip()
        if not session:
            raise CheckinError(f"{account_name} 缺少 session")
        tasks_value = item.get("tasks", [])
        if not isinstance(tasks_value, list) or not tasks_value:
            raise CheckinError(f"{account_name} 缺少 tasks，且 tasks 必须是非空数组")
        tasks = [
            parse_task_config(task_item, account_name=account_name, task_index=task_index)
            for task_index, task_item in enumerate(tasks_value, start=1)
        ]
        accounts.append(
            TelegramAccountConfig(
                name=account_name,
                session=session,
                notify_chat_id=str(item.get("notify_chat_id", "")).strip(),
                tasks=tasks,
            )
        )
    return accounts


def parse_task_config(item: Any, *, account_name: str, task_index: int) -> TelegramTaskConfig:
    if not isinstance(item, dict):
        raise CheckinError(f"{account_name} 的 tasks 中每个任务必须是 JSON 对象")

    task_name = str(item.get("name", f"task-{task_index}")).strip() or f"task-{task_index}"
    task_type = str(item.get("type", "")).strip()
    target_account = str(item.get("target_account", item.get("account_name", ""))).strip()
    bot_username = str(item.get("bot_username", "")).strip()
    message = str(item.get("message", item.get("command", ""))).strip()

    if not bot_username:
        raise CheckinError(f"{account_name} / {task_name} 缺少 bot_username")
    if not message:
        raise CheckinError(f"{account_name} / {task_name} 缺少 message")

    return TelegramTaskConfig(
        name=task_name,
        type=task_type or task_name,
        target_account=target_account or account_name,
        bot_username=bot_username,
        message=message,
    )


def parse_legacy_telegram_accounts(accounts_value: Any) -> list[TelegramAccountConfig]:
    parsed_accounts = parse_json_array(accounts_value, "HDHIVE_TELEGRAM_ACCOUNTS_JSON / hdhive_telegram_accounts_json")
    accounts: list[TelegramAccountConfig] = []
    for index, item in enumerate(parsed_accounts, start=1):
        if not isinstance(item, dict):
            raise CheckinError("HDHIVE_TELEGRAM_ACCOUNTS_JSON 中每个账号必须是 JSON 对象")
        name = str(item.get("name", f"account-{index}")).strip() or f"account-{index}"
        session = str(item.get("session", "")).strip()
        bot_username = str(item.get("bot_username", "")).strip()
        command = str(item.get("command", DEFAULT_TASK_MESSAGE)).strip() or DEFAULT_TASK_MESSAGE
        if not session:
            raise CheckinError(f"{name} 缺少 session")
        if not bot_username:
            raise CheckinError(f"{name} 缺少 bot_username")
        accounts.append(
            TelegramAccountConfig(
                name=name,
                session=session,
                notify_chat_id=str(item.get("notify_chat_id", "")).strip(),
                tasks=[
                    TelegramTaskConfig(
                        name=str(item.get("task_name", "HDHive 自动签到")).strip() or "HDHive 自动签到",
                        type=str(item.get("type", "签到")).strip() or "签到",
                        target_account=name,
                        bot_username=bot_username,
                        message=command,
                    )
                ],
            )
        )
    return accounts


def load_account_configs_from_mapping(mapping: dict[str, Any]) -> list[LegacyTelegramTaskConfig]:
    """Compatibility helper for old tests and integrations."""
    runtime = load_runtime_config_from_mapping(mapping)
    configs: list[LegacyTelegramTaskConfig] = []
    for account in runtime.accounts:
        for task in account.tasks:
            configs.append(
                LegacyTelegramTaskConfig(
                    api_id=runtime.api_id,
                    api_hash=runtime.api_hash,
                    session=account.session,
                    bot_username=task.bot_username,
                    command=task.message,
                    response_timeout_seconds=runtime.response_timeout_seconds,
                    artifacts_dir=runtime.artifacts_dir,
                    name=account.name,
                    notify_chat_id=account.notify_chat_id,
                    proxy=runtime.proxy,
                    proxy_label=runtime.proxy_label,
                )
            )
    return configs


def load_summary_notify_chat_id_from_mapping(mapping: dict[str, Any]) -> str:
    return get_mapping_value(
        mapping,
        "TELEGRAM_SUMMARY_NOTIFY_CHAT_ID",
        "",
        "telegram_summary_notify_chat_id",
    )


def load_telegram_bot_token_from_mapping(mapping: dict[str, Any]) -> str:
    return get_mapping_value(
        mapping,
        "TELEGRAM_BOT_TOKEN",
        "",
        "telegram_bot_token",
    )


def load_runtime_config() -> TelegramRuntimeConfig:
    env_mapping = {
        "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID", ""),
        "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", ""),
        "TELEGRAM_RESPONSE_TIMEOUT_SECONDS": os.getenv("TELEGRAM_RESPONSE_TIMEOUT_SECONDS", ""),
        "TELEGRAM_ARTIFACTS_DIR": os.getenv("TELEGRAM_ARTIFACTS_DIR", ""),
        "HDHIVE_ARTIFACTS_DIR": os.getenv("HDHIVE_ARTIFACTS_DIR", ""),
        "TELEGRAM_SUMMARY_NOTIFY_CHAT_ID": os.getenv("TELEGRAM_SUMMARY_NOTIFY_CHAT_ID", ""),
        "TELEGRAM_ACCOUNTS_JSON": os.getenv("TELEGRAM_ACCOUNTS_JSON", ""),
        "HDHIVE_TELEGRAM_ACCOUNTS_JSON": os.getenv("HDHIVE_TELEGRAM_ACCOUNTS_JSON", ""),
        "TELEGRAM_PROXY_URL": os.getenv("TELEGRAM_PROXY_URL", ""),
        "TELEGRAM_PROJECT_NAME": os.getenv("TELEGRAM_PROJECT_NAME", ""),
    }
    merged = {**env_mapping, **LOCAL_CONFIG}
    return load_runtime_config_from_mapping(merged)


def load_runtime_configs() -> list[LegacyTelegramTaskConfig]:
    """Compatibility helper for the previous one-task-per-config API."""
    runtime = load_runtime_config()
    configs: list[LegacyTelegramTaskConfig] = []
    for account in runtime.accounts:
        for task in account.tasks:
            configs.append(
                LegacyTelegramTaskConfig(
                    api_id=runtime.api_id,
                    api_hash=runtime.api_hash,
                    session=account.session,
                    bot_username=task.bot_username,
                    command=task.message,
                    response_timeout_seconds=runtime.response_timeout_seconds,
                    artifacts_dir=runtime.artifacts_dir,
                    name=account.name,
                    notify_chat_id=account.notify_chat_id,
                    proxy=runtime.proxy,
                    proxy_label=runtime.proxy_label,
                )
            )
    return configs


def load_summary_notify_chat_id() -> str:
    env_mapping = {
        "TELEGRAM_SUMMARY_NOTIFY_CHAT_ID": os.getenv("TELEGRAM_SUMMARY_NOTIFY_CHAT_ID", ""),
    }
    merged = {**env_mapping, **LOCAL_CONFIG}
    return load_summary_notify_chat_id_from_mapping(merged)


def load_telegram_bot_token() -> str:
    env_mapping = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    }
    merged = {**env_mapping, **LOCAL_CONFIG}
    return load_telegram_bot_token_from_mapping(merged)


async def run_telegram_checkin(config: LegacyTelegramTaskConfig) -> TelegramTaskResult:
    if TelegramClient is None or StringSession is None:
        raise CheckinError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")

    runtime = TelegramRuntimeConfig(
        api_id=config.api_id,
        api_hash=config.api_hash,
        response_timeout_seconds=config.response_timeout_seconds,
        artifacts_dir=config.artifacts_dir,
        accounts=[
            TelegramAccountConfig(
                name=config.name,
                session=config.session,
                notify_chat_id=config.notify_chat_id,
                tasks=[
                    TelegramTaskConfig(
                        name=config.command,
                        type=config.command,
                        target_account=config.name,
                        bot_username=config.bot_username,
                        message=config.command,
                    )
                ],
            )
        ],
        proxy=config.proxy,
        proxy_label=config.proxy_label,
    )
    return (await run_telegram_account_tasks(runtime, runtime.accounts[0]))[0]


async def run_telegram_account_tasks(runtime: TelegramRuntimeConfig, account: TelegramAccountConfig) -> list[TelegramTaskResult]:
    if TelegramClient is None or StringSession is None:
        raise CheckinError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")

    log(f"[{account.name}] 准备执行 {len(account.tasks)} 个 Telegram 任务")
    if runtime.proxy_label:
        log(f"[{account.name}] 使用 Telegram 代理: {runtime.proxy_label}")

    results: list[TelegramTaskResult] = []
    client = TelegramClient(StringSession(account.session), runtime.api_id, runtime.api_hash, proxy=runtime.proxy)
    async with client:
        for task in account.tasks:
            result = await run_single_task(client, runtime, account, task)
            results.append(result)

        if account.notify_chat_id and results:
            await send_account_notification(client, account.notify_chat_id, runtime.project_name, results)

    return results


async def run_single_task(
    client: Any,
    runtime: TelegramRuntimeConfig,
    account: TelegramAccountConfig,
    task: TelegramTaskConfig,
) -> TelegramTaskResult:
    started_at = datetime.now()
    log(f"[{account.name}] [{task.name}] 准备向 {task.bot_username} 发送消息: {task.message}")
    try:
        bot = await client.get_entity(task.bot_username)
        async with client.conversation(bot, timeout=runtime.response_timeout_seconds, exclusive=False) as conv:
            await conv.send_message(task.message)
            log(f"[{account.name}] [{task.name}] 消息已发送，等待机器人回复...")
            reply = await conv.get_response()
        reply_text = getattr(reply, "raw_text", "") or getattr(reply, "message", "") or ""
        result = TelegramTaskResult(
            telegram_account_name=account.name,
            task_name=task.name,
            task_type=task.type,
            target_account=task.target_account,
            bot_username=task.bot_username,
            sent_message=task.message,
            status="replied",
            reply_text=compact(reply_text) or "机器人回复为空",
            elapsed_seconds=(datetime.now() - started_at).total_seconds(),
        )
        log(f"[{account.name}] [{task.name}] 机器人返回: {result.reply_text}")
        return result
    except asyncio.TimeoutError:
        result = TelegramTaskResult(
            telegram_account_name=account.name,
            task_name=task.name,
            task_type=task.type,
            target_account=task.target_account,
            bot_username=task.bot_username,
            sent_message=task.message,
            status="timeout",
            reply_text=f"超过 {runtime.response_timeout_seconds:g} 秒未收到机器人回复",
            elapsed_seconds=(datetime.now() - started_at).total_seconds(),
        )
        log(f"[{account.name}] [{task.name}] {result.reply_text}")
        return result
    except Exception as exc:
        result = TelegramTaskResult(
            telegram_account_name=account.name,
            task_name=task.name,
            task_type=task.type,
            target_account=task.target_account,
            bot_username=task.bot_username,
            sent_message=task.message,
            status="error",
            reply_text="任务执行异常",
            error=str(exc),
            elapsed_seconds=(datetime.now() - started_at).total_seconds(),
        )
        log(f"[{account.name}] [{task.name}] 任务执行异常: {exc}")
        return result


async def resolve_notify_target(client: Any, notify_chat_id: str) -> Any:
    target = notify_chat_id.strip()
    if target.lower() in {"me", "self", "saved", "saved_messages"}:
        return "me"

    if re.fullmatch(r"-?\d+", target):
        numeric_target = int(target)
        me = await client.get_me()
        if getattr(me, "id", None) == numeric_target:
            return "me"

        async for dialog in client.iter_dialogs():
            entity = getattr(dialog, "entity", None)
            if getattr(entity, "id", None) == numeric_target:
                return entity
        return numeric_target

    return target


async def send_summary_notification(client: Any, notify_chat_id: str, result: TelegramTaskResult) -> bool:
    try:
        target = await resolve_notify_target(client, notify_chat_id)
        await client.send_message(target, build_summary_message(result), parse_mode="html")
    except Exception as exc:
        log(f"结果通知发送失败，任务结果不受影响: {exc}")
        return False

    log(f"已发送结果通知到 Telegram Chat: {notify_chat_id}")
    return True


async def send_account_notification(
    client: Any,
    notify_chat_id: str,
    project_name: str,
    results: list[TelegramTaskResult],
) -> bool:
    try:
        target = await resolve_notify_target(client, notify_chat_id)
        await client.send_message(target, build_account_notification_message(project_name, results), parse_mode="html")
    except Exception as exc:
        log(f"账号任务通知发送失败，任务结果不受影响: {exc}")
        return False

    log(f"已发送账号任务通知到 Telegram Chat: {notify_chat_id}")
    return True


def send_run_summary_notification(bot_token: str, notify_chat_id: str, project_name: str, results: list[TelegramTaskResult]) -> bool:
    """Send the all-task summary through Telegram Bot API."""
    token = bot_token.strip()
    chat_id = notify_chat_id.strip()
    if not token or not chat_id:
        return False

    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": build_summary_notification_message(project_name, results),
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(response_body)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                log(f"汇总通知发送失败，任务结果不受影响: {parsed}")
                return False
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        log(f"汇总通知发送失败，任务结果不受影响: {exc}")
        return False

    log(f"已通过 Telegram Bot 发送所有账号汇总通知到 Chat: {chat_id}")
    return True


def build_summary_message(result: TelegramTaskResult) -> str:
    elapsed = "" if result.elapsed_seconds is None else f"\n├ 耗时：<code>{result.elapsed_seconds:.1f}s</code>"
    error = "" if not result.error else f"\n├ 异常：{escape(result.error)}"
    return (
        "🧩 <b>Telegram 自动任务</b>\n"
        f"├ 执行时间：<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"├ Telegram账号：<code>{escape(result.telegram_account_name)}</code>\n"
        f"⎡ 任务名称：{escape(result.task_name)}\n"
        f"├ 任务类型：{escape(result.task_type)}\n"
        f"├ 任务账号：<code>{escape(result.target_account)}</code>\n"
        f"├ 目标机器人：<code>{escape(result.bot_username)}</code>\n"
        f"├ 发送内容：<code>{escape(result.sent_message)}</code>"
        f"{elapsed}"
        f"{error}\n"
        f"⎣ 机器人返回：{escape(result.reply_text)}"
    )


def build_account_notification_message(project_name: str, results: list[TelegramTaskResult]) -> str:
    if not results:
        return f"🧩 <b>{escape(project_name)}</b>\n暂无任务结果"

    account_name = results[0].telegram_account_name
    lines = [
        f"🧩 <b>{escape(project_name)}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🕒 执行时间：<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>",
        "",
        f"👥 Telegram账号：<code>{escape(account_name)}</code>",
    ]
    for result in results:
        lines.extend(build_task_result_lines(result))
    return "\n".join(lines)


def build_summary_notification_message(project_name: str, results: list[TelegramTaskResult]) -> str:
    grouped: dict[str, list[TelegramTaskResult]] = {}
    for result in results:
        grouped.setdefault(result.telegram_account_name, []).append(result)

    lines = [
        f"🧩 <b>{escape(project_name)}汇总</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🕒 执行时间：<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>",
        f"📦 任务数量：{len(results)}",
    ]
    for account_name, account_results in grouped.items():
        lines.extend(
            [
                "",
                f"👥 Telegram账号：<code>{escape(account_name)}</code>",
            ]
        )
        for result in account_results:
            lines.extend(build_task_result_lines(result))
    return "\n".join(lines)


def build_task_result_lines(result: TelegramTaskResult) -> list[str]:
    error = f"\n├ ⚠️ 异常信息：{escape(result.error)}" if result.error else ""
    return [
        "",
        f"⎡ 🏷️ 任务名称：{escape(result.task_name)}",
        f"├ 📌 任务类型：{escape(result.task_type)}",
        f"├ 👤 任务账号：<code>{escape(result.target_account)}</code>",
        f"├ 🤖 目标机器人：<code>{escape(result.bot_username)}</code>",
        f"├ 📤 发送内容：<code>{escape(result.sent_message)}</code>{error}",
        f"⎣ 📝 机器人返回：{escape(result.reply_text)}",
    ]


def write_outputs(result: TelegramTaskResult | list[TelegramTaskResult], artifacts_dir: Path) -> None:
    results = result if isinstance(result, list) else [result]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifacts_dir / "latest-results.json"
    payload: dict[str, Any] = {
        "summary": {"total": len(results)},
        "results": [asdict(item) for item in results],
    }
    if len(results) == 1:
        payload.update(asdict(results[0]))
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"任务结果已保存至: {result_path}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if summary_path:
        Path(summary_path).write_text(build_markdown_summary(results), encoding="utf-8")


def build_markdown_summary(result: TelegramTaskResult | list[TelegramTaskResult]) -> str:
    results = result if isinstance(result, list) else [result]
    lines = [
        "# Telegram Automated Tasks",
        "",
        f"- Total: `{len(results)}`",
        "",
        "| Telegram account | Task | Type | Target account | Bot | Sent message | Status | Bot reply |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        lines.append(
            f"| {item.telegram_account_name} | {item.task_name} | {item.task_type} | {item.target_account} | "
            f"`{item.bot_username}` | `{item.sent_message}` | `{item.status}` | {item.reply_text} |"
        )
    return "\n".join(lines) + "\n"


async def async_main() -> int:
    results: list[TelegramTaskResult] = []
    try:
        runtime = load_runtime_config()
        summary_notify_chat_id = load_summary_notify_chat_id()
        telegram_bot_token = load_telegram_bot_token()
        task_count = sum(len(account.tasks) for account in runtime.accounts)
        log(f"成功加载 {len(runtime.accounts)} 个 Telegram 账号，共 {task_count} 个任务")
        for account in runtime.accounts:
            results.extend(await run_telegram_account_tasks(runtime, account))
        write_outputs(results, runtime.artifacts_dir)
        if summary_notify_chat_id:
            if telegram_bot_token:
                send_run_summary_notification(telegram_bot_token, summary_notify_chat_id, runtime.project_name, results)
            else:
                log("已配置汇总通知目标，但未配置 TELEGRAM_BOT_TOKEN / telegram_bot_token，跳过汇总通知。")
    except CheckinError as exc:
        log(f"配置或执行错误: {exc}")
        return 1

    return 0 if results and all(result.status == "replied" for result in results) else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
