import time

import pytest

from conftest import await_run, create_task


def test_execution_preserves_raw_reply_and_does_not_guess_success(ready):
    task = create_task(ready)
    response = ready.client.post(f"/api/tasks/{task['id']}/run", headers={"Idempotency-Key": "same-client-request"})
    assert response.status_code == 202
    run = await_run(ready, response.json()["id"])
    assert run["status"] == "replied"
    assert run["businessStatus"] == "unknown"
    assert run["reply"] == "签到成功，获得 5 积分。"
    assert run["sent"] is True
    assert ready.factory.sends[0][1]["parse_mode"] is None
    replay = ready.client.post(f"/api/tasks/{task['id']}/run", headers={"Idempotency-Key": "same-client-request"})
    assert replay.json()["id"] == run["id"]
    assert len(ready.factory.sends) == 1


def test_task_list_returns_latest_reply_and_does_not_reuse_a_previous_run(ready):
    task = create_task(ready)
    db = ready.app.state.db
    run, _ = db.claim_run(task["id"], "manual")
    text = "原始回复第一行\n第二行 <b>保持原文</b>"
    db.update_run(run["id"], status="replied", reply=text, sent=True, sendState="sent")
    current = ready.client.get("/api/state").json()["tasks"][0]
    assert current["lastStatus"] == current["lastRun"]["status"] == "replied"
    assert current["lastRun"]["reply"] == text
    assert current["lastRun"]["id"] == run["id"]
    queued, _ = db.claim_run(task["id"], "manual")
    current = ready.client.get("/api/state").json()["tasks"][0]
    assert current["lastRun"]["id"] == queued["id"]
    assert current["lastStatus"] == "queued"
    assert current["lastRun"]["reply"] == ""
    assert ready.factory.sends == []


def test_task_reply_is_available_even_outside_the_loaded_history_page(ready):
    from shike.database import new_id
    db = ready.app.state.db
    first = create_task(ready)
    old, _ = db.claim_run(first["id"], "manual")
    db.update_run(old["id"], status="replied", reply="较早任务的真实回复")
    other = create_task(ready, name="另一个任务")
    newer, _ = db.claim_run(other["id"], "manual")
    db.update_run(newer["id"], status="sent")
    with db.tx(True) as connection:
        seed = list(connection.execute("SELECT * FROM runs WHERE id=?", (newer["id"],)).fetchone())
        rows = []
        for index in range(201):
            item = seed.copy()
            item[0], item[8] = new_id("run"), time.time() + index
            rows.append(item)
        connection.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    state = ready.client.get("/api/state").json()
    assert old["id"] not in {run["id"] for run in state["runs"]}
    task = next(t for t in state["tasks"] if t["id"] == first["id"])
    assert task["lastRun"]["reply"] == "较早任务的真实回复"
    assert "logs" not in task["lastRun"]


@pytest.mark.parametrize("target,target_type", [("@test_user", "user"), ("me", "self"), ("@testbot", "bot")])
def test_only_send_needs_no_reply(ready, target, target_type):
    ready.factory.mode = "timeout"  # None of these recipients sends any reply.
    task = create_task(ready, target=target, targetType=target_type, steps=[{"type": "send", "text": "a plain reminder"}])
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    run = await_run(ready, run_id)
    assert run["status"] == "sent"
    assert run["sendState"] == "sent"
    assert run["replies"] == []
    assert run["reply"] == ""  # A system hint must not be stored as a recipient's reply.
    assert len(ready.factory.sends) == 1
    assert any(log["message"] == "消息已发送" for log in run["logs"])
    assert not any("等待目标回复" in log["message"] for log in run["logs"])


def test_clicks_current_message_and_accepts_edited_reply(ready):
    task = create_task(ready, steps=[{"type": "send", "text": "/start"}, {"type": "wait", "seconds": 1}, {"type": "click", "text": "每日签到"}, {"type": "wait", "seconds": 1}], successWords="签到成功")
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    result = await_run(ready, run_id)
    assert result["status"] == "success"
    assert ready.factory.clicks == 1
    assert len(result["replies"]) == 2


def test_group_wait_ignores_unrelated_messages(ready):
    ready.factory.mode = "group"
    task = create_task(ready, target="-100123456")
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    run = await_run(ready, run_id)
    assert "无关群消息" not in run["reply"]
    assert run["status"] == "replied"


@pytest.mark.parametrize("target,target_type", [("@test_user", "user"), ("@testbot", "bot")])
def test_timeout_records_sent_and_does_not_retry(ready, target, target_type):
    ready.factory.mode = "timeout"
    task = create_task(ready, target=target, targetType=target_type)
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    run = await_run(ready, run_id)
    assert run["status"] == "timeout"
    assert run["sent"] is True
    assert run["sendState"] == "sent"
    assert run["errorCode"] == "REPLY_TIMEOUT"
    assert "若只需发消息" in run["error"]
    assert run["replies"] == []
    assert len(ready.factory.sends) == 1


def test_unknown_send_is_not_labeled_not_sent(ready):
    ready.factory.mode = "uncertain"
    task = create_task(ready)
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    run = await_run(ready, run_id)
    assert run["status"] == "error"
    assert run["sendState"] == "unknown"
    assert len(ready.factory.sends) == 0


def test_flood_wait_persists_cooldown(ready):
    ready.factory.mode = "flood"
    task = create_task(ready)
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    result = await_run(ready, run_id)
    assert result["status"] == "limited"
    assert ready.client.get("/api/accounts").json()[0]["blockedUntil"]
    assert ready.client.post(f"/api/tasks/{task['id']}/run").status_code == 429


def test_same_task_is_exclusive_but_pause_is_allowed_during_execution(ready):
    ready.factory.mode = "timeout"
    task = create_task(ready)
    first = ready.client.post(f"/api/tasks/{task['id']}/run").json()
    second = ready.client.post(f"/api/tasks/{task['id']}/run")
    assert second.status_code == 409
    assert second.json()["runId"] == first["id"]
    assert ready.client.patch(f"/api/tasks/{task['id']}/enabled", json={"enabled": False}).status_code == 200
    assert ready.client.delete(f"/api/tasks/{task['id']}").status_code == 409
    cancelled = ready.client.post(f"/api/runs/{first['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert len(ready.factory.sends) <= 1


def test_failure_keywords_take_precedence(ready):
    task = create_task(ready, successWords="签到成功", failureWords="积分")
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    run = await_run(ready, run_id)
    assert run["status"] == "failed"
    assert run["matchedRule"] == "积分"


def test_same_account_queues_different_tasks(ready):
    ready.factory.mode = "timeout"
    one = create_task(ready)
    two = create_task(ready, name="第二个任务")
    a = ready.client.post(f"/api/tasks/{one['id']}/run").json()
    b = ready.client.post(f"/api/tasks/{two['id']}/run").json()
    time.sleep(.05)
    assert ready.client.get(f"/api/runs/{a['id']}").json()["status"] == "running"
    assert ready.client.get(f"/api/runs/{b['id']}").json()["status"] == "queued"
    ready.client.post(f"/api/runs/{a['id']}/cancel")
    ready.client.post(f"/api/runs/{b['id']}/cancel")


def test_text_keyboard_button_correlates_the_new_sent_message(ready):
    ready.factory.text_button = True
    task = create_task(ready, steps=[{"type": "send", "text": "/start"}, {"type": "wait", "seconds": 1}, {"type": "click", "text": "每日签到"}, {"type": "wait", "seconds": 1}])
    run_id = ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"]
    result = await_run(ready, run_id)
    assert result["status"] == "replied"
    assert len(ready.factory.sends) == 2
    assert result["replies"][0]["messageId"] != result["replies"][1]["messageId"]
