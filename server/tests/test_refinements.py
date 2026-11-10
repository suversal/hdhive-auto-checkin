import time
from datetime import datetime

from conftest import await_run, create_task
from shike.rendering import render_message


def test_bulk_pause_resume_and_atomic_validation(ready):
    first = create_task(ready)
    second = create_task(ready, name="第二个任务")
    ids = [first["id"], second["id"]]
    assert ready.client.post("/api/tasks/bulk", json={"taskIds": ids, "enabled": False}).json()["updated"] == 2
    assert all(not t["enabled"] and t["nextRunAt"] is None for t in ready.client.get("/api/tasks").json())
    response = ready.client.post("/api/tasks/bulk", json={"taskIds": [first["id"], "missing"], "enabled": True})
    assert response.status_code == 404
    assert not ready.app.state.db.task(first["id"])["enabled"]
    assert ready.client.post("/api/tasks/bulk", json={"taskIds": ids, "enabled": True}).status_code == 200
    assert all(t["enabled"] and t["nextRunAt"] for t in ready.client.get("/api/tasks").json())
    assert ready.factory.sends == []


def test_bulk_rejects_duplicate_selection_and_auth_missing(ready):
    assert ready.client.post("/api/tasks/bulk", headers={"Cookie":""}, json={"taskIds": ["one"], "enabled": False}).status_code == 401
    task = create_task(ready)
    assert ready.client.post("/api/tasks/bulk", json={"taskIds": [task["id"],task["id"]], "enabled": False}).status_code == 400


def test_message_tokens_follow_task_timezone_and_leave_other_braces_literal():
    at = datetime.fromisoformat("2026-11-09T23:45:00+00:00").timestamp()
    text = "{{date}} {{time}} {{weekday}} {literal} {{unknown}}"
    assert render_message(text, {"timezone":"Asia/Shanghai"}, at) == "2026-11-10 07:45 星期二 {literal} {{unknown}}"
    assert render_message("{{date}}", {"timezone":"UTC"}, at) == "2026-11-09"


def test_variable_execution_records_the_actual_sent_content(ready):
    task = create_task(ready, steps=[{"type":"send", "text":"日期 {{date}} / {{weekday}}"}])
    result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert result["status"] == "sent"
    assert "{{date}}" not in result["message"]
    assert result["message"] == ready.factory.sends[0][0]
    assert result["sentMessages"][0]["messageId"] > 0
    assert result["sentMessages"][0]["text"] == result["message"]


def test_cancelling_delay_does_not_send_the_next_message(ready):
    task = create_task(ready, steps=[{"type":"send", "text":"第一条"}, {"type":"delay","seconds":20}, {"type":"send","text":"不应发送"}])
    run = ready.client.post(f"/api/tasks/{task['id']}/run").json()
    for _ in range(100):
        if ready.factory.sends:
            break
        time.sleep(.01)
    result = ready.client.post(f"/api/runs/{run['id']}/cancel").json()
    assert result["status"] == "cancelled"
    assert [t[0] for t in ready.factory.sends] == ["第一条"]


def test_delay_between_reply_and_button_remains_valid(ready):
    task = create_task(ready, steps=[{"type":"send","text":"/start"}, {"type":"wait","seconds":1}, {"type":"delay","seconds":1}, {"type":"click","text":"每日签到"}, {"type":"wait","seconds":1}])
    result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert result["status"] == "replied"
    assert ready.factory.clicks == 1
