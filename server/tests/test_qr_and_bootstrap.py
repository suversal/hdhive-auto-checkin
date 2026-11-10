import time
from urllib.parse import parse_qs, urlparse

from shike.security import setup_link


def test_quick_setup_link_keeps_token_out_of_http_query_and_path():
    secret = "test-setup-value-with+special&symbols"
    parsed = urlparse(setup_link("http://127.0.0.1:8787", secret))
    assert secret not in parsed.query
    assert secret not in parsed.path
    assert parse_qs(parsed.fragment.split("?", 1)[1])["bootstrap"][0] == secret


def qr_status(instance, login_id, expected):
    for _ in range(100):
        result = instance.client.get("/api/accounts/login/" + login_id)
        if result.json().get("step") == expected:
            return result.json()
        time.sleep(.01)
    raise AssertionError("QR state did not reach " + expected)


def test_qr_login_returns_image_and_persists_verified_session(ready):
    started = ready.client.post("/api/accounts/login/qr", json={"name": "主账号", "accountId": ready.account["id"]})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["qrImage"].startswith("data:image/png;base64,")
    assert "tg://" not in started.text
    ready.client.portal.call(ready.factory.qr_event.set)
    completed = qr_status(ready, body["loginId"], "complete")
    assert completed["account"]["status"] == "connected"
    assert len(ready.app.state.db.accounts()) == 1


def test_qr_preserves_two_factor_authentication(ready):
    ready.factory.two_factor = True
    body = ready.client.post("/api/accounts/login/qr", json={"name": "主账号", "accountId": ready.account["id"]}).json()
    ready.client.portal.call(ready.factory.qr_event.set)
    qr_status(ready, body["loginId"], "password")
    response = ready.client.post(f"/api/accounts/login/{body['loginId']}/password", json={"password": "test-two-factor-password"})
    assert response.json()["step"] == "complete"


def test_qr_cannot_be_read_by_another_admin_session(ready):
    body = ready.client.post("/api/accounts/login/qr", json={"name": "主账号"}).json()
    logged = ready.client.post("/api/auth/login", json={"password": "test-admin-password"}).json()
    ready.client.headers["X-CSRF-Token"] = logged["csrfToken"]
    assert ready.client.get("/api/accounts/login/" + body["loginId"]).status_code == 410


def test_qr_cancel_disconnects_pending_client(ready):
    body = ready.client.post("/api/accounts/login/qr", json={"name": "新账号"}).json()
    pending = ready.app.state.telegram.pending[body["loginId"]]
    assert ready.client.delete("/api/accounts/login/" + body["loginId"]).status_code == 200
    assert body["loginId"] not in ready.app.state.telegram.pending
    assert pending.client.connected is False


def test_chunked_requests_are_bounded_even_without_content_length(instance):
    response = instance.client.post("/api/auth/login", content=(b"x" * 65536 for _ in range(17)), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_logout_revokes_pending_qr_login(ready):
    body = ready.client.post("/api/accounts/login/qr", json={"name": "新账号"}).json()
    pending = ready.app.state.telegram.pending[body["loginId"]]
    assert ready.client.post("/api/auth/logout").status_code == 200
    assert body["loginId"] not in ready.app.state.telegram.pending
    assert pending.client.connected is False
