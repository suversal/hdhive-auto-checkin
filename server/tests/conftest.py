from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from telethon import events
from telethon.errors import FloodWaitError, PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.tl import types

from shike.app import create_app
from shike.config import Config


class FakeMessage:
    def __init__(self, client, message_id, text, reply_to=None):
        self.client, self.id = client, message_id
        self.raw_text = self.message = text
        self.reply_to_msg_id, self.out, self.media = reply_to, False, None
        kind = types.ButtonTypeDefault() if client.factory.text_button else types.InlineButtonTypeCallback(b"fresh-current-data")
        self.buttons = [[SimpleNamespace(text="每日签到", button=types.KeyboardButton("每日签到", kind))]]

    async def click(self, i, j):
        self.client.factory.clicks += 1
        if self.client.factory.text_button:
            return await self.client.send_message("@testbot", "每日签到")
        edited = FakeMessage(self.client, self.id, "签到成功，获得 5 积分。", self.reply_to_msg_id)
        await self.client.emit(edited, edited=True)


class FakeClient:
    def __init__(self, factory, session, api_id, api_hash, proxy):
        self.factory, self.secret = factory, session or "test-session-from-code-with-no-network"
        self.session = SimpleNamespace(save=lambda: self.secret)
        self.authorized, self.connected, self.handlers = bool(session), False, []
        self.user_id = 2 if session.endswith("-2") else 1

    async def connect(self):
        if self.factory.mode == "network":
            raise ConnectionError("sensitive transport diagnostics must never be exposed")
        self.connected = True

    def is_connected(self):
        return self.connected

    async def disconnect(self):
        self.connected = False

    async def is_user_authorized(self):
        return self.authorized

    async def send_code_request(self, phone):
        return SimpleNamespace(phone_code_hash="test-private-code-hash")

    async def qr_login(self):
        return FakeQR(self)

    async def sign_in(self, **kwargs):
        if "code" in kwargs:
            if kwargs["code"] != "12345":
                raise PhoneCodeInvalidError(None)
            if self.factory.two_factor:
                raise SessionPasswordNeededError(None)
        self.authorized = True

    async def get_me(self):
        return types.User(id=self.user_id, first_name="测试账号", username="test_user", phone="8613800000000", bot=False)

    async def get_entity(self, target):
        if target == "me":
            return await self.get_me()
        if target == "@test_user":
            return types.User(id=998, first_name="测试用户", username="test_user", bot=False)
        if isinstance(target, int) and target < 0:
            return SimpleNamespace(id=abs(target), title="测试群组", broadcast=False, left=False)
        return types.User(id=999, first_name="测试机器人", username="testbot", bot=True)

    async def iter_dialogs(self, limit=100):
        yield SimpleNamespace(entity=await self.get_entity("@testbot"), name="测试机器人", id=999, is_user=True, is_group=False)

    def add_event_handler(self, handler, builder):
        self.handlers.append((handler, builder))

    def remove_event_handler(self, handler, builder):
        self.handlers = [(h, b) for h, b in self.handlers if h != handler or b is not builder]

    async def emit(self, message, edited=False):
        for handler, builder in list(self.handlers):
            if isinstance(builder, events.MessageEdited) == edited:
                await handler(SimpleNamespace(message=message))

    async def send_message(self, entity, text, **kwargs):
        if self.factory.mode == "flood":
            raise FloodWaitError(None, capture=12)
        if self.factory.mode == "uncertain":
            raise asyncio.TimeoutError("unknown send outcome")
        self.factory.sends.append((text, kwargs))
        self.factory.sequence += 2
        sent = SimpleNamespace(id=self.factory.sequence)
        if self.factory.mode != "timeout" and entity != "me":
            if self.factory.mode == "group":
                await self.emit(FakeMessage(self, sent.id + 1, "无关群消息不应被接受", -999))
            reply = FakeMessage(self, sent.id + 1, "签到成功，获得 5 积分。", sent.id)
            await self.emit(reply)
        return sent


class FakeFactory:
    def __init__(self):
        self.mode, self.two_factor = "normal", False
        self.sends, self.sequence, self.clicks = [], 10, 0
        self.qr_event = asyncio.Event()
        self.text_button = False

    def __call__(self, *args):
        return FakeClient(self, *args)


class FakeQR:
    def __init__(self, client):
        self.client = client
        self.expires = datetime.now(UTC) + timedelta(seconds=30)
        self.url = "tg://login?token=synthetic-unit-test-qr-not-a-real-token"

    async def wait(self, timeout=None):
        await asyncio.wait_for(self.client.factory.qr_event.wait(), timeout)
        if self.client.factory.two_factor:
            raise SessionPasswordNeededError(None)
        self.client.authorized = True
        return await self.client.get_me()

    async def recreate(self):
        self.expires = datetime.now(UTC) + timedelta(seconds=30)
        self.url += "-refreshed"


@pytest.fixture
def instance(tmp_path):
    factory = FakeFactory()
    config = Config(tmp_path / "data", scheduler_enabled=False)
    app = create_app(config, client_factory=factory)
    with TestClient(app) as client:
        yield SimpleNamespace(app=app, client=client, factory=factory, config=config)


def initialize(instance):
    from shike.admin import initialize_admin
    initialize_admin(instance.app.state.db, "test-admin-password", "测试空间")
    response = instance.client.post("/api/auth/login", json={"password": "test-admin-password"})
    assert response.status_code == 200, response.text
    instance.client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
    return response


@pytest.fixture
def ready(instance):
    initialize(instance)
    response = instance.client.put("/api/settings/telegram", json={"apiId": 12345, "apiHash": "a" * 32})
    assert response.status_code == 200, response.text
    response = instance.client.post("/api/accounts/import", json={"name": "主账号", "session": "test-session-imported-real-adapter-tests"})
    assert response.status_code == 201, response.text
    instance.account = response.json()
    return instance


def task_body(account_id, **overrides):
    return {"name": "测试签到", "accountId": account_id, "target": "@testbot", "steps": [{"type": "send", "text": "/checkin"}, {"type": "wait", "seconds": 1}], "notify": "none", **overrides}


def create_task(instance, **overrides):
    response = instance.client.post("/api/tasks", json=task_body(instance.account["id"], **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def await_run(instance, run_id):
    for _ in range(250):
        run = instance.client.get("/api/runs/" + run_id).json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(.01)
    raise AssertionError("run did not complete")
