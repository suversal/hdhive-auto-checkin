import io
import json
import tarfile
import time

import pytest
from cryptography.fernet import Fernet

from conftest import create_task
from shike.database import Database
from shike.maintenance import backup, maintenance, restore
from shike.models import TaskInput
from shike.security import InstanceLock, Vault, password_hash


def seeded(folder):
    vault = Vault(folder)
    db = Database(folder)
    db.set("admin_password", password_hash("synthetic-backup-password"))
    db.set("telegram_credentials", vault.encrypt(json.dumps({"apiId": 12345, "apiHash": "a" * 32})))
    account = db.save_account("合成账号", 1, {}, vault.encrypt("synthetic-session"))
    task = TaskInput(name="合成任务", accountId=account["id"], target="me", steps=[{"type": "send", "text": "不得真实发送"}], notify="none").model_dump(exclude={"revision"})
    task = db.save_task(task, time.time() - 30, time.time() - 30)
    run, _ = db.claim_run(task["id"], "manual")
    db.update_run(run["id"], status="running", sent=True, sendState="sent", message="合成历史内容")
    with db.tx(True) as connection:
        connection.execute("INSERT INTO sessions VALUES ('synthetic-token','synthetic-csrf',?)", (time.time() + 3600,))
    return vault, db, task, run


def test_backup_restore_preserves_key_accounts_and_history_but_pauses_tasks(tmp_path):
    source = tmp_path / "source"
    vault, db, task, run = seeded(source)
    archive = tmp_path / "data.tar.gz"
    backup(source, str(archive))
    assert archive.stat().st_mode & 0o777 == 0o600
    target = tmp_path / "target"
    restore(target, str(archive))
    restored = Database(target)
    assert restored.get("admin_password") == db.get("admin_password")
    assert Vault(target).decrypt(restored.get("telegram_credentials")) == vault.decrypt(db.get("telegram_credentials"))
    assert not restored.task(task["id"])["enabled"]
    assert restored.task(task["id"])["nextRunAt"] is None
    historical = restored.run(run["id"])
    assert historical["status"] == "interrupted"
    assert historical["sendState"] == "sent"
    assert historical["errorCode"] == "BACKUP_RESTORED"
    with restored.tx() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert (target / "master.key").stat().st_mode & 0o777 == 0o600


def test_backup_and_restore_refuse_running_instance(tmp_path):
    source = tmp_path / "source"
    seeded(source)
    archive = tmp_path / "data.tar.gz"
    backup(source, str(archive))
    lock = InstanceLock(source)
    try:
        with pytest.raises(RuntimeError):
            backup(source, str(tmp_path / "second.tar.gz"))
        with pytest.raises(RuntimeError):
            restore(source, str(archive), True)
    finally:
        lock.close()


def test_restore_rejects_overwrite_and_external_key_mismatch(tmp_path, monkeypatch):
    source = tmp_path / "source"
    seeded(source)
    archive = tmp_path / "data.tar.gz"
    backup(source, str(archive))
    before = (source / "shike.db").read_bytes()
    with pytest.raises(ValueError, match="目标已有数据"):
        restore(source, str(archive))
    monkeypatch.setenv("SHIKE_SECRET_KEY", Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="SHIKE_SECRET_KEY"):
        restore(source, str(archive), True)
    assert (source / "shike.db").read_bytes() == before


@pytest.mark.parametrize("name,link", [("../escape", False), ("master.key", True)])
def test_restore_rejects_unsafe_archive_without_modifying_data(tmp_path, name, link):
    source = tmp_path / "source"
    seeded(source)
    before = (source / "shike.db").read_bytes()
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo(name)
        if link:
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            handle.addfile(info)
        else:
            info.size = 4
            handle.addfile(info, io.BytesIO(b"test"))
    with pytest.raises(ValueError, match="不支持"):
        restore(source, str(archive), True)
    assert (source / "shike.db").read_bytes() == before
    assert not (tmp_path / "escape").exists()


def test_restore_detects_tampered_backup_before_replacing_data(tmp_path):
    source = tmp_path / "source"
    seeded(source)
    archive = tmp_path / "data.tar.gz"
    backup(source, str(archive))
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(archive) as original, tarfile.open(bad, "w:gz") as modified:
        for info in original:
            content = original.extractfile(info).read()
            if info.name == "setup.token":
                content = b"changed"
                info.size = len(content)
            modified.addfile(info, io.BytesIO(content))
    before = (source / "shike.db").read_bytes()
    with pytest.raises(ValueError, match="校验失败"):
        restore(source, str(bad), True)
    assert (source / "shike.db").read_bytes() == before


def test_maintenance_blocks_new_manual_and_scheduled_sends_and_can_be_released(ready):
    task = create_task(ready)
    status = maintenance(ready.config.data_dir, True)
    assert status == {"maintenance": True, "activeRuns": 0}
    response = ready.client.post(f"/api/tasks/{task['id']}/run")
    assert response.status_code == 409
    assert response.json()["code"] == "MAINTENANCE"
    with ready.app.state.db.tx(True) as connection:
        connection.execute("UPDATE tasks SET due_at=?,next_at=?", (time.time() - 1, time.time() - 1))
    ready.client.portal.call(ready.app.state.runner.tick)
    assert ready.factory.sends == []
    assert ready.app.state.db.runs() == []
    maintenance(ready.config.data_dir, False)
    assert ready.client.post(f"/api/tasks/{task['id']}/run").status_code == 202


def test_maintenance_reports_active_jobs_without_cancelling_them(ready):
    task = create_task(ready)
    run, _ = ready.app.state.db.claim_run(task["id"], "manual")
    assert maintenance(ready.config.data_dir, True)["activeRuns"] == 1
    assert ready.app.state.db.run(run["id"])["status"] == "queued"
    maintenance(ready.config.data_dir, False)
