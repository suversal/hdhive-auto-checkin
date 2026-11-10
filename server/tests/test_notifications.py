import time

from shike.database import new_id

from conftest import create_task


def test_summary_counts_all_records_and_is_not_sent_twice(ready):
    task = create_task(ready, notify="summary")
    db = ready.app.state.db
    run, _ = db.claim_run(task["id"], "manual")
    db.update_run(run["id"], status="sent", sent=True, sendState="sent")
    with db.tx(True) as connection:
        seed = list(connection.execute("SELECT * FROM runs WHERE id=?", (run["id"],)).fetchone())
        rows = []
        for index in range(1001):
            item = seed.copy()
            item[0], item[4], item[8] = new_id("run"), "error" if index == 0 else "sent", time.time()
            rows.append(item)
        connection.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.set("settings", {**db.get("settings"), "summaryTime": "00:00"})
    ready.client.portal.call(ready.app.state.runner.maybe_summary)
    ready.client.portal.call(ready.app.state.runner.maybe_summary)
    assert len(ready.factory.sends) == 1
    assert "共 1002 条记录，1 次需要留意" in ready.factory.sends[0][0]
    assert db.get("last_summary_status") == "sent"
    state = ready.client.get("/api/state").json()
    assert len(state["runs"]) == 200
    assert state["summary"] == {"todayExecuted": 1002, "attention": 1}
