"""Operator-only administrator provisioning. No public registration endpoint."""
from __future__ import annotations

from .database import Database
from .security import password_hash


def initialize_admin(db: Database, password: str, workspace: str = "我的工作空间"):
    if not 10 <= len(password) <= 1024:
        raise ValueError("管理密码需要 10 到 1024 位。")
    workspace = workspace.strip()
    if not 1 <= len(workspace) <= 30:
        raise ValueError("工作空间名称需要 1 到 30 个字符。")
    hashed = password_hash(password)
    with db.tx(True) as connection:
        if db.get("admin_password", connection=connection):
            raise ValueError("管理员已设置，不会覆盖现有密码；重设请使用 reset-password。")
        db.set("admin_password", hashed, connection=connection)
        settings = db.get("settings", connection=connection)
        settings["workspace"] = workspace
        db.set("settings", settings, connection=connection)
        connection.execute("DELETE FROM sessions")
