import os
import subprocess
import sys

from shike.database import Database
from shike.security import InstanceLock, check_password


def command(data, *args, password="synthetic-terminal-password"):
    environment = {**os.environ, "SHIKE_DATA_DIR": str(data)}
    environment.pop("SHIKE_SECRET_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "shike", *args, "--password-stdin"],
        input=password + "\n", text=True, capture_output=True, env=environment,
    )


def test_cli_initializes_once_without_printing_or_overwriting_password(tmp_path):
    data = tmp_path / "data"
    result = command(data, "init-admin", "--workspace", "终端空间")
    assert result.returncode == 0, result.stderr
    assert "synthetic-terminal-password" not in result.stdout + result.stderr
    db = Database(data)
    hashed = db.get("admin_password")
    assert check_password("synthetic-terminal-password", hashed)
    assert db.get("settings")["workspace"] == "终端空间"
    assert not (data / "setup.token").exists()
    result = command(data, "init-admin", password="different-password")
    assert result.returncode == 0
    assert db.get("admin_password") == hashed


def test_cli_refuses_short_password_and_running_instance(tmp_path):
    data = tmp_path / "data"
    assert command(data, "init-admin", password="short").returncode == 1
    db = Database(data)
    assert db.get("admin_password") is None
    lock = InstanceLock(data)
    try:
        result = command(data, "init-admin")
        assert result.returncode == 1
        assert "单实例" in result.stderr
        assert db.get("admin_password") is None
    finally:
        lock.close()


def test_cli_password_reset_preserves_settings_and_revokes_sessions(tmp_path):
    data = tmp_path / "data"
    assert command(data, "init-admin", "--workspace", "保留空间").returncode == 0
    db = Database(data)
    with db.tx() as connection:
        connection.execute("INSERT INTO sessions VALUES ('old','csrf',9999999999)")
    result = command(data, "reset-password", password="replacement-terminal-password")
    assert result.returncode == 0, result.stderr
    assert "replacement-terminal-password" not in result.stdout + result.stderr
    assert check_password("replacement-terminal-password", db.get("admin_password"))
    assert db.get("settings")["workspace"] == "保留空间"
    with db.tx() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
