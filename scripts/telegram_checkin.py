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


class CheckinError(Exception):
    """Raised when required configuration or Telegram execution fails."""


@dataclass
class TelegramCheckinResult:
    command: str
    status: str
    response_success: Optional[bool]
    message: str
    description: str
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


def get_config_value(env_name: str, default: str = "", local_key: Optional[str] = None) -> str:
    key = local_key or env_name.lower()
    local_value = LOCAL_CONFIG.get(key)
    if local_value is not None:
        return str(local_value).strip()
    return os.getenv(env_name, default).strip()


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


def load_runtime_config() -> TelegramRuntimeConfig:
    api_id_raw = get_config_value("TELEGRAM_API_ID", "", "telegram_api_id")
    api_hash = get_config_value("TELEGRAM_API_HASH", "", "telegram_api_hash")
    session = get_config_value("TELEGRAM_SESSION", "", "telegram_session")
    bot_username = get_config_value("HDHIVE_BOT_USERNAME", "", "hdhive_bot_username")
    command = get_config_value("HDHIVE_SIGN_COMMAND", "赌狗签到", "hdhive_sign_command")
    timeout_raw = get_config_value("TELEGRAM_RESPONSE_TIMEOUT_SECONDS", "60", "telegram_response_timeout_seconds")
    artifacts_dir = Path(get_config_value("HDHIVE_ARTIFACTS_DIR", "artifacts", "artifacts_dir"))
    notify_chat_id = get_config_value("TELEGRAM_NOTIFY_CHAT_ID", "", "telegram_notify_chat_id")

    missing = [
        name
        for name, value in {
            "TELEGRAM_API_ID": api_id_raw,
            "TELEGRAM_API_HASH": api_hash,
            "TELEGRAM_SESSION": session,
            "HDHIVE_BOT_USERNAME": bot_username,
        }.items()
        if not value
    ]
    if missing:
        raise CheckinError(f"缺少必要配置: {', '.join(missing)}")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise CheckinError("TELEGRAM_API_ID 必须是数字") from exc

    try:
        response_timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise CheckinError("TELEGRAM_RESPONSE_TIMEOUT_SECONDS 必须是数字") from exc

    return TelegramRuntimeConfig(
        api_id=api_id,
        api_hash=api_hash,
        session=session,
        bot_username=bot_username,
        command=command,
        response_timeout_seconds=max(1, response_timeout_seconds),
        artifacts_dir=artifacts_dir,
        notify_chat_id=notify_chat_id,
    )


async def run_telegram_checkin(config: TelegramRuntimeConfig) -> TelegramCheckinResult:
    if TelegramClient is None or StringSession is None:
        raise CheckinError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")

    started_at = datetime.now()
    log(f"准备向 {config.bot_username} 发送签到命令: {config.command}")

    client = TelegramClient(StringSession(config.session), config.api_id, config.api_hash)
    async with client:
        bot = await client.get_entity(config.bot_username)
        async with client.conversation(bot, timeout=config.response_timeout_seconds, exclusive=False) as conv:
            await conv.send_message(config.command)
            log("签到命令已发送，等待机器人回复...")
            reply = await conv.get_response()

        reply_text = getattr(reply, "raw_text", "") or getattr(reply, "message", "") or ""
        result = parse_bot_reply(reply_text, command=config.command)
        result.elapsed_seconds = (datetime.now() - started_at).total_seconds()
        log(f"机器人回复: {result.description}")

        if config.notify_chat_id:
            await client.send_message(config.notify_chat_id, build_summary_message(result), parse_mode="html")
            log(f"已发送结果通知到 Telegram Chat: {config.notify_chat_id}")

        return result


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


def write_outputs(result: TelegramCheckinResult, artifacts_dir: Path) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifacts_dir / "latest-results.json"
    result_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"任务结果已保存至: {result_path}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if summary_path:
        Path(summary_path).write_text(build_markdown_summary(result), encoding="utf-8")


def build_markdown_summary(result: TelegramCheckinResult) -> str:
    points = "" if result.points is None else str(result.points)
    return (
        "# HDHive Telegram Check-in\n\n"
        f"- Command: `{result.command}`\n"
        f"- Status: `{result.status}`\n"
        f"- Already signed: `{result.already_signed}`\n"
        f"- Points: `{points}`\n"
        f"- Result: {result.description}\n"
    )


async def async_main() -> int:
    try:
        config = load_runtime_config()
        result = await run_telegram_checkin(config)
        write_outputs(result, config.artifacts_dir)
    except asyncio.TimeoutError:
        config = load_runtime_config()
        result = TelegramCheckinResult(
            command=config.command,
            status="unknown",
            response_success=None,
            message="等待机器人回复超时",
            description=f"超过 {config.response_timeout_seconds:g} 秒未收到机器人回复",
            result_source="telegram_bot",
        )
        write_outputs(result, config.artifacts_dir)
        log(result.description)
        return 1
    except CheckinError as exc:
        log(f"配置或执行错误: {exc}")
        return 1

    return 0 if result.status == "success" else 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
