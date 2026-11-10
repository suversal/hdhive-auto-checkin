import json
from datetime import UTC, datetime, timedelta

from conftest import await_run, create_task, task_body


def test_account_rename_is_offline_and_preserves_identity_session_tasks_and_history(ready):
    from shike.database import Database
    db = ready.app.state.db
    account_id = ready.account["id"]
    task = create_task(ready)
    db.claim_run(task["id"], "manual")
    before = db.account(account_id, private=True)
    historical = db.runs()
    # Renaming a disconnected account must not invoke Telegram or reset its state.
    db.account_status(account_id, "invalid")
    ready.factory.mode = "network"
    response = ready.client.patch(f"/api/accounts/{account_id}", json={"name": "  工作账号 · 中文  "})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "工作账号 · 中文"
    assert "sessionCipher" not in response.json()
    assert db.account(account_id, private=True) == {**before, "name": "工作账号 · 中文", "status": "invalid"}
    assert db.task(task["id"]) == task
    assert db.runs() == historical
    assert ready.client.get("/api/state").json()["accounts"][0]["name"] == "工作账号 · 中文"
    assert Database(ready.config.data_dir).account(account_id)["name"] == "工作账号 · 中文"
    assert ready.factory.sends == []


def test_account_rename_validates_name_and_rejects_changes_to_other_fields(ready):
    path = f"/api/accounts/{ready.account['id']}"
    for body in ({"name": ""}, {"name": " \t\n"}, {"name": "长" * 31}, {"name": "名称", "status": "invalid"}):
        assert ready.client.patch(path, json=body).status_code == 422
    assert ready.app.state.db.account(ready.account["id"])["name"] == "主账号"
    assert ready.client.patch("/api/accounts/does-not-exist", json={"name": "名称"}).status_code == 404


def test_account_rename_requires_login_and_csrf(ready):
    path = f"/api/accounts/{ready.account['id']}"
    assert ready.client.patch(path, json={"name": "名称"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    ready.client.cookies.clear()
    assert ready.client.patch(path, json={"name": "名称"}).status_code == 401
    assert ready.app.state.db.account(ready.account["id"])["name"] == "主账号"


def test_account_import_encrypts_session_and_omits_secrets(ready):
    state = ready.client.get("/api/state").json()
    assert len(state["accounts"]) == 1
    assert state["accounts"][0]["status"] == "connected"
    assert "session" not in json.dumps(state).lower()
    assert "a" * 32 not in json.dumps(state)
    row = ready.app.state.db.account(ready.account["id"], private=True)
    assert "test-session-imported" not in row["sessionCipher"]
    assert ready.app.state.vault.decrypt(row["sessionCipher"]).startswith("test-session-imported")


def test_phone_code_and_two_factor_are_real_service_flow(ready):
    ready.factory.two_factor = True
    start = ready.client.post("/api/accounts/login/start", json={"name": "重新登录", "phone": "+8613800000000", "accountId": ready.account["id"]})
    assert start.status_code == 200
    key = start.json()["loginId"]
    assert ready.client.post(f"/api/accounts/login/{key}/code", json={"code": "00000"}).json()["code"] == "CODE_INVALID"
    response = ready.client.post(f"/api/accounts/login/{key}/code", json={"code": "12345"})
    assert response.json()["step"] == "password"
    response = ready.client.post(f"/api/accounts/login/{key}/password", json={"password": "not-persisted-test-password"})
    assert response.status_code == 200
    assert response.json()["step"] == "complete"
    assert key not in ready.app.state.telegram.pending
    for suffix in ("", "-wal"):
        path = ready.app.state.db.path.with_name("shike.db" + suffix)
        if path.exists():
            assert b"not-persisted-test-password" not in path.read_bytes()


def test_login_handle_is_bound_to_admin_session(ready):
    response = ready.client.post("/api/accounts/login/start", json={"name": "登录流程", "phone": "+8613800000000"})
    key = response.json()["loginId"]
    logged = ready.client.post("/api/auth/login", json={"password": "test-admin-password"})
    ready.client.headers["X-CSRF-Token"] = logged.json()["csrfToken"]
    assert ready.client.post(f"/api/accounts/login/{key}/code", json={"code": "12345"}).status_code == 410


def test_duplicate_account_is_rejected_and_network_is_not_session_invalid(ready):
    response = ready.client.post("/api/accounts/import", json={"name": "重复", "session": "test-session-imported-real-adapter-tests"})
    assert response.status_code == 409
    ready.factory.mode = "network"
    ready.client.portal.call(ready.app.state.telegram.close_account, ready.account["id"])
    response = ready.client.post(f"/api/accounts/{ready.account['id']}/check")
    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert ready.app.state.db.account(ready.account["id"])["status"] == "connected"


def test_dialogs_and_target_resolve(ready):
    response = ready.client.get(f"/api/accounts/{ready.account['id']}/dialogs")
    assert response.status_code == 200
    assert response.json()[0]["id"] == "me"
    resolved = ready.client.post("/api/targets/resolve", json={"accountId": ready.account["id"], "target": "@testbot"})
    assert resolved.json()["targetType"] == "bot"
    assert ready.client.post("/api/targets/resolve", json={"accountId": ready.account["id"], "target": "https://untrusted.invalid"}).status_code == 400


def test_task_crud_and_revision_conflict(ready):
    task = create_task(ready)
    assert task["nextRunAt"]
    body = task_body(ready.account["id"], name="修改后的任务", revision=task["revision"])
    response = ready.client.put("/api/tasks/" + task["id"], json=body)
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert ready.client.put("/api/tasks/" + task["id"], json=body).status_code == 409
    assert ready.client.patch(f"/api/tasks/{task['id']}/enabled", json={"enabled": False}).json()["nextRunAt"] is None
    assert ready.client.delete("/api/tasks/" + task["id"]).status_code == 200
    assert ready.client.get("/api/tasks").json() == []


def test_task_validation_and_expired_one_off(ready):
    for overrides in ({"steps": [{"type": "click", "text": "click"}]}, {"timezone": "No/SuchZone"}, {"schedule": "cron", "cron": "not cron"}, {"schedule": "weekly", "weekdays": []}, {"steps": [{"type": "send", "text": ""}]}):
        assert ready.client.post("/api/tasks", json=task_body(ready.account["id"], **overrides)).status_code == 422
    response = ready.client.post("/api/tasks", json=task_body(ready.account["id"], schedule="once", once="2020-01-01T00:00"))
    assert response.json()["code"] == "SCHEDULE_EXPIRED"


def test_template_roundtrip_excludes_accounts_and_stays_paused(ready):
    create_task(ready)
    template = ready.client.get("/api/templates/export").json()
    assert "accountId" not in template["tasks"][0]
    assert "session" not in json.dumps(template).lower()
    response = ready.client.post("/api/templates/import", json=template)
    assert response.status_code == 201
    assert ready.client.get("/api/tasks").json()[-1]["enabled"] is False
    bad = {"format": "shike-task-v1", "tasks": [template["tasks"][0], {**template["tasks"][0], "session": "do-not-import"}]}
    assert ready.client.post("/api/templates/import", json=bad).status_code == 400
    assert len(ready.client.get("/api/tasks").json()) == 2


def test_removing_account_pauses_related_tasks_and_preserves_records(ready):
    task = create_task(ready)
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    await_run(ready, run_id)
    assert ready.client.delete(f"/api/accounts/{ready.account['id']}").status_code == 200
    assert ready.client.get("/api/tasks").json()[0]["enabled"] is False
    assert ready.client.get(f"/api/runs/{run_id}").status_code == 200
