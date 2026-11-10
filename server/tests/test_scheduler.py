from datetime import UTC, datetime

from shike.scheduling import next_time, preview

from conftest import await_run, create_task, task_body


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def test_daily_weekly_and_timezones():
    body = task_body("a", schedule="daily", time="08:30", timezone="Asia/Shanghai")
    assert next_time(body, epoch("2026-11-09T00:00:00+00:00")) == epoch("2026-11-09T00:30:00+00:00")
    body.update(schedule="weekly", weekdays=[5])
    assert next_time(body, epoch("2026-11-09T00:00:00+00:00")) == epoch("2026-11-13T00:30:00+00:00")


def test_dst_nonexistent_time_is_skipped():
    body = task_body("a", schedule="daily", time="02:30", timezone="America/New_York")
    assert next_time(body, epoch("2026-03-08T00:00:00-05:00")) == epoch("2026-03-09T02:30:00-04:00")


def test_cron_and_interval_are_anchored():
    body = task_body("a", schedule="cron", cron="30 8 * * 1-5", timezone="Asia/Shanghai")
    assert len(preview(body, epoch("2026-11-09T00:00:00+00:00"))) == 3
    body.update(schedule="interval", interval=1)
    start = epoch("2026-11-09T00:00:00+00:00")
    assert next_time(body, start + 3700, anchor=start) == start + 7200


def test_scheduled_tick_claims_once_and_advances_persistently(ready):
    task = create_task(ready)
    now = ready.app.state.runner.clock()
    with ready.app.state.db.tx() as db:
        db.execute("UPDATE tasks SET next_at=?,due_at=? WHERE id=?", (now - 1, now - 1, task["id"]))
    ready.client.portal.call(ready.app.state.runner.tick)
    ready.client.portal.call(ready.app.state.runner.tick)
    runs = ready.client.get("/api/runs").json()["items"]
    assert len(runs) == 1
    assert runs[0]["source"] == "scheduled"
    await_run(ready, runs[0]["id"])
    assert ready.app.state.db.task(task["id"])["nextRunAt"]


def test_restart_marks_unfinished_and_skips_missed_instead_of_replaying(ready):
    task = create_task(ready)
    run, _ = ready.app.state.db.claim_run(task["id"], "manual")
    ready.app.state.db.update_run(run["id"], status="running", sent=True, sendState="sent")
    now = ready.app.state.runner.clock()
    with ready.app.state.db.tx() as db:
        db.execute("UPDATE tasks SET next_at=?,due_at=? WHERE id=?", (now - 3600, now - 3600, task["id"]))
    ready.app.state.runner.recover()
    assert ready.app.state.db.run(run["id"])["status"] == "interrupted"
    assert ready.app.state.db.run(run["id"])["sent"] is True
    assert any(r["status"] == "skipped" for r in ready.app.state.db.runs())
    assert not ready.factory.sends


def test_one_off_disables_itself_after_claim(ready):
    from datetime import timedelta
    task = create_task(ready, schedule="once", once=(datetime.now(UTC) + timedelta(minutes=5)).isoformat())
    now = ready.app.state.runner.clock()
    # When the scheduler reaches this instant, the one-off timestamp is in the past.
    ready.app.state.runner.clock = lambda: now + 600
    ready.client.portal.call(ready.app.state.runner.tick)
    assert ready.app.state.db.task(task["id"])["enabled"] is False
