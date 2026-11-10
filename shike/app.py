from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Config
from .database import Database, iso, new_id
from .errors import AppError
from .models import (
    ApiCredentials, LoginCode, LoginInput, Model, PasswordChange, PasswordInput,
    PhoneLogin, QRStart, SessionImport, SettingsInput, TaskInput,
)
from .runner import Runner
from .scheduling import next_time, preview
from .security import BodyLimitMiddleware, InstanceLock, Vault, check_password, digest, password_hash
from .telegram import TelegramService, telegram_error


COOKIE = "shike_session"
SESSION_LIFETIME = 86400


class EnabledInput(Model):
    enabled: bool


class BulkInput(Model):
    taskIds: list[str] = Field(min_length=1, max_length=100)
    enabled: bool


class ResolveInput(Model):
    accountId: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)


class NotificationToken(Model):
    token: str = Field(pattern=r"^\d{5,20}:[a-zA-Z0-9_-]{20,100}$")


class TemplateImport(Model):
    format: str
    tasks: list[dict] = Field(min_length=1, max_length=100)


def create_app(config: Config | None = None, *, client_factory=None) -> FastAPI:
    config = config or Config.from_env()

    @asynccontextmanager
    async def lifespan(app):
        vault = Vault(config.data_dir)
        lock = InstanceLock(config.data_dir)
        try:
            db = Database(config.data_dir)
            # Detect a wrong key immediately instead of presenting every account as invalid.
            for key in ("telegram_credentials", "notification_token"):
                if encrypted := db.get(key):
                    vault.decrypt(encrypted)
            telegram = TelegramService(db, vault, client_factory)
            runner = Runner(db, telegram)
            app.state.db, app.state.vault = db, vault
            app.state.telegram, app.state.runner = telegram, runner
            runner.recover()
            loop = asyncio.create_task(runner.loop(config.scheduler_interval)) if config.scheduler_enabled else None
            if config.open_browser:
                async def open_local_browser():
                    import webbrowser
                    await asyncio.sleep(.4)
                    base = config.public_url or f"http://127.0.0.1:{config.local_port}"
                    await asyncio.to_thread(webbrowser.open, base)
                asyncio.create_task(open_local_browser())
            try:
                yield
            finally:
                if loop:
                    loop.cancel()
                    await asyncio.gather(loop, return_exceptions=True)
                await runner.stop()
                await telegram.close()
        finally:
            lock.close()

    app = FastAPI(title="拾刻", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.url.path.startswith("/api/"):
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 1024 * 1024:
                return JSONResponse({"code": "BODY_TOO_LARGE", "message": "请求内容过大。"}, status_code=413)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                expected = config.public_url or str(request.base_url).rstrip("/")
                if origin and origin != expected:
                    return JSONResponse({"code": "ORIGIN_INVALID", "message": "请求来源不匹配，请从面板原地址操作。"}, status_code=403)
                if request.headers.get("sec-fetch-site") == "cross-site":
                    return JSONResponse({"code": "ORIGIN_INVALID", "message": "不允许跨站提交。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return JSONResponse({"code": error.code, "message": error.message, **error.details}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        fields = [{"field": ".".join(map(str, e["loc"][1:])), "message": e["msg"]} for e in error.errors()]
        return JSONResponse({"code": "VALIDATION_ERROR", "message": "请检查填写的内容，字段格式或任务步骤不正确。", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def internal_error(request, error):
        logging.getLogger("shike").error("服务操作未完成，异常类型：%s", type(error).__name__)
        return JSONResponse({"code": "INTERNAL_ERROR", "message": "服务操作未完成，请稍后重试。"}, status_code=500)

    def db() -> Database:
        return app.state.db

    def session(request: Request):
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 128:
            return None
        with db().tx() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE token_hash=? AND expires>?", (digest(token), time.time())).fetchone()
            return dict(row) if row else None

    def auth(request: Request):
        current = session(request)
        if current is None:
            raise AppError("AUTH_REQUIRED", "请先登录管理面板。", 401)
        if request.method not in ("GET", "HEAD"):
            csrf = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(csrf, current["csrf"]):
                raise AppError("CSRF_INVALID", "页面验证已过期，请刷新页面后重试。", 403)
        return current

    def issue_session(response: Response):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with db().tx() as connection:
            connection.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), csrf, time.time() + SESSION_LIFETIME))
        response.set_cookie(COOKIE, token, max_age=SESSION_LIFETIME, httponly=True, secure=config.secure_cookie, samesite="strict", path="/")
        return {"authenticated": True, "csrfToken": csrf}

    def limit(request, scope, **kwargs):
        db().rate_limit(scope, request.client.host if request.client else "local", **kwargs)

    def public_settings():
        return {**db().get("settings"), "hasApi": bool(db().get("telegram_credentials")), "hasNotificationToken": bool(db().get("notification_token")), "lastSummaryStatus": db().get("last_summary_status")}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__, "adapter": "telegram" if client_factory is None else "test", "scheduler": "running" if config.scheduler_enabled else "disabled"}

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        current = session(request)
        return {"initialized": bool(db().get("admin_password")), "authenticated": current is not None, "csrfToken": current["csrf"] if current else None}

    @app.post("/api/auth/login")
    async def login(body: LoginInput, request: Request, response: Response):
        limit(request, "login")
        hashed = db().get("admin_password")
        if not hashed:
            raise AppError("ADMIN_NOT_INITIALIZED", "请先由部署者在服务器终端设置管理密码，再刷新登录。", 503)
        if not await asyncio.to_thread(check_password, body.password, hashed):
            raise AppError("LOGIN_INVALID", "管理密码不正确。", 401)
        return issue_session(response)

    @app.post("/api/auth/logout")
    async def logout(response: Response, current=Depends(auth)):
        for login_id, pending in list(app.state.telegram.pending.items()):
            if pending.owner == current["token_hash"]:
                await app.state.telegram.cancel_login(pending.owner, login_id)
        with db().tx() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (current["token_hash"],))
        response.delete_cookie(COOKIE, path="/", secure=config.secure_cookie, httponly=True, samesite="strict")
        return {"ok": True}

    @app.post("/api/auth/password")
    async def change_password(body: PasswordChange, request: Request, response: Response, current=Depends(auth)):
        limit(request, "password", limit=6)
        if not await asyncio.to_thread(check_password, body.current, db().get("admin_password")):
            raise AppError("PASSWORD_INVALID", "当前管理密码不正确。", 403)
        hashed = await asyncio.to_thread(password_hash, body.password)
        for login_id, pending in list(app.state.telegram.pending.items()):
            await app.state.telegram.cancel_login(pending.owner, login_id)
        with db().tx(True) as connection:
            db().set("admin_password", hashed, connection=connection)
            connection.execute("DELETE FROM sessions")
        return issue_session(response)

    @app.get("/api/state")
    async def state(current=Depends(auth)):
        settings, tasks, runs = public_settings(), db().tasks(), db().runs()
        now = time.time()
        for task in tasks:
            task["nextRuns"] = []
            if task["enabled"] and task["nextRunAt"]:
                task["nextRuns"].append(task["nextRunAt"])
                anchor = datetime.fromisoformat(task["nextScheduledAt"]).timestamp()
                following = anchor
                for _ in range(2):
                    following = next_time(task, following, anchor=anchor)
                    if following is None:
                        break
                    task["nextRuns"].append(iso(following))
        zone = ZoneInfo(settings["timezone"])
        midnight = datetime.now(zone).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        with db().tx() as connection:
            for task in tasks:
                latest = connection.execute("SELECT status FROM runs WHERE task_id=? ORDER BY created DESC,rowid DESC LIMIT 1", (task["id"],)).fetchone()
                task["lastStatus"] = latest[0] if latest else None
            counts = {r[0]: r[1] for r in connection.execute("SELECT status,COUNT(*) FROM runs WHERE created>=? GROUP BY status", (midnight,))}
        summary = {"todayExecuted": sum(n for status,n in counts.items() if status not in ("queued","running","skipped")), "attention": sum(counts.get(status,0) for status in ("error","failed","timeout","limited","interrupted"))}
        return {"settings": settings, "tasks": tasks, "accounts": db().accounts(), "runs": runs, "serverTime": iso(), "version": __version__, "summary": summary, "adapter": "telegram" if client_factory is None else "test"}

    @app.get("/api/settings")
    async def get_settings(current=Depends(auth)):
        return public_settings()

    @app.put("/api/settings")
    async def save_settings(body: SettingsInput, current=Depends(auth)):
        old = db().get("settings")
        proxy_changed = any(old[k] != getattr(body, k) for k in ("proxyType", "proxyHost", "proxyPort"))
        if proxy_changed and (db().busy() or app.state.telegram.pending):
            raise AppError("CONNECTION_BUSY", "有任务或登录流程正在使用连接，请完成后再修改代理。", 409)
        if proxy_changed:
            for account in db().accounts():
                await app.state.telegram.close_account(account["id"])
        db().set("settings", body.model_dump())
        return public_settings()

    @app.put("/api/settings/telegram")
    async def save_credentials(body: ApiCredentials, current=Depends(auth)):
        if db().busy() or app.state.telegram.pending:
            raise AppError("CONNECTION_BUSY", "请先完成正在进行的任务和登录流程，再更新连接信息。", 409)
        for account in db().accounts():
            await app.state.telegram.close_account(account["id"])
        db().set("telegram_credentials", app.state.vault.encrypt(body.model_dump_json()))
        return {"hasApi": True}

    @app.put("/api/settings/notification-token")
    async def save_notification_token(body: NotificationToken, current=Depends(auth)):
        db().set("notification_token", app.state.vault.encrypt(body.token))
        return {"hasNotificationToken": True}

    @app.post("/api/settings/test-connection")
    async def test_connection(current=Depends(auth)):
        client = app.state.telegram.make_client()
        try:
            await asyncio.wait_for(client.connect(), 20)
            return {"connected": True}
        except Exception as exc:
            raise telegram_error(exc) from None
        finally:
            await client.disconnect()

    @app.post("/api/settings/test-notification")
    async def test_notification(current=Depends(auth)):
        await app.state.runner.send_notification("拾刻测试通知：你的通知连接已经准备好。")
        return {"sent": True}

    @app.post("/api/accounts/login/start")
    async def start_login(body: PhoneLogin, request: Request, current=Depends(auth)):
        limit(request, "telegram_start", limit=3, window=60)
        return await app.state.telegram.start_login(current["token_hash"], body.name, body.phone, body.accountId)

    @app.post("/api/accounts/login/qr")
    async def start_qr(body: QRStart, request: Request, current=Depends(auth)):
        limit(request, "telegram_qr", limit=3, window=60)
        return await app.state.telegram.start_qr(current["token_hash"], body.name, body.accountId)

    @app.get("/api/accounts/login/{login_id}")
    async def login_status(login_id: str, current=Depends(auth)):
        return app.state.telegram.login_status(current["token_hash"], login_id)

    @app.post("/api/accounts/login/{login_id}/code")
    async def login_code(login_id: str, body: LoginCode, request: Request, current=Depends(auth)):
        limit(request, "telegram_code", limit=8, window=600)
        return await app.state.telegram.submit_code(current["token_hash"], login_id, body.code)

    @app.post("/api/accounts/login/{login_id}/password")
    async def login_password(login_id: str, body: PasswordInput, request: Request, current=Depends(auth)):
        limit(request, "telegram_password", limit=6, window=600)
        return await app.state.telegram.submit_password(current["token_hash"], login_id, body.password)

    @app.delete("/api/accounts/login/{login_id}")
    async def cancel_login(login_id: str, current=Depends(auth)):
        await app.state.telegram.cancel_login(current["token_hash"], login_id)
        return {"ok": True}

    @app.post("/api/accounts/import", status_code=201)
    async def import_session(body: SessionImport, request: Request, current=Depends(auth)):
        limit(request, "telegram_import", limit=5, window=60)
        return await app.state.telegram.import_session(body.name, body.session, body.accountId)

    @app.get("/api/accounts")
    async def accounts(current=Depends(auth)):
        return db().accounts()

    @app.post("/api/accounts/{account_id}/check")
    async def check_account(account_id: str, current=Depends(auth)):
        return await app.state.telegram.check(account_id)

    @app.delete("/api/accounts/{account_id}")
    async def remove_account(account_id: str, current=Depends(auth)):
        db().account(account_id)
        db().remove_account(account_id)
        await app.state.telegram.close_account(account_id)
        return {"ok": True}

    @app.get("/api/accounts/{account_id}/dialogs")
    async def dialogs(account_id: str, search: str = "", current=Depends(auth)):
        return await asyncio.wait_for(app.state.telegram.dialogs(account_id, search[:100]), 40)

    @app.post("/api/targets/resolve")
    async def resolve_target(body: ResolveInput, current=Depends(auth)):
        # Reuse server-side target validation; do not treat arbitrary URLs as chats.
        try:
            target = TaskInput.target_value(body.target)
        except ValueError:
            raise AppError("TARGET_INVALID", "目标应为 @用户名、数字会话 ID 或 me。") from None
        return await app.state.telegram.resolve(body.accountId, target)

    async def prepare_task(body: TaskInput):
        task = body.model_dump()
        if task["enabled"]:
            if not task["accountId"]:
                raise AppError("ACCOUNT_REQUIRED", "请先选择执行账号。")
            account = db().account(task["accountId"])
            if account["status"] == "invalid":
                raise AppError("SESSION_INVALID", "请先重新登录这个执行账号。", 409)
            task.update(await app.state.telegram.resolve(task["accountId"], task["target"]))
        elif task["accountId"]:
            db().account(task["accountId"])
        now = time.time()
        following = next_time(task, now) if task["enabled"] else None
        if task["enabled"] and following is None:
            raise AppError("SCHEDULE_EXPIRED", "这个计划没有未来的执行时间，请修改日期或时间。")
        return task, following, Runner.due(following, task)

    @app.post("/api/tasks/preview")
    async def schedule_preview(body: TaskInput, current=Depends(auth)):
        return {"nextRuns": preview(body.model_dump(), time.time()), "serverTime": iso()}

    @app.get("/api/tasks")
    async def tasks(current=Depends(auth)):
        return db().tasks()

    @app.post("/api/tasks", status_code=201)
    async def create_task(body: TaskInput, current=Depends(auth)):
        task, following, due = await prepare_task(body)
        return db().save_task(task, following, due)

    @app.post("/api/tasks/bulk")
    async def bulk_tasks(body: BulkInput, current=Depends(auth)):
        if len(set(body.taskIds)) != len(body.taskIds):
            raise AppError("TASK_SELECTION_INVALID", "请选择不重复的任务。")
        prepared = []
        for task_id in body.taskIds:
            existing = db().task(task_id)
            base = {k: v for k, v in existing.items() if k in TaskInput.model_fields}
            base["enabled"] = body.enabled
            task, following, due = await prepare_task(TaskInput.model_validate(base))
            prepared.append((task_id, existing["revision"], task, following, due))
        with db().tx(True) as connection:
            for task_id, revision, task, following, due in prepared:
                existing = db().task(task_id, connection=connection)
                if existing["revision"] != revision:
                    raise AppError("REVISION_CONFLICT", "部分任务已在其他页面修改，请刷新后重新选择。", 409)
                connection.execute("UPDATE tasks SET enabled=?,config=?,next_at=?,due_at=?,revision=revision+1,updated=? WHERE id=?", (body.enabled, json.dumps({k: v for k,v in task.items() if k != "revision"}, ensure_ascii=False), following, due, time.time(), task_id))
        return {"updated": len(prepared), "enabled": body.enabled}

    @app.put("/api/tasks/{task_id}")
    async def update_task(task_id: str, body: TaskInput, current=Depends(auth)):
        db().task(task_id)
        task, following, due = await prepare_task(body)
        return db().save_task(task, following, due, task_id)

    @app.patch("/api/tasks/{task_id}/enabled")
    async def toggle_task(task_id: str, body: EnabledInput, current=Depends(auth)):
        existing = db().task(task_id)
        base = {k: v for k, v in existing.items() if k in TaskInput.model_fields}
        base["enabled"] = body.enabled
        task, following, due = await prepare_task(TaskInput.model_validate(base))
        with db().tx(True) as connection:
            connection.execute("UPDATE tasks SET enabled=?,config=?,next_at=?,due_at=?,revision=revision+1 WHERE id=?", (body.enabled, json.dumps({k: v for k, v in task.items() if k != "revision"}, ensure_ascii=False), following, due, task_id))
        return db().task(task_id)

    @app.delete("/api/tasks/{task_id}")
    async def remove_task(task_id: str, current=Depends(auth)):
        db().remove_task(task_id)
        return {"ok": True}

    @app.post("/api/tasks/{task_id}/run", status_code=202)
    async def run_task(task_id: str, idempotency_key: str | None = Header(default=None), current=Depends(auth)):
        if idempotency_key and len(idempotency_key) > 128:
            raise AppError("IDEMPOTENCY_INVALID", "执行请求标识过长。")
        return app.state.runner.enqueue(task_id, idempotency_key)

    @app.get("/api/runs")
    async def runs(limit: int = 200, offset: int = 0, current=Depends(auth)):
        if not 1 <= limit <= 1000 or offset < 0:
            raise AppError("PAGINATION_INVALID", "记录分页范围无效。")
        return {"items": db().runs(limit, offset), "offset": offset, "limit": limit}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str, current=Depends(auth)):
        return db().run(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, current=Depends(auth)):
        return await app.state.runner.cancel(run_id)

    @app.get("/api/templates/export")
    async def export_templates(current=Depends(auth)):
        keys = set(TaskInput.model_fields) - {"accountId", "revision"}
        return {"format": "shike-task-v1", "tasks": [{k: v for k, v in t.items() if k in keys} for t in db().tasks()]}

    @app.post("/api/templates/import", status_code=201)
    async def import_templates(body: TemplateImport, current=Depends(auth)):
        if body.format != "shike-task-v1":
            raise AppError("TEMPLATE_FORMAT", "请选择由拾刻导出的任务模板。")
        available = next((a["id"] for a in db().accounts() if a["status"] == "connected"), "")
        prepared = []
        for raw in body.tasks:
            try:
                item = TaskInput.model_validate({**raw, "accountId": available, "enabled": False, "revision": None})
            except ValidationError:
                raise AppError("TEMPLATE_INVALID", "模板包含无效任务或不允许导入的字段，请检查配置。") from None
            prepared.append(item.model_dump(exclude={"revision"}))
        with db().tx(True) as connection:
            if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] + len(prepared) > 500:
                raise AppError("TASK_LIMIT", "导入后任务数将超过 500 个，请减少导入数量。")
            for item in prepared:
                now = time.time()
                connection.execute("INSERT INTO tasks VALUES (?,?,?,?,1,NULL,NULL,?,?)", (new_id("task"), available or None, json.dumps(item, ensure_ascii=False), 0, now, now))
        return {"imported": len(prepared), "enabled": False}

    if config.web_dir.exists():
        app.mount("/assets", StaticFiles(directory=config.web_dir), name="assets")

        @app.get("/", include_in_schema=False)
        async def index():
            return FileResponse(config.web_dir / "index.html", headers={"Cache-Control": "no-cache"})

    return app
