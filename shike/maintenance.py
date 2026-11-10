"""Offline backups and guarded deployment maintenance. Never connects to Telegram."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import __version__
from .database import Database, iso
from .security import InstanceLock

FILES = {"shike.db", "master.key"}
# Accept old backups containing the now unused bootstrap token. Never restore it.
LEGACY_FILES = FILES | {"setup.token"}


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def maintenance(data_dir: Path, enabled: bool | None = None) -> dict:
    if not (data_dir / "shike.db").is_file():
        raise ValueError("实例尚未启动，没有可维护的数据。")
    db = Database(data_dir)
    with db.tx(True) as connection:
        if enabled is not None:
            db.set("maintenance_until", time.time() + 3600 if enabled else 0, connection=connection)
        until = db.get("maintenance_until", 0, connection=connection)
        active = connection.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0]
    return {"maintenance": until > time.time(), "activeRuns": active}


def validate_snapshot(folder: Path):
    try:
        fernet = Fernet((folder / "master.key").read_bytes())
        with closing(sqlite3.connect((folder / "shike.db").as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("备份数据库完整性检查失败。")
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("备份的数据格式与此版本不兼容，请使用对应版本镜像。")
            for value, in db.execute("SELECT value FROM meta WHERE key IN ('telegram_credentials','notification_token')"):
                fernet.decrypt(json.loads(value).encode())
            for value, in db.execute("SELECT session_cipher FROM accounts"):
                fernet.decrypt(value.encode())
    except (InvalidToken, sqlite3.Error, TypeError, KeyError) as exc:
        raise ValueError("备份数据库或加密密钥不匹配，未修改原数据。") from exc


def backup(data_dir: Path, output: str = "-"):
    if not (data_dir / "shike.db").is_file():
        raise ValueError("没有可备份的数据库，请先启动实例。")
    lock = InstanceLock(data_dir)
    try:
        with tempfile.TemporaryDirectory(prefix="shike-backup-") as temporary:
            folder = Path(temporary)
            with closing(sqlite3.connect(data_dir / "shike.db")) as source, closing(sqlite3.connect(folder / "shike.db")) as target:
                source.backup(target)  # Includes committed WAL data in a standalone snapshot.
            external_key = os.getenv("SHIKE_SECRET_KEY")
            key = external_key.encode() if external_key else (data_dir / "master.key").read_bytes()
            (folder / "master.key").write_bytes(key)
            validate_snapshot(folder)
            manifest = {"format": 2, "version": __version__, "createdAt": iso(), "files": {}}
            for name in sorted(FILES):
                manifest["files"][name] = file_hash(folder / name)
            (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            handle = sys.stdout.buffer if output == "-" else open(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")
            try:
                with tarfile.open(fileobj=handle, mode="w|gz") as archive:
                    for name in sorted(FILES | {"manifest.json"}):
                        entry = archive.gettarinfo(str(folder / name), arcname=name)
                        entry.mode = 0o600
                        with (folder / name).open("rb") as content:
                            archive.addfile(entry, content)
            finally:
                if output != "-":
                    handle.close()
    finally:
        lock.close()


def restore(data_dir: Path, archive_path: str, replace: bool = False):
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = InstanceLock(data_dir)
    try:
        if any((data_dir / name).exists() for name in FILES) and not replace:
            raise ValueError("目标已有数据。确认需要覆盖时使用 --replace。")
        with tempfile.TemporaryDirectory(prefix="restore-", dir=data_dir) as temporary:
            folder = Path(temporary).resolve()
            seen = set()
            handle = sys.stdin.buffer if archive_path == "-" else open(archive_path, "rb")
            try:
                with tarfile.open(fileobj=handle, mode="r|gz") as archive:
                    for entry in archive:
                        if entry.name not in LEGACY_FILES | {"manifest.json"} or entry.name in seen or not entry.isfile():
                            raise ValueError("备份含有不支持的文件、路径或链接，未修改原数据。")
                        limit = 2 * 1024**3 if entry.name == "shike.db" else 65536
                        if entry.size > limit:
                            raise ValueError("备份文件超出支持大小，未修改原数据。")
                        seen.add(entry.name)
                        with archive.extractfile(entry) as source, (folder / entry.name).open("xb") as target:
                            shutil.copyfileobj(source, target)
                        os.chmod(folder / entry.name, 0o600)
            finally:
                if archive_path != "-":
                    handle.close()
            if seen not in (FILES | {"manifest.json"}, LEGACY_FILES | {"manifest.json"}):
                raise ValueError("备份文件不完整，未修改原数据。")
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("备份格式不支持。")
            expected = LEGACY_FILES if manifest.get("format") == 1 else FILES if manifest.get("format") == 2 else None
            if expected is None or seen != expected | {"manifest.json"} or not isinstance(manifest.get("files"), dict) or set(manifest["files"]) != expected:
                raise ValueError("备份格式不支持。")
            for name in seen - {"manifest.json"}:
                if file_hash(folder / name) != manifest["files"][name]:
                    raise ValueError("备份校验失败，未修改原数据。")
            external_key = os.getenv("SHIKE_SECRET_KEY")
            if external_key and external_key.encode() != (folder / "master.key").read_bytes():
                raise ValueError("当前 SHIKE_SECRET_KEY 与备份不一致，请使用备份对应的 .env。")
            validate_snapshot(folder)
            # Restoring an older snapshot must never re-send messages already sent later.
            db = Database(folder)
            with db.tx(True) as connection:
                for row in connection.execute("SELECT id,config FROM tasks").fetchall():
                    config = json.loads(row["config"])
                    config["enabled"] = False
                    connection.execute("UPDATE tasks SET config=?,enabled=0,next_at=NULL,due_at=NULL,revision=revision+1 WHERE id=?", (json.dumps(config, ensure_ascii=False), row["id"]))
                for row in connection.execute("SELECT id,result FROM runs WHERE status IN ('queued','running')").fetchall():
                    result = json.loads(row["result"])
                    result.update(errorCode="BACKUP_RESTORED", error="从备份恢复的未完成执行已中断，不自动重发。", duration="恢复时中断")
                    connection.execute("UPDATE runs SET status='interrupted',finished=?,result=? WHERE id=?", (time.time(), json.dumps(result, ensure_ascii=False), row["id"]))
                connection.execute("DELETE FROM sessions")
                db.set("maintenance_until", 0, connection=connection)
            with closing(sqlite3.connect(folder / "shike.db")) as connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            for suffix in ("-wal", "-shm"):
                (data_dir / ("shike.db" + suffix)).unlink(missing_ok=True)
            for name in FILES:
                os.replace(folder / name, data_dir / name)
            (data_dir / "setup.token").unlink(missing_ok=True)
            os.chmod(data_dir, 0o700)
    finally:
        lock.close()
