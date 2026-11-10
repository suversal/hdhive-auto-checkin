"""Local browser integration fixture. Not copied into the production image.

Only synthetic test credentials are used. The UI explicitly labels this adapter
as an automated test environment. No Telegram connection or message is made.
"""
import argparse
import tempfile
import json
import time
from pathlib import Path

from conftest import FakeFactory
from shike.app import create_app
from shike.config import Config
from shike.database import Database
from shike.security import Vault, password_hash
from shike.models import TaskInput
from shike.scheduling import next_time


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", choices=("ready", "new", "uninitialized"), default="ready")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    data = Path(tempfile.mkdtemp(prefix="shike-ui-check-"))
    vault = Vault(data)
    db = Database(data)
    if args.state != "uninitialized":
        db.set("admin_password", password_hash("test-admin-password"))
        db.set("settings", {**db.get("settings"), "workspace": "自动化测试空间"})
    if args.state == "ready":
        db.set("telegram_credentials", vault.encrypt(json.dumps({"apiId":12345,"apiHash":"a"*32})))
        account = db.save_account("测试账号 A", 1, {"username":"sample_account","phone":"合成测试数据","letter":"S"}, vault.encrypt("test-session-imported"))
        for name, target in (("每日签到","@testbot"),("每周备忘","me"),("积分查询","@testbot")):
            task = TaskInput(name=name, accountId=account["id"], target=target, targetName="发给自己" if target=="me" else "测试机器人", targetType="self" if target=="me" else "bot", steps=[{"type":"send","text":"测试消息"}], notify="none").model_dump(exclude={"revision"})
            following = next_time(task, time.time())
            db.save_task(task, following, following)
    app = create_app(Config(data, scheduler_interval=.2), client_factory=FakeFactory())
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
