from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .errors import AppError
from .models import SettingsInput


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def iso(timestamp: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if timestamp is None else timestamp, UTC).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts (scope TEXT NOT NULL, ip TEXT NOT NULL, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_at ON attempts(scope, ip, at);
CREATE TABLE IF NOT EXISTS accounts (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT UNIQUE NOT NULL,
 profile TEXT NOT NULL, session_cipher TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'connected', blocked_until REAL NOT NULL DEFAULT 0,
 created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
 config TEXT NOT NULL, enabled INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 next_at REAL, due_at REAL, created REAL NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(enabled, due_at);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL, account_id TEXT,
 snapshot TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
 scheduled_at REAL, idempotency TEXT, created REAL NOT NULL,
 started REAL, finished REAL, result TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS run_active ON runs(task_id) WHERE status IN ('queued','running');
CREATE UNIQUE INDEX IF NOT EXISTS run_idempotency ON runs(task_id,idempotency) WHERE idempotency IS NOT NULL;
CREATE INDEX IF NOT EXISTS runs_created ON runs(created DESC);
CREATE INDEX IF NOT EXISTS runs_task ON runs(task_id,created DESC);
PRAGMA user_version=1;
"""


class Database:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "shike.db"
        with self.tx() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("数据库版本较新，不能使用旧版服务打开。")
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('settings',?)", (json.dumps(SettingsInput().model_dump()),))
        os.chmod(self.path, 0o600)

    @contextmanager
    def tx(self, immediate: bool = False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            if immediate:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, key: str, default=None, *, connection=None):
        if connection is not None:
            row = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default
        with self.tx() as db:
            return self.get(key, default, connection=db)

    def set(self, key, value, *, connection=None):
        if connection is not None:
            connection.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, ensure_ascii=False)))
        else:
            with self.tx() as db:
                self.set(key, value, connection=db)

    def rate_limit(self, scope: str, ip: str, *, limit=8, window=900):
        now = time.time()
        with self.tx(True) as db:
            db.execute("DELETE FROM attempts WHERE at<?", (now - 3600,))
            n = db.execute("SELECT COUNT(*) FROM attempts WHERE scope=? AND ip=? AND at>?", (scope, ip, now - window)).fetchone()[0]
            if n >= limit:
                raise AppError("RATE_LIMITED", "请求过于频繁，请稍后再试。", 429)
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (scope, ip, now))

    def accounts(self, private=False):
        with self.tx() as db:
            return [self.account_row(r, private) for r in db.execute("SELECT * FROM accounts ORDER BY created")]

    def account_row(self, row, private=False):
        out = {**json.loads(row["profile"]), "id": row["id"], "name": row["name"], "status": row["status"], "blockedUntil": iso(row["blocked_until"]) if row["blocked_until"] else None}
        if private:
            out.update(sessionCipher=row["session_cipher"], userId=row["user_id"], blockedUntilEpoch=row["blocked_until"])
        return out

    def account(self, account_id, private=False):
        with self.tx() as db:
            row = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                raise AppError("ACCOUNT_NOT_FOUND", "账号不存在或已移除。", 404)
            return self.account_row(row, private)

    def save_account(self, name, user_id, profile, encrypted_session, account_id=None):
        with self.tx(True) as db:
            existing = db.execute("SELECT * FROM accounts WHERE user_id=?", (str(user_id),)).fetchone()
            if account_id:
                target = db.execute("SELECT user_id FROM accounts WHERE id=?", (account_id,)).fetchone()
                if not target:
                    raise AppError("ACCOUNT_NOT_FOUND", "需要重新登录的账号已被移除。", 404)
                if str(user_id) != target[0]:
                    raise AppError("ACCOUNT_MISMATCH", "登录的 Telegram 身份与原账号不一致，请单独添加新账号。", 409)
            elif existing:
                raise AppError("ACCOUNT_EXISTS", "这个 Telegram 账号已经接入，请使用重新登录。", 409)
            account_id = account_id or new_id("account")
            db.execute("""INSERT INTO accounts VALUES (?,?,?,?,?,'connected',0,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, profile=excluded.profile,
                session_cipher=excluded.session_cipher,status='connected',blocked_until=0""",
                (account_id, name.strip(), str(user_id), json.dumps(profile, ensure_ascii=False), encrypted_session, time.time()))
        return self.account(account_id)

    def rename_account(self, account_id: str, name: str):
        with self.tx(True) as db:
            if db.execute("UPDATE accounts SET name=? WHERE id=?", (name, account_id)).rowcount == 0:
                raise AppError("ACCOUNT_NOT_FOUND", "账号不存在或已移除。", 404)
            return self.account_row(db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())

    def account_status(self, account_id, status, blocked_until=None):
        with self.tx() as db:
            if blocked_until is None:
                db.execute("UPDATE accounts SET status=? WHERE id=?", (status, account_id))
            else:
                db.execute("UPDATE accounts SET status=?,blocked_until=? WHERE id=?", (status, blocked_until, account_id))

    def remove_account(self, account_id):
        with self.tx(True) as db:
            if db.execute("SELECT 1 FROM runs WHERE account_id=? AND status IN ('queued','running')", (account_id,)).fetchone():
                raise AppError("ACCOUNT_BUSY", "这个账号还有任务执行中，请等待结束或取消任务后再移除。", 409)
            for row in db.execute("SELECT id,config FROM tasks WHERE account_id=?", (account_id,)).fetchall():
                config = json.loads(row["config"])
                config.update(accountId="", enabled=False)
                db.execute("UPDATE tasks SET account_id=NULL,config=?,enabled=0,next_at=NULL,due_at=NULL,revision=revision+1 WHERE id=?", (json.dumps(config, ensure_ascii=False), row["id"]))
            db.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    def task_row(self, row):
        return {**json.loads(row["config"]), "id": row["id"], "enabled": bool(row["enabled"]), "revision": row["revision"], "nextRunAt": iso(row["due_at"]) if row["due_at"] else None, "createdAt": iso(row["created"]), "nextScheduledAt": iso(row["next_at"]) if row["next_at"] else None}

    def tasks(self):
        with self.tx() as db:
            return [self.task_row(r) for r in db.execute("SELECT * FROM tasks ORDER BY created")]

    def task(self, task_id, *, connection=None):
        if connection is not None:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise AppError("TASK_NOT_FOUND", "任务不存在或已删除。", 404)
            return self.task_row(row)
        with self.tx() as db:
            return self.task(task_id, connection=db)

    def save_task(self, config, next_at, due_at, task_id=None):
        now = time.time()
        with self.tx(True) as db:
            if task_id:
                existing = self.task(task_id, connection=db)
                if config.get("revision") is not None and config["revision"] != existing["revision"]:
                    raise AppError("REVISION_CONFLICT", "任务已在其他页面修改，请刷新后重试。", 409)
                if db.execute("SELECT 1 FROM runs WHERE task_id=? AND status IN ('queued','running')", (task_id,)).fetchone():
                    raise AppError("TASK_BUSY", "任务仍在执行中，请结束后再修改配置。", 409)
                config = {k: v for k, v in config.items() if k != "revision"}
                db.execute("UPDATE tasks SET account_id=?,config=?,enabled=?,next_at=?,due_at=?,revision=revision+1,updated=? WHERE id=?", (config["accountId"] or None, json.dumps(config, ensure_ascii=False), config["enabled"], next_at, due_at, now, task_id))
            else:
                if db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] >= 500:
                    raise AppError("TASK_LIMIT", "当前实例最多支持 500 个任务。")
                task_id = new_id("task")
                config = {k: v for k, v in config.items() if k != "revision"}
                db.execute("INSERT INTO tasks VALUES (?,?,?,?,1,?,?,?,?)", (task_id, config["accountId"] or None, json.dumps(config, ensure_ascii=False), config["enabled"], next_at, due_at, now, now))
        return self.task(task_id)

    def remove_task(self, task_id):
        with self.tx(True) as db:
            self.task(task_id, connection=db)
            if db.execute("SELECT 1 FROM runs WHERE task_id=? AND status IN ('queued','running')", (task_id,)).fetchone():
                raise AppError("TASK_BUSY", "任务仍在执行中，请结束或取消后再删除。", 409)
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def run_row(self, row):
        task = json.loads(row["snapshot"])
        result = json.loads(row["result"])
        return {**result, "id": row["id"], "taskId": row["task_id"], "taskName": task["name"], "accountId": row["account_id"], "target": task["target"], "status": row["status"], "source": row["source"], "at": iso(row["created"]), "startedAt": iso(row["started"]) if row["started"] else None, "finishedAt": iso(row["finished"]) if row["finished"] else None, "scheduledAt": iso(row["scheduled_at"]) if row["scheduled_at"] else None}

    def runs(self, limit=200, offset=0):
        with self.tx() as db:
            rows = db.execute("SELECT * FROM runs ORDER BY created DESC,rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [self.run_row(r) for r in rows]

    def run(self, run_id, private=False):
        with self.tx() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise AppError("RUN_NOT_FOUND", "执行记录不存在。", 404)
            out = self.run_row(row)
            if private:
                out["snapshot"] = json.loads(row["snapshot"])
            return out

    def active_run(self, task_id):
        with self.tx() as db:
            row = db.execute("SELECT * FROM runs WHERE task_id=? AND status IN ('queued','running')", (task_id,)).fetchone()
            return self.run_row(row) if row else None

    def claim_run(self, task_id, source, key=None, *, connection=None, scheduled_at=None):
        if connection is None:
            with self.tx(True) as db:
                return self.claim_run(task_id, source, key, connection=db, scheduled_at=scheduled_at)
        db = connection
        task = self.task(task_id, connection=db)
        if key:
            prior = db.execute("SELECT * FROM runs WHERE task_id=? AND idempotency=?", (task_id, key)).fetchone()
            if prior:
                return self.run_row(prior), False
        if self.get("maintenance_until", 0, connection=db) > time.time():
            raise AppError("MAINTENANCE", "实例正在备份或升级，请稍后执行。", 409)
        active = db.execute("SELECT id FROM runs WHERE task_id=? AND status IN ('queued','running')", (task_id,)).fetchone()
        if active:
            raise AppError("RUN_EXISTS", "这个任务已经在执行或排队，请查看现有记录。", 409, runId=active[0])
        if db.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0] >= 100:
            raise AppError("QUEUE_FULL", "执行队列已满，请稍后重试。", 429)
        account = db.execute("SELECT name,status FROM accounts WHERE id=?", (task["accountId"],)).fetchone()
        if not account or account["status"] == "invalid":
            raise AppError("ACCOUNT_UNAVAILABLE", "执行前请先接入或重新登录账号。", 409)
        task["accountName"] = account["name"]
        run_id = new_id("run")
        initial = {"logs": [], "replies": [], "sent": False, "sendState": "not_sent", "businessStatus": "unknown", "message": " → ".join(s.get("text", "") for s in task["steps"] if s["type"] != "wait"), "reply": "", "duration": "排队中"}
        db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, task_id, task["accountId"], json.dumps(task, ensure_ascii=False), "queued", source, scheduled_at, key, time.time(), None, None, json.dumps(initial, ensure_ascii=False)))
        row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self.run_row(row), True

    def update_run(self, run_id, *, status=None, **fields):
        with self.tx(True) as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return
            result = json.loads(row["result"])
            result.update(fields)
            started = row["started"]
            finished = row["finished"]
            if status == "running" and started is None:
                started = time.time()
            if status and status not in ("queued", "running"):
                finished = time.time()
                result["duration"] = f"{max(0, finished - (started or row['created'])):.1f} 秒"
            db.execute("UPDATE runs SET result=?,status=?,started=?,finished=? WHERE id=?", (json.dumps(result, ensure_ascii=False), status or row["status"], started, finished, run_id))

    def log(self, run_id, message, *, step=None, state="info"):
        run = self.run(run_id)
        logs = run.get("logs", [])
        logs.append({"at": iso(), "message": message, "step": step, "state": state})
        self.update_run(run_id, logs=logs[-200:])

    def busy(self):
        with self.tx() as db:
            return bool(db.execute("SELECT 1 FROM runs WHERE status IN ('queued','running')").fetchone())

    def cleanup(self, retention):
        now = time.time()
        with self.tx() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute("DELETE FROM runs WHERE created<? AND status NOT IN ('queued','running')", (now - int(retention) * 86400,))
