#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"请先设置环境变量 {name}")
    return value


async def async_main() -> int:
    api_id = int(require_env("TELEGRAM_API_ID"))
    api_hash = require_env("TELEGRAM_API_HASH")
    phone = input("Telegram phone number: ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        await client.send_code_request(phone)
        code = input("Login code: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as exc:
            if "password" not in exc.__class__.__name__.lower():
                raise
            password = getpass.getpass("Two-step password: ")
            await client.sign_in(password=password)

        print("\nTELEGRAM_SESSION:")
        print(client.session.save())
        print("\n请把上面的字符串保存到 GitHub Secrets，不要提交到仓库。")
    finally:
        await client.disconnect()

    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
