import asyncio
import time

from conftest import await_run, create_task


def test_idle_connection_is_replaced_before_next_execution(ready):
    task = create_task(ready)
    service = ready.app.state.telegram
    old = service.clients[ready.account["id"]]
    service.last_used[ready.account["id"]] = time.monotonic() - 46
    result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert result["status"] == "replied"
    assert old.connected is False
    assert service.clients[ready.account["id"]] is not old
    assert len(ready.factory.sends) == 1


def test_pre_send_read_failure_evicts_transport_without_sending(ready):
    task = create_task(ready)
    service = ready.app.state.telegram
    old = service.clients[ready.account["id"]]

    async def failed_read(target):
        raise asyncio.TimeoutError()

    old.get_entity = failed_read
    result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert result["status"] == "error" and result["sendState"] == "not_sent"
    assert result["errorCode"] == "TELEGRAM_NETWORK"
    assert old.connected is False and ready.account["id"] not in service.clients
    assert not ready.factory.sends
    # Only a new explicit request can try this task again.
    new_result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert new_result["status"] == "replied"
    assert len(ready.factory.sends) == 1


def test_uncertain_send_is_not_replayed_when_transport_is_discarded(ready):
    task = create_task(ready)
    service = ready.app.state.telegram
    old = service.clients[ready.account["id"]]
    attempts = []

    async def uncertain_send(entity, text, **kwargs):
        attempts.append(text)
        raise asyncio.TimeoutError()

    old.send_message = uncertain_send
    result = await_run(ready, ready.client.post(f"/api/tasks/{task['id']}/run").json()["id"])
    assert result["sendState"] == "unknown"
    assert ready.account["id"] not in service.clients
    ready.client.portal.call(ready.app.state.runner.tick)
    assert len(attempts) == 1
