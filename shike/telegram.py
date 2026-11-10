from __future__ import annotations

import asyncio
import base64
import io
import secrets
import time
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable

import socks
from telethon import TelegramClient, events
from telethon.errors import (
    AuthKeyDuplicatedError, AuthKeyUnregisteredError, FloodWaitError,
    PasswordHashInvalidError, PhoneCodeExpiredError, PhoneCodeInvalidError,
    PhoneNumberInvalidError, SessionPasswordNeededError, SessionRevokedError,
)
from telethon.sessions import StringSession
from telethon.tl import types

from .database import Database
from .errors import AppError
from .security import Vault
from .rendering import render_message


AUTH_ERRORS = (AuthKeyDuplicatedError, AuthKeyUnregisteredError, SessionRevokedError)


def supported_button(button) -> bool:
    # Telegram changed keyboard constructors in newer layers. Whitelist both
    # layouts; URL, phone, location and inline-switch actions remain unsupported.
    if hasattr(button, "type"):
        safe = tuple(getattr(types, name) for name in ("ButtonTypeDefault", "InlineButtonTypeCallback") if hasattr(types, name))
        return isinstance(button.type, safe)
    safe = tuple(getattr(types, name) for name in ("KeyboardButtonCallback", "KeyboardButton") if hasattr(types, name))
    return isinstance(button, safe)


def telegram_error(exc: Exception) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, FloodWaitError):
        return AppError("TELEGRAM_FLOOD_WAIT", "Telegram 要求稍后重试，请等待限流结束。", 429, retryAfter=max(1, exc.seconds))
    if isinstance(exc, AUTH_ERRORS):
        return AppError("SESSION_INVALID", "Telegram 登录会话已失效，请重新登录。", 409)
    if isinstance(exc, PhoneCodeInvalidError):
        return AppError("CODE_INVALID", "验证码不正确，请输入最新收到的验证码。")
    if isinstance(exc, PhoneCodeExpiredError):
        return AppError("CODE_EXPIRED", "验证码已过期，请重新发起登录。")
    if isinstance(exc, PasswordHashInvalidError):
        return AppError("PASSWORD_INVALID", "两步验证密码不正确。")
    if isinstance(exc, PhoneNumberInvalidError):
        return AppError("PHONE_INVALID", "手机号无效，请检查国家区号和号码。")
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return AppError("TELEGRAM_NETWORK", "连接 Telegram 超时或网络不可用，请检查服务器网络与代理设置。", 503)
    # Do not return RPC exception strings: they may include request or account data.
    return AppError("TELEGRAM_ERROR", "Telegram 操作未完成，请检查账号状态、目标权限和任务步骤。", 502)


@dataclass
class PendingLogin:
    client: object
    owner: str
    name: str
    phone: str
    code_hash: str
    expires: float
    account_id: str | None
    needs_password: bool = False
    qr: object | None = None
    qr_task: asyncio.Task | None = None
    qr_image: str = ""
    qr_error: AppError | None = None


class TelegramService:
    def __init__(self, db: Database, vault: Vault, client_factory: Callable | None = None):
        self.db, self.vault = db, vault
        self.factory = client_factory or self._real_client
        self.clients: dict[str, object] = {}
        self.last_used: dict[str, float] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.pending: dict[str, PendingLogin] = {}
        self.login_locks: dict[str, asyncio.Lock] = {}
        self.completed: dict[str, tuple[str, dict, float]] = {}

    def _real_client(self, session, api_id, api_hash, proxy):
        return TelegramClient(
            StringSession(session), api_id, api_hash, proxy=proxy,
            timeout=12, connection_retries=1, request_retries=0,
            flood_sleep_threshold=0, device_model="Shike Self-hosted",
            app_version="0.1.0", sequential_updates=True,
        )

    def proxy(self):
        settings = self.db.get("settings")
        if settings["proxyType"] == "none":
            return None
        return (socks.SOCKS5 if settings["proxyType"] == "socks5" else socks.HTTP,
                settings["proxyHost"], int(settings["proxyPort"]), True)

    def credentials(self):
        encrypted = self.db.get("telegram_credentials")
        if not encrypted:
            raise AppError("API_NOT_CONFIGURED", "请先在设置中配置 Telegram API ID 和 API Hash。", 409)
        import json
        return json.loads(self.vault.decrypt(encrypted))

    def make_client(self, session=""):
        creds = self.credentials()
        try:
            return self.factory(session, creds["apiId"], creds["apiHash"], self.proxy())
        except (ValueError, TypeError):
            raise AppError("SESSION_FORMAT_INVALID", "登录会话格式无效，请使用 Telethon StringSession。") from None

    def lock(self, account_id):
        return self.locks.setdefault(account_id, asyncio.Lock())

    async def start_login(self, owner, name, phone, account_id=None):
        await self.cleanup_logins()
        if len(self.pending) >= 5 or sum(p.owner == owner for p in self.pending.values()) >= 2:
            raise AppError("LOGIN_LIMIT", "已有登录流程等待完成，请先完成或取消。", 429)
        if account_id:
            self.db.account(account_id)
        client = self.make_client()
        try:
            await asyncio.wait_for(client.connect(), 20)
            sent = await asyncio.wait_for(client.send_code_request(phone.replace(" ", "")), 30)
            login_id = secrets.token_urlsafe(24)
            self.pending[login_id] = PendingLogin(client, owner, name.strip(), phone.replace(" ", ""), sent.phone_code_hash, time.time() + 600, account_id)
            return {"loginId": login_id, "step": "code", "expiresIn": 600}
        except Exception as exc:
            await client.disconnect()
            raise telegram_error(exc) from None

    @staticmethod
    def qr_image(qr):
        import qrcode
        image = qrcode.make(qr.url, border=4)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()

    async def start_qr(self, owner, name, account_id=None):
        await self.cleanup_logins()
        if not name.strip():
            raise AppError("NAME_REQUIRED", "请填写账号名称。")
        if len(self.pending) >= 5 or sum(p.owner == owner for p in self.pending.values()) >= 2:
            raise AppError("LOGIN_LIMIT", "请先完成或取消已有登录流程。", 429)
        if account_id:
            self.db.account(account_id)
        client = self.make_client()
        try:
            await asyncio.wait_for(client.connect(), 20)
            qr = await asyncio.wait_for(client.qr_login(), 30)
            login_id = secrets.token_urlsafe(24)
            pending = PendingLogin(client, owner, name.strip(), "", "", time.time() + 600, account_id, qr=qr)
            pending.qr_image = self.qr_image(qr)
            self.pending[login_id] = pending
            pending.qr_task = asyncio.create_task(self.wait_qr(login_id, pending))
            await asyncio.sleep(0)  # Register Telegram's wait handler before exposing the QR.
            return self.login_status(owner, login_id)
        except Exception as exc:
            await client.disconnect()
            raise telegram_error(exc) from None

    def login_status(self, owner, login_id):
        if completed := self.completed.get(login_id):
            if completed[0] == owner and completed[2] > time.time():
                return {"step": "complete", "account": completed[1]}
        pending = self.pending_login(login_id, owner)
        if pending.qr_error:
            return {"step": "error", "message": pending.qr_error.message, "code": pending.qr_error.code}
        if pending.needs_password:
            return {"step": "password", "loginId": login_id}
        if pending.qr is None:
            return {"step": "code", "loginId": login_id}
        return {"step": "qr", "loginId": login_id, "qrImage": pending.qr_image, "expiresAt": pending.qr.expires.isoformat()}

    async def wait_qr(self, login_id, pending):
        try:
            while pending.expires > time.time():
                remaining = min(pending.expires - time.time(), max(1, pending.qr.expires.timestamp() - time.time()))
                try:
                    await pending.qr.wait(timeout=remaining)
                except asyncio.TimeoutError:
                    await asyncio.wait_for(pending.qr.recreate(), 30)
                    pending.qr_image = self.qr_image(pending.qr)
                    continue
                except SessionPasswordNeededError:
                    pending.needs_password = True
                    return
                async with self.login_locks.setdefault(login_id, asyncio.Lock()):
                    if login_id in self.pending:
                        await self.finish_login(login_id, pending)
                return
        except asyncio.CancelledError:
            return
        except Exception as exc:
            pending.qr_error = telegram_error(exc)

    def pending_login(self, login_id, owner):
        pending = self.pending.get(login_id)
        if not pending or pending.owner != owner or pending.expires < time.time():
            raise AppError("LOGIN_EXPIRED", "登录流程已过期或服务已重启，请重新获取验证码。", 410)
        return pending

    async def submit_code(self, owner, login_id, code):
        async with self.login_locks.setdefault(login_id, asyncio.Lock()):
            pending = self.pending_login(login_id, owner)
            if pending.qr is not None:
                raise AppError("LOGIN_STEP_INVALID", "扫码登录不使用短信验证码，请扫描二维码。", 409)
            try:
                await asyncio.wait_for(pending.client.sign_in(phone=pending.phone, code=code, phone_code_hash=pending.code_hash), 30)
                return await self.finish_login(login_id, pending)
            except SessionPasswordNeededError:
                pending.needs_password = True
                return {"loginId": login_id, "step": "password"}
            except Exception as exc:
                raise telegram_error(exc) from None

    async def submit_password(self, owner, login_id, password):
        async with self.login_locks.setdefault(login_id, asyncio.Lock()):
            pending = self.pending_login(login_id, owner)
            if not pending.needs_password:
                raise AppError("LOGIN_STEP_INVALID", "请先完成验证码验证。", 409)
            try:
                await asyncio.wait_for(pending.client.sign_in(password=password), 30)
                return await self.finish_login(login_id, pending)
            except Exception as exc:
                raise telegram_error(exc) from None

    async def finish_login(self, login_id, pending):
        account = await self.persist_account(pending.client, pending.name, pending.account_id)
        self.completed[login_id] = (pending.owner, account, time.time() + 60)
        self.pending.pop(login_id, None)
        await pending.client.disconnect()
        self.login_locks.pop(login_id, None)
        await self.close_account(account["id"])
        return {"step": "complete", "account": account}

    async def import_session(self, name, session, account_id=None):
        client = self.make_client(session.strip())
        try:
            await asyncio.wait_for(client.connect(), 20)
            if not await asyncio.wait_for(client.is_user_authorized(), 15):
                raise AppError("SESSION_INVALID", "该登录会话尚未授权或已失效。", 409)
            account = await self.persist_account(client, name, account_id)
            await self.close_account(account["id"])
            return account
        except Exception as exc:
            raise telegram_error(exc) from None
        finally:
            await client.disconnect()

    async def persist_account(self, client, name, account_id):
        me = await asyncio.wait_for(client.get_me(), 15)
        if not me or getattr(me, "bot", False):
            raise AppError("USER_ACCOUNT_REQUIRED", "请接入 Telegram 用户账号，机器人 Token 仅用于可选通知。")
        session = client.session.save()
        if not session:
            raise AppError("SESSION_EMPTY", "Telegram 未返回有效登录会话，请重新登录。")
        phone = getattr(me, "phone", "") or ""
        profile = {"username": getattr(me, "username", "") or "", "phone": ("+" + phone[:2] + " ···· " + phone[-4:]) if phone else "已隐藏", "letter": (getattr(me, "first_name", "") or name or "A")[0].upper()}
        return self.db.save_account(name, me.id, profile, self.vault.encrypt(session), account_id)

    @asynccontextmanager
    async def account_client(self, account_id):
        async with self.lock(account_id):
            account = self.db.account(account_id, private=True)
            if account["blockedUntilEpoch"] > time.time():
                raise AppError("TELEGRAM_FLOOD_WAIT", "Telegram 要求等待，请在限流结束后执行。", 429, retryAfter=int(account["blockedUntilEpoch"] - time.time()) + 1)
            client = self.clients.get(account_id)
            if client is not None and time.monotonic() - self.last_used.get(account_id, 0) > 45:
                # Reconnect before any side effect after an idle interval. Some
                # proxies silently drop sockets while is_connected stays true.
                self.clients.pop(account_id, None)
                self.last_used.pop(account_id, None)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 5)
                client = None
            if client is None:
                client = self.make_client(self.vault.decrypt(account["sessionCipher"]))
                self.clients[account_id] = client
            try:
                if not client.is_connected():
                    await asyncio.wait_for(client.connect(), 20)
                if not await asyncio.wait_for(client.is_user_authorized(), 15):
                    raise AppError("SESSION_INVALID", "登录会话已失效，请重新登录账号。", 409)
                self.db.account_status(account_id, "connected", 0)
                yield client
            except Exception as exc:
                error = telegram_error(exc)
                if error.code == "SESSION_INVALID":
                    self.db.account_status(account_id, "invalid")
                if error.code == "TELEGRAM_FLOOD_WAIT":
                    self.db.account_status(account_id, "limited", time.time() + error.details.get("retryAfter", 60))
                if error.code == "TELEGRAM_NETWORK":
                    # Discard the transport, never replay the failed operation.
                    self.clients.pop(account_id, None)
                    self.last_used.pop(account_id, None)
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(client.disconnect(), 5)
                raise error from None
            finally:
                if self.clients.get(account_id) is client:
                    self.last_used[account_id] = time.monotonic()

    async def check(self, account_id):
        async with self.account_client(account_id) as client:
            await asyncio.wait_for(client.get_me(), 15)
        return self.db.account(account_id)

    @staticmethod
    def entity_info(entity, target):
        is_user = isinstance(entity, types.User)
        kind = "self" if target == "me" else "bot" if getattr(entity, "bot", False) else "user" if is_user else "channel" if getattr(entity, "broadcast", False) else "group"
        name = getattr(entity, "title", None) or " ".join(filter(None, [getattr(entity, "first_name", ""), getattr(entity, "last_name", "")])) or str(target)
        if kind == "self":
            name = "发给自己（Telegram 收藏夹）"
        if getattr(entity, "left", False) or getattr(entity, "kicked", False):
            raise AppError("TARGET_NO_ACCESS", "当前账号已离开或无法访问这个会话。")
        if kind == "channel" and not (getattr(entity, "creator", False) or getattr(getattr(entity, "admin_rights", None), "post_messages", False)):
            raise AppError("TARGET_READ_ONLY", "当前账号没有在这个频道发布消息的权限。")
        return {"target": str(target), "targetName": name, "targetType": kind}

    async def resolve(self, account_id, target):
        async with self.account_client(account_id) as client:
            try:
                entity = await asyncio.wait_for(client.get_entity(int(target) if target.lstrip("-").isdigit() else target), 20)
            except ValueError:
                # StringSession does not persist entity access hashes; refresh recent dialogs.
                async for _ in client.iter_dialogs(limit=100):
                    pass
                try:
                    entity = await asyncio.wait_for(client.get_entity(int(target) if target.lstrip("-").isdigit() else target), 20)
                except ValueError:
                    raise AppError("TARGET_NOT_FOUND", "无法找到这个会话。请先在 Telegram 打开它，或从最近会话选择。") from None
            return self.entity_info(entity, target)

    async def dialogs(self, account_id, search=""):
        async with self.account_client(account_id) as client:
            result = [{"id": "me", "name": "收藏夹", "type": "self", "sub": "Saved Messages", "icon": "book"}]
            async for dialog in client.iter_dialogs(limit=100):
                entity = dialog.entity
                username = getattr(entity, "username", None)
                target = "@" + username if username else str(dialog.id)
                if search and search.lower() not in (dialog.name + " " + target).lower():
                    continue
                kind = "bot" if getattr(entity, "bot", False) else "user" if dialog.is_user else "group" if dialog.is_group else "channel"
                result.append({"id": target, "name": dialog.name, "type": kind, "sub": target, "icon": "bot" if kind == "bot" else "users" if kind == "group" else "user" if kind == "user" else "send"})
            return result

    async def execute(self, task, run_id):
        account_id = task["accountId"]
        async with self.account_client(account_id) as client:
            self.db.log(run_id, "执行账号已连接")
            try:
                entity = await asyncio.wait_for(client.get_entity(int(task["target"]) if task["target"].lstrip("-").isdigit() else task["target"]), 20)
            except ValueError:
                async for _ in client.iter_dialogs(limit=100):
                    pass
                entity = await client.get_entity(int(task["target"]) if task["target"].lstrip("-").isdigit() else task["target"])
            info = self.entity_info(entity, task["target"])
            private = info["targetType"] in ("bot", "user", "self")
            queue: asyncio.Queue = asyncio.Queue(maxsize=100)
            seq, cursor, last_sent, last_reply = 0, 0, None, None
            replies, sent_texts, sent_messages = [], [], []
            execution_time = time.time()

            async def receive(event):
                nonlocal seq
                msg = event.message
                if getattr(msg, "out", False):
                    return
                seq += 1
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait((seq, msg))

            builders = [events.NewMessage(chats=entity, incoming=True), events.MessageEdited(chats=entity, incoming=True)]
            for builder in builders:
                client.add_event_handler(receive, builder)
            try:
                for index, step in enumerate(task["steps"]):
                    self.db.log(run_id, {"send": "准备发送消息", "wait": f"等待目标回复（最多 {step.get('seconds', 60)} 秒）", "click": "查找当前回复中的按钮", "delay": "间隔等待"}[step["type"]], step=index + 1, state="running")
                    if step["type"] == "send":
                        cursor = seq
                        rendered = render_message(step["text"], task, execution_time)
                        if len(rendered) > 4096:
                            raise AppError("MESSAGE_TOO_LONG", "替换日期变量后消息超过 4096 个字符，请缩短内容。")
                        sent_texts.append(rendered)
                        self.db.update_run(run_id, sendState="unknown", message="\n\n".join(sent_texts))
                        last_sent = await asyncio.wait_for(client.send_message(entity, rendered, parse_mode=None, link_preview=False), 30)
                        sent_messages.append({"messageId":last_sent.id,"text":rendered})
                        self.db.update_run(run_id, sent=True, sendState="sent", sentMessages=sent_messages)
                        last_reply = None
                    elif step["type"] == "delay":
                        await asyncio.sleep(step["seconds"])
                    elif step["type"] == "wait":
                        deadline = asyncio.get_running_loop().time() + step["seconds"]
                        timeout_message = "消息已发送，但在设定时间内未收到回复。若只需发消息，请移除“等待回复”步骤；本次不会自动重发。"
                        while True:
                            remaining = deadline - asyncio.get_running_loop().time()
                            if remaining <= 0:
                                raise AppError("REPLY_TIMEOUT", timeout_message)
                            try:
                                event_seq, message = await asyncio.wait_for(queue.get(), remaining)
                            except asyncio.TimeoutError:
                                raise AppError("REPLY_TIMEOUT", timeout_message) from None
                            if event_seq <= cursor or last_sent is None:
                                continue
                            reply_to = getattr(message, "reply_to_msg_id", None)
                            if not private and reply_to != last_sent.id:
                                continue
                            if private and reply_to and reply_to != last_sent.id:
                                continue
                            if message.id < last_sent.id and (last_reply is None or message.id != last_reply.id):
                                continue
                            last_reply, cursor = message, event_seq
                            raw = getattr(message, "raw_text", None) or getattr(message, "message", "") or ""
                            replies.append({"text": raw, "hasMedia": bool(getattr(message, "media", None)), "messageId": message.id})
                            self.db.update_run(run_id, sendState="sent", replies=replies[-50:], reply="\n\n".join(r["text"] or "[非文本消息]" for r in replies[-50:]))
                            break
                    elif step["type"] == "click":
                        if last_reply is None:
                            raise AppError("BUTTON_NO_MESSAGE", "没有收到可供点击按钮的当前回复。")
                        matches = [(i, j, button) for i, row in enumerate(last_reply.buttons or []) for j, button in enumerate(row) if button.text == step["text"]]
                        if len(matches) != 1:
                            raise AppError("BUTTON_NOT_UNIQUE", "没有找到唯一匹配的按钮，请检查本次回复和按钮文字。")
                        i, j, button = matches[0]
                        if not supported_button(button.button):
                            raise AppError("BUTTON_UNSUPPORTED", "仅支持回调或普通文字按钮，不自动打开链接或提交联系人与位置。")
                        cursor = seq
                        self.db.update_run(run_id, sendState="unknown")
                        clicked = await asyncio.wait_for(last_reply.click(i, j), 30)
                        if hasattr(clicked, "id"):
                            last_sent = clicked
                        self.db.update_run(run_id, sent=True, sendState="sent" if clicked is not None else "unknown")
                    self.db.log(run_id, "消息已发送" if step["type"] == "send" else "步骤已完成", step=index + 1, state="done")
            finally:
                for builder in builders:
                    client.remove_event_handler(receive, builder)

    async def cancel_login(self, owner, login_id):
        pending = self.pending.get(login_id)
        if pending and pending.owner == owner and pending.qr_task and not pending.qr_task.done():
            pending.qr_task.cancel()
            await asyncio.gather(pending.qr_task, return_exceptions=True)
        async with self.login_locks.setdefault(login_id, asyncio.Lock()):
            pending = self.pending.get(login_id)
            if pending and pending.owner == owner:
                self.pending.pop(login_id, None)
                await pending.client.disconnect()
        self.login_locks.pop(login_id, None)

    async def cleanup_logins(self):
        self.completed = {key: value for key, value in self.completed.items() if value[2] > time.time()}
        for key, pending in list(self.pending.items()):
            if pending.expires < time.time() and not self.login_locks.get(key, asyncio.Lock()).locked():
                await self.cancel_login(pending.owner, key)

    async def close_account(self, account_id):
        async with self.lock(account_id):
            client = self.clients.pop(account_id, None)
            self.last_used.pop(account_id, None)
            if client:
                await client.disconnect()

    async def close(self):
        for pending in list(self.pending.values()):
            if pending.qr_task:
                pending.qr_task.cancel()
        await asyncio.gather(*(p.qr_task for p in self.pending.values() if p.qr_task), return_exceptions=True)
        for pending in list(self.pending.values()):
            await pending.client.disconnect()
        self.pending.clear()
        for client in list(self.clients.values()):
            await client.disconnect()
        self.clients.clear()
        self.last_used.clear()
