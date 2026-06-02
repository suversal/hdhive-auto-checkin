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

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    TelegramClient = None  # type: ignore[assignment]
    StringSession = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_ENV = "HDHIVE_LOCAL_CONFIG_PATH"
DEFAULT_LOCAL_CONFIG_PATH = PROJECT_ROOT / "local.config.json"
HDHIVE_BASE_URL = "https://hdhive.com"
DEFAULT_SIGN_COMMAND = "赌狗签到"


class CheckinError(Exception):
    """Raised when required configuration or Telegram execution fails."""


@dataclass
class TelegramCheckinResult:
    command: str
    status: str
    response_success: Optional[bool]
    message: str
    description: str
    account_name: str = "default"
    result_source: str = "telegram_bot"
    points: Optional[int] = None
    already_signed: bool = False
    raw_reply: str = ""
    elapsed_seconds: Optional[float] = None


@dataclass
class TelegramRuntimeConfig:
    api_id: int
    api_hash: str
    session: str
    bot_username: str
    command: str
    response_timeout_seconds: float
    artifacts_dir: Path
    name: str = "default"
    notify_chat_id: str = ""


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def compact(text: str) -> str:
    return " ".join((text or "").split())


def load_local_config() -> dict[str, Any]:
    path = Path(os.getenv(LOCAL_CONFIG_ENV, str(DEFAULT_LOCAL_CONFIG_PATH))).expanduser()
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
    if value is not None:
        return str(value).strip()
    value = mapping.get(env_name)
    if value is not None:
        return str(value).strip()
    return default.strip()


def parse_points(text: str) -> Optional[int]:
    match = re.search(r"获得\s*([+-]?\d+)\s*积分", text)
    if not match:
        return None
    return int(match.group(1))


def parse_bot_reply(reply_text: str, *, command: str) -> TelegramCheckinResult:
    description = compact(reply_text)
    points = parse_points(description)

    if "签到成功" in description:
        return TelegramCheckinResult(
            command=command,
            status="success",
            response_success=True,
            message="签到成功",
            description=description,
            points=points,
            raw_reply=reply_text,
        )

    if "已经签到" in description or "明天再来" in description:
        return TelegramCheckinResult(
            command=command,
            status="success",
            response_success=True,
            message="今日已签到",
            description=description,
            points=points,
            already_signed=True,
            raw_reply=reply_text,
        )

    if "失败" in description:
        return TelegramCheckinResult(
            command=command,
            status="failed",
            response_success=False,
            message="签到失败",
            description=description,
            points=points,
            raw_reply=reply_text,
        )

    return TelegramCheckinResult(
        command=command,
        status="unknown",
        response_success=None,
        message="未识别机器人回复",
        description=description or "机器人回复为空",
        points=points,
        raw_reply=reply_text,
    )


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


def load_account_configs_from_mapping(mapping: dict[str, Any]) -> list[TelegramRuntimeConfig]:
    api_id_raw = get_mapping_value(mapping, "TELEGRAM_API_ID", "", "telegram_api_id")
    api_hash = get_mapping_value(mapping, "TELEGRAM_API_HASH", "", "telegram_api_hash")
    timeout_raw = get_mapping_value(
        mapping,
        "TELEGRAM_RESPONSE_TIMEOUT_SECONDS",
        "60",
        "telegram_response_timeout_seconds",
    )
    artifacts_dir = Path(get_mapping_value(mapping, "HDHIVE_ARTIFACTS_DIR", "artifacts", "artifacts_dir"))
    accounts_value = mapping.get("hdhive_telegram_accounts_json")
    if accounts_value is None:
        accounts_value = mapping.get("HDHIVE_TELEGRAM_ACCOUNTS_JSON", "")

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

    if not accounts_value:
        raise CheckinError("缺少必要配置: HDHIVE_TELEGRAM_ACCOUNTS_JSON")

    if isinstance(accounts_value, str):
        try:
            parsed_accounts = json.loads(accounts_value)
        except json.JSONDecodeError as exc:
            raise CheckinError(f"HDHIVE_TELEGRAM_ACCOUNTS_JSON JSON 格式错误: {exc}") from exc
    else:
        parsed_accounts = accounts_value
    if isinstance(parsed_accounts, dict):
        parsed_accounts = [parsed_accounts]
    if not isinstance(parsed_accounts, list) or not parsed_accounts:
        raise CheckinError("HDHIVE_TELEGRAM_ACCOUNTS_JSON 必须是非空 JSON 数组")

    configs: list[TelegramRuntimeConfig] = []
    for index, item in enumerate(parsed_accounts, start=1):
        if not isinstance(item, dict):
            raise CheckinError("HDHIVE_TELEGRAM_ACCOUNTS_JSON 中每个账号必须是 JSON 对象")
        session = str(item.get("session", "")).strip()
        bot_username = str(item.get("bot_username", "")).strip()
        name = str(item.get("name", f"account-{index}")).strip() or f"account-{index}"
        if not session:
            raise CheckinError(f"{name} 缺少 session")
        if not bot_username:
            raise CheckinError(f"{name} 缺少 bot_username")
        configs.append(
            TelegramRuntimeConfig(
                api_id=api_id,
                api_hash=api_hash,
                session=session,
                bot_username=bot_username,
                command=str(item.get("command", DEFAULT_SIGN_COMMAND)).strip() or DEFAULT_SIGN_COMMAND,
                response_timeout_seconds=response_timeout_seconds,
                artifacts_dir=artifacts_dir,
                name=name,
                notify_chat_id=str(item.get("notify_chat_id", "")).strip(),
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


def load_runtime_configs() -> list[TelegramRuntimeConfig]:
    env_mapping = {
        "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID", ""),
        "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH", ""),
        "TELEGRAM_RESPONSE_TIMEOUT_SECONDS": os.getenv("TELEGRAM_RESPONSE_TIMEOUT_SECONDS", ""),
        "HDHIVE_ARTIFACTS_DIR": os.getenv("HDHIVE_ARTIFACTS_DIR", ""),
        "TELEGRAM_SUMMARY_NOTIFY_CHAT_ID": os.getenv("TELEGRAM_SUMMARY_NOTIFY_CHAT_ID", ""),
        "HDHIVE_TELEGRAM_ACCOUNTS_JSON": os.getenv("HDHIVE_TELEGRAM_ACCOUNTS_JSON", ""),
    }
    merged = {**env_mapping, **LOCAL_CONFIG}
    return load_account_configs_from_mapping(merged)


def load_summary_notify_chat_id() -> str:
    env_mapping = {
        "TELEGRAM_SUMMARY_NOTIFY_CHAT_ID": os.getenv("TELEGRAM_SUMMARY_NOTIFY_CHAT_ID", ""),
    }
    merged = {**env_mapping, **LOCAL_CONFIG}
    return load_summary_notify_chat_id_from_mapping(merged)


async def run_telegram_checkin(config: TelegramRuntimeConfig) -> TelegramCheckinResult:
    if TelegramClient is None or StringSession is None:
        raise CheckinError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")

    started_at = datetime.now()
    log(f"[{config.name}] 准备向 {config.bot_username} 发送签到命令: {config.command}")

    client = TelegramClient(StringSession(config.session), config.api_id, config.api_hash)
    async with client:
        bot = await client.get_entity(config.bot_username)
        async with client.conversation(bot, timeout=config.response_timeout_seconds, exclusive=False) as conv:
            await conv.send_message(config.command)
            log(f"[{config.name}] 签到命令已发送，等待机器人回复...")
            reply = await conv.get_response()

        reply_text = getattr(reply, "raw_text", "") or getattr(reply, "message", "") or ""
        result = parse_bot_reply(reply_text, command=config.command)
        result.account_name = config.name
        result.elapsed_seconds = (datetime.now() - started_at).total_seconds()
        log(f"[{config.name}] 机器人回复: {result.description}")

        if config.notify_chat_id:
            await send_summary_notification(client, config.notify_chat_id, result)

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


async def send_summary_notification(client: Any, notify_chat_id: str, result: TelegramCheckinResult) -> bool:
    try:
        target = await resolve_notify_target(client, notify_chat_id)
        await client.send_message(target, build_summary_message(result), parse_mode="html")
    except Exception as exc:
        log(f"结果通知发送失败，签到结果不受影响: {exc}")
        return False

    log(f"已发送结果通知到 Telegram Chat: {notify_chat_id}")
    return True


async def send_run_summary_notification(config: TelegramRuntimeConfig, notify_chat_id: str, results: list[TelegramCheckinResult]) -> bool:
    if TelegramClient is None or StringSession is None:
        raise CheckinError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")

    client = TelegramClient(StringSession(config.session), config.api_id, config.api_hash)
    async with client:
        try:
            target = await resolve_notify_target(client, notify_chat_id)
            await client.send_message(target, build_summary_notification_message(results), parse_mode="html")
        except Exception as exc:
            log(f"汇总通知发送失败，签到结果不受影响: {exc}")
            return False

    log(f"已发送所有账号汇总通知到 Telegram Chat: {notify_chat_id}")
    return True


def build_summary_message(result: TelegramCheckinResult) -> str:
    status_label = {
        "success": "签到成功",
        "failed": "签到失败",
        "unknown": "结果未知",
    }.get(result.status, result.status)
    already_signed = "是" if result.already_signed else "否"
    points = "" if result.points is None else f"\n├ 积分: <b>{result.points}</b>"
    elapsed = "" if result.elapsed_seconds is None else f"\n├ 耗时: <code>{result.elapsed_seconds:.1f}s</code>"
    safe_description = escape(result.description)
    safe_command = escape(result.command)
    return (
        "🧩 <b>HDHive Telegram 自动签到</b>\n"
        f"├ 执行时间: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"├ 命令: <code>{safe_command}</code>\n"
        f"├ 状态: <b>{status_label}</b>\n"
        f"├ 已签: <code>{already_signed}</code>"
        f"{points}"
        f"{elapsed}\n"
        f"└ 结果: {safe_description}"
    )


def build_summary_notification_message(results: list[TelegramCheckinResult]) -> str:
    summary = build_run_summary(results)
    lines = [
        "🧩 <b>HDHive 自动签到</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🕒 执行时间：<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>",
        f"🌐 目标站点：<code>{HDHIVE_BASE_URL}</code>",
        f"📊 统计汇总：成功 {summary['success']}  /失败 {summary['failed']}  /未知 {summary['unknown']}",
    ]
    for result in results:
        lines.extend(
            [
                "",
                "👥",
                f"⎡ 📧 账号：<code>{escape(result.account_name)}</code>",
                f"├ 🏷️ 类型：{escape(result.command)}",
                f"⎣ 📝 结果：{escape(result.description)}",
            ]
        )
    return "\n".join(lines)


def build_run_summary(results: list[TelegramCheckinResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "success": sum(1 for result in results if result.status == "success"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "unknown": sum(1 for result in results if result.status == "unknown"),
    }


def write_outputs(result: TelegramCheckinResult | list[TelegramCheckinResult], artifacts_dir: Path) -> None:
    results = result if isinstance(result, list) else [result]
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifacts_dir / "latest-results.json"
    payload: dict[str, Any] = {
        "summary": build_run_summary(results),
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


def build_markdown_summary(result: TelegramCheckinResult | list[TelegramCheckinResult]) -> str:
    results = result if isinstance(result, list) else [result]
    summary = build_run_summary(results)
    lines = [
        "# HDHive Telegram Check-in",
        "",
        f"- Total: `{summary['total']}`",
        f"- Success: `{summary['success']}`",
        f"- Failed: `{summary['failed']}`",
        f"- Unknown: `{summary['unknown']}`",
        "",
        "| Account | Command | Status | Already signed | Points | Result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        points = "" if item.points is None else str(item.points)
        lines.append(
            f"| {item.account_name} | `{item.command}` | `{item.status}` | "
            f"`{item.already_signed}` | `{points}` | {item.description} |"
        )
    return "\n".join(lines) + "\n"


async def async_main() -> int:
    results: list[TelegramCheckinResult] = []
    try:
        configs = load_runtime_configs()
        summary_notify_chat_id = load_summary_notify_chat_id()
        artifacts_dir = configs[0].artifacts_dir
        log(f"成功加载 {len(configs)} 个 Telegram 签到账号")
        for config in configs:
            try:
                results.append(await run_telegram_checkin(config))
            except asyncio.TimeoutError:
                result = TelegramCheckinResult(
                    account_name=config.name,
                    command=config.command,
                    status="unknown",
                    response_success=None,
                    message="等待机器人回复超时",
                    description=f"超过 {config.response_timeout_seconds:g} 秒未收到机器人回复",
                    result_source="telegram_bot",
                )
                results.append(result)
                log(f"[{config.name}] {result.description}")
            except Exception as exc:
                result = TelegramCheckinResult(
                    account_name=config.name,
                    command=config.command,
                    status="failed",
                    response_success=False,
                    message="签到执行异常",
                    description=str(exc),
                    result_source="telegram_bot",
                )
                results.append(result)
                log(f"[{config.name}] 签到执行异常: {exc}")
        write_outputs(results, artifacts_dir)
        if summary_notify_chat_id:
            await send_run_summary_notification(configs[0], summary_notify_chat_id, results)
    except CheckinError as exc:
        log(f"配置或执行错误: {exc}")
        return 1

    return 0 if results and all(result.status == "success" for result in results) else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
