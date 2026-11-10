from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from .errors import AppError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def setup_link(base_url: str, token: str) -> str:
    # The fragment never reaches the server, reverse proxy or HTTP access log.
    # The frontend consumes it and immediately replaces the browser history URL.
    return base_url.rstrip("/") + "/?setup=1#setup?bootstrap=" + quote(token, safe="")


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return "pbkdf2_sha256$600000$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(value).decode()


def check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        result = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(result, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def private_file(path: Path, value: bytes) -> bytes:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        os.chmod(path, 0o600)
        return path.read_bytes()
    with os.fdopen(fd, "wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    return value


class Vault:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(data_dir, 0o700)
        key_file = data_dir / "master.key"
        external = os.getenv("SHIKE_SECRET_KEY")
        if external:
            key = external.encode()
        else:
            # A lost key must never be silently replaced beside an existing database.
            if not key_file.exists() and (data_dir / "shike.db").exists():
                raise RuntimeError("数据目录缺少加密密钥。请恢复原 master.key 或设置原 SHIKE_SECRET_KEY。")
            key = private_file(key_file, Fernet.generate_key())
        try:
            self.fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("SHIKE_SECRET_KEY 必须是有效的 Fernet 密钥。") from exc
        self.setup_token = os.getenv("SHIKE_SETUP_TOKEN") or private_file(
            data_dir / "setup.token", secrets.token_urlsafe(32).encode()
        ).decode().strip()
        if len(self.setup_token) < 16:
            raise RuntimeError("首次设置口令至少需要 16 个字符。")

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            raise AppError("VAULT_KEY_MISMATCH", "无法解密凭证，请检查实例的原始加密密钥。", 503) from exc


class InstanceLock:
    def __init__(self, data_dir: Path):
        self.file = (data_dir / "instance.lock").open("a+")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise RuntimeError("此数据目录已有实例运行。拾刻要求单实例、单 Uvicorn worker。") from None

    def close(self):
        if not self.file.closed:
            fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()


class BodyLimitMiddleware:
    """Bound JSON requests even when the client uses chunked transfer encoding."""

    def __init__(self, app, max_bytes=1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                from starlette.responses import JSONResponse
                response = JSONResponse({"code": "BODY_TOO_LARGE", "message": "请求内容不能超过 1 MB。"}, status_code=413)
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            return messages.pop(0) if messages else await receive()

        await self.app(scope, replay, send)
