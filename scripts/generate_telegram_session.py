#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import getpass
import sys

try:
    from telethon import TelegramClient
    from telethon.errors import (
        ApiIdInvalidError,
        FloodWaitError,
        PasswordHashInvalidError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        SessionPasswordNeededError,
    )
    from telethon.sessions import StringSession
except ImportError:  # pragma: no cover - depends on local environment
    TelegramClient = None  # type: ignore[assignment]
    StringSession = None  # type: ignore[assignment]
    ApiIdInvalidError = FloodWaitError = PasswordHashInvalidError = PhoneCodeExpiredError = None  # type: ignore[assignment]
    PhoneCodeInvalidError = PhoneNumberInvalidError = SessionPasswordNeededError = None  # type: ignore[assignment]


API_ID = 0
API_HASH = ""


def log(message: str) -> None:
    print(f"[session] {message}", flush=True)


def validate_api_credentials(api_id: int, api_hash: str) -> tuple[int, str]:
    if not api_id:
        raise RuntimeError("请先在 scripts/generate_telegram_session.py 中填写 API_ID")
    if not api_hash:
        raise RuntimeError("请先在 scripts/generate_telegram_session.py 中填写 API_HASH")
    return api_id, api_hash.strip()


def load_api_credentials() -> tuple[int, str]:
    return validate_api_credentials(API_ID, API_HASH)


def prompt_required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        log("输入不能为空，请重新输入。")


def build_session_output(session: str) -> str:
    return (
        "\nTELEGRAM_SESSION:\n"
        f"{session}\n\n"
        "请把上面的字符串保存到 GitHub Secrets 的 TELEGRAM_SESSION。\n"
        "这个字符串等同于 Telegram 登录凭证，不要提交到仓库，也不要发给别人。"
    )


def ensure_telethon_installed() -> None:
    if TelegramClient is None or StringSession is None:
        raise RuntimeError("未安装 telethon，请先执行: python -m pip install -r requirements.txt")


async def async_main() -> int:
    api_id, api_hash = load_api_credentials()
    ensure_telethon_installed()

    log("开始生成 Telethon StringSession。")
    log("验证码和二步验证密码只会发送给 Telegram，不会写入文件。")
    phone = prompt_required("Telegram 手机号（带国家区号，例如 +8613800000000）: ")

    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        log("正在连接 Telegram...")
        await client.connect()
        log("正在发送登录验证码...")
        await client.send_code_request(phone)
        code = prompt_required("Telegram 验证码: ")
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            log("账号开启了二步验证，需要输入 Two-Step Verification Password。")
            password = getpass.getpass("Telegram 二步验证密码: ")
            await client.sign_in(password=password)

        session = client.session.save()
        if not session:
            raise RuntimeError("Telegram 已登录，但未生成 session 字符串")

        log("Session 生成成功。")
        print(build_session_output(session))
    except PhoneNumberInvalidError as exc:
        raise RuntimeError("手机号格式无效，请确认包含国家区号，例如 +86...") from exc
    except PhoneCodeInvalidError as exc:
        raise RuntimeError("验证码无效，请重新运行脚本并输入最新验证码") from exc
    except PhoneCodeExpiredError as exc:
        raise RuntimeError("验证码已过期，请重新运行脚本获取新验证码") from exc
    except PasswordHashInvalidError as exc:
        raise RuntimeError("Telegram 二步验证密码错误，请确认后重新运行脚本") from exc
    except FloodWaitError as exc:
        seconds = getattr(exc, "seconds", 0)
        raise RuntimeError(f"请求过于频繁，Telegram 要求等待 {seconds} 秒后再试") from exc
    except ApiIdInvalidError as exc:
        raise RuntimeError("API_ID 或 API_HASH 无效，请检查 my.telegram.org 上的应用信息") from exc
    except Exception as exc:
        if "password" in exc.__class__.__name__.lower():
            try:
                log("账号开启了二步验证，需要输入 Two-Step Verification Password。")
                password = getpass.getpass("Telegram 二步验证密码: ")
                await client.sign_in(password=password)
                session = client.session.save()
                if not session:
                    raise RuntimeError("Telegram 已登录，但未生成 session 字符串")
                log("Session 生成成功。")
                print(build_session_output(session))
                return 0
            except Exception:
                raise
        raise
    finally:
        if client.is_connected():
            await client.disconnect()
            log("已断开 Telegram 连接。")

    return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except RuntimeError as exc:
        log(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
