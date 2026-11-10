from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .database import Database, iso, new_id
from .errors import AppError
from .scheduling import next_time
from .telegram import TelegramService, telegram_error


FINAL_ERRORS = {"timeout", "error", "failed", "interrupted", "limited"}
RESULT_LABELS = {
    "queued": "排队中", "running": "执行中", "sent": "已发送",
    "replied": "已收到回复", "success": "匹配成功规则", "failed": "匹配失败规则",
    "timeout": "已发送 · 未等到回复", "error": "执行异常", "interrupted": "执行中断",
    "limited": "限流等待", "cancelled": "已取消", "skipped": "已跳过",
}


def classify_result(task: dict, run: dict) -> tuple[str, str, str | None]:
    if next(s["type"] for s in reversed(task["steps"]) if s["type"] != "delay") != "wait":
        return "sent", "unknown", None
    text = run.get("replies", [{}])[-1].get("text", "") if run.get("replies") else ""
    for field, status in (("failureWords", "failed"), ("successWords", "success")):
        words = [v.strip() for v in task[field].replace("，", ",").split(",") if v.strip()]
        matched = next((word for word in words if word in text), None)
        if matched:
            return status, status, matched
    return "replied", "unknown", None


class Runner:
    def __init__(self, db: Database, telegram: TelegramService, clock=time.time):
        self.db, self.telegram, self.clock = db, telegram, clock
        self.jobs: dict[str, asyncio.Task] = {}
        self.account_locks: dict[str, asyncio.Lock] = {}
        self.stopping = False
        self.last_cleanup = 0.0
        self.summary_job = None

    @staticmethod
    def due(nominal, task):
        return nominal + random.SystemRandom().uniform(0, task["jitter"] * 60) if nominal is not None else None

    def launch(self, run):
        run_id = run["id"]
        if run_id in self.jobs:
            return
        job = asyncio.create_task(self.execute(run_id), name="shike-run-" + run_id)
        self.jobs[run_id] = job
        job.add_done_callback(lambda completed: self.jobs.pop(run_id, None))

    def enqueue(self, task_id, key=None):
        task = self.db.task(task_id)
        account = self.db.account(task["accountId"], private=True)
        if account["blockedUntilEpoch"] > self.clock():
            raise AppError("TELEGRAM_FLOOD_WAIT", "账号仍处于 Telegram 限流等待中，请稍后执行。", 429, retryAfter=int(account["blockedUntilEpoch"] - self.clock()) + 1)
        run, created = self.db.claim_run(task_id, "manual", key)
        if created:
            self.launch(run)
        return run

    async def execute(self, run_id):
        run = self.db.run(run_id, private=True)
        task = run["snapshot"]
        try:
            lock = self.account_locks.setdefault(task["accountId"], asyncio.Lock())
            async with lock:
                self.db.update_run(run_id, status="running", duration="执行中")
                await asyncio.wait_for(self.telegram.execute(task, run_id), 2100)
                status, business, matched = classify_result(task, self.db.run(run_id))
                fields = {"businessStatus": business, "matchedRule": matched}
                self.db.update_run(run_id, status=status, **fields)
        except asyncio.CancelledError:
            self.db.update_run(run_id, status="interrupted" if self.stopping else "cancelled", errorCode="SERVICE_STOPPED" if self.stopping else "CANCELLED", error="服务停止，本次执行不自动重放。" if self.stopping else "用户已取消，已发送的消息无法撤回。")
            return
        except Exception as exc:
            error = telegram_error(exc)
            status = "timeout" if error.code == "REPLY_TIMEOUT" else "limited" if error.code == "TELEGRAM_FLOOD_WAIT" else "error"
            self.db.update_run(run_id, status=status, error=error.message, errorCode=error.code, retryAfter=error.details.get("retryAfter"))
            self.db.log(run_id, error.message, state="error")
        if not self.stopping:
            try:
                await self.notify_run(task, run_id)
            except Exception:
                # Notification errors never turn a successful business task into a retry.
                self.db.update_run(run_id, notificationStatus="failed")

    async def cancel(self, run_id):
        run = self.db.run(run_id)
        job = self.jobs.get(run_id)
        if job:
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
        elif run["status"] in ("queued", "running"):
            self.db.update_run(run_id, status="cancelled", error="用户已取消，消息不会自动重发。")
        return self.db.run(run_id)

    async def tick(self):
        now = self.clock()
        if self.db.get("maintenance_until", 0) > now:
            return
        launch = []
        with self.db.tx(True) as db:
            rows = db.execute("""SELECT t.* FROM tasks t JOIN accounts a ON a.id=t.account_id
                WHERE t.enabled=1 AND t.due_at<=? AND a.status!='invalid' AND a.blocked_until<=?
                ORDER BY t.due_at LIMIT 100""", (now, now)).fetchall()
            for row in rows:
                task = self.db.task_row(row)
                if db.execute("SELECT 1 FROM runs WHERE task_id=? AND status IN ('queued','running')", (row["id"],)).fetchone():
                    continue
                try:
                    run, created = self.db.claim_run(row["id"], "scheduled", "schedule:" + str(row["next_at"]), connection=db, scheduled_at=row["next_at"])
                except AppError as exc:
                    if exc.code == "QUEUE_FULL":
                        break
                    continue
                # Advance from now: a long execution never causes a burst of missed sends.
                following = next_time(task, now, anchor=row["next_at"])
                if following is None:
                    task["enabled"] = False
                db.execute("UPDATE tasks SET next_at=?,due_at=?,enabled=?,config=? WHERE id=?", (following, self.due(following, task), task["enabled"], json.dumps({k: v for k, v in task.items() if k not in ("id", "revision", "nextRunAt", "createdAt", "nextScheduledAt")}, ensure_ascii=False), row["id"]))
                if created:
                    launch.append(run)
        for run in launch:
            self.launch(run)
        if now - self.last_cleanup > 60:
            await self.telegram.cleanup_logins()
            self.db.cleanup(self.db.get("settings")["retention"])
            self.last_cleanup = now
        if self.summary_job is None or self.summary_job.done():
            self.summary_job = asyncio.create_task(self.maybe_summary())

    def recover(self):
        now = self.clock()
        with self.db.tx() as connection:
            active = connection.execute("SELECT id FROM runs WHERE status IN ('queued','running')").fetchall()
        for row in active:
            self.db.update_run(row["id"], status="interrupted", errorCode="SERVICE_RESTARTED", error="服务重启时此执行尚未完成，已保留发送状态，不自动重发。")
        with self.db.tx(True) as db:
            for row in db.execute("SELECT * FROM tasks WHERE enabled=1 AND due_at<?", (now - 60,)).fetchall():
                task = self.db.task_row(row)
                result = {"sent": False, "sendState": "not_sent", "businessStatus": "unknown", "duration": "未执行", "message": "", "reply": "服务未运行时错过了这次计划，已跳过并恢复后续计划。", "logs": [], "replies": []}
                db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (new_id("run"), row["id"], row["account_id"], row["config"], "skipped", "scheduled", row["next_at"], "schedule:" + str(row["next_at"]), now, None, now, json.dumps(result, ensure_ascii=False)))
                following = next_time(task, now, anchor=row["next_at"])
                if following is None:
                    task["enabled"] = False
                config = {k: v for k, v in task.items() if k not in ("id", "revision", "nextRunAt", "createdAt", "nextScheduledAt")}
                db.execute("UPDATE tasks SET next_at=?,due_at=?,enabled=?,config=? WHERE id=?", (following, self.due(following, task), task["enabled"], json.dumps(config, ensure_ascii=False), row["id"]))

    async def loop(self, interval):
        while not self.stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception:
                # Keep the scheduler alive without leaking a request/session in logs.
                import logging
                logging.getLogger("shike.scheduler").error("调度检查未完成，将在下一周期重试。")
            await asyncio.sleep(interval)

    async def stop(self):
        self.stopping = True
        jobs = list(self.jobs.values())
        if self.summary_job is not None and not self.summary_job.done():
            jobs.append(self.summary_job)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)

    async def send_notification(self, text, account_id=None):
        settings = self.db.get("settings")
        if settings["notifyTarget"] == "bot":
            import httpx
            import logging
            logging.getLogger("httpx").setLevel(logging.WARNING)
            encrypted = self.db.get("notification_token")
            if not encrypted or not settings["notifyChat"]:
                raise AppError("NOTIFICATION_NOT_CONFIGURED", "请先配置通知机器人和接收会话。", 409)
            token = self.telegram.vault.decrypt(encrypted)
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.post("https://api.telegram.org/bot" + token + "/sendMessage", json={"chat_id": settings["notifyChat"], "text": text[:4000]})
                if response.status_code != 200 or not response.json().get("ok"):
                    raise AppError("NOTIFICATION_FAILED", "通知未送达，请检查机器人 Token、会话 ID 和接收权限。", 502)
            return
        if account_id is None:
            accounts = [a for a in self.db.accounts() if a["status"] == "connected"]
            if not accounts:
                raise AppError("NOTIFICATION_NO_ACCOUNT", "没有可用于发送通知的账号。", 409)
            account_id = accounts[0]["id"]
        async with self.telegram.account_client(account_id) as client:
            await asyncio.wait_for(client.send_message("me", text[:4000], parse_mode=None, link_preview=False), 30)

    async def notify_run(self, task, run_id):
        run = self.db.run(run_id)
        if task["notify"] in ("none", "summary") or (task["notify"] == "failure" and run["status"] not in FINAL_ERRORS):
            self.db.update_run(run_id, notificationStatus="not_requested")
            return
        detail = run.get("reply") or run.get("error") or ("消息已发送，本任务无需等待回复。" if run["status"] == "sent" else "没有文本回复")
        text = f"拾刻 · {task['name']}\n执行结果：{RESULT_LABELS.get(run['status'], run['status'])}\n目标：{task['target']}\n\n" + detail
        await self.send_notification(text, task["accountId"])
        self.db.update_run(run_id, notificationStatus="sent")

    async def maybe_summary(self):
        settings = self.db.get("settings")
        local = datetime.fromtimestamp(self.clock(), UTC).astimezone(ZoneInfo(settings["timezone"]))
        today = local.date().isoformat()
        if local.strftime("%H:%M") < settings["summaryTime"] or self.db.get("last_summary_date") == today:
            return
        selected = {t["id"] for t in self.db.tasks() if t["notify"] == "summary"}
        if not selected:
            return
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        placeholders = ",".join("?" for _ in selected)
        query = f"FROM runs WHERE created>=? AND task_id IN ({placeholders})"
        params = (midnight, *selected)
        with self.db.tx() as connection:
            counts = {r[0]: r[1] for r in connection.execute("SELECT status,COUNT(*) " + query + " GROUP BY status", params)}
            recent = connection.execute("SELECT * " + query + " ORDER BY created DESC,rowid DESC LIMIT 40", params).fetchall()
            runs = [self.db.run_row(r) for r in recent]
        # Claim before sending, so an uncertain network outcome is never replayed on restart.
        self.db.set("last_summary_date", today)
        total = sum(counts.values())
        attention = sum(counts.get(status, 0) for status in FINAL_ERRORS)
        text = f"拾刻 · 每日摘要 {today}\n共 {total} 条记录，{attention} 次需要留意。\n" + "\n".join(r["taskName"] + "：" + RESULT_LABELS.get(r["status"], r["status"]) for r in runs)
        try:
            await self.send_notification(text)
            self.db.set("last_summary_status", "sent")
        except Exception:
            self.db.set("last_summary_status", "failed")
