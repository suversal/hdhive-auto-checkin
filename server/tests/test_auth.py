import json
import os

from fastapi.testclient import TestClient

from shike.app import COOKIE, create_app
from shike.security import InstanceLock, Vault, check_password, password_hash

from conftest import initialize


def test_private_endpoints_require_auth(instance):
    for path in ("/api/state", "/api/accounts", "/api/tasks", "/api/runs", "/api/settings"):
        assert instance.client.get(path).status_code == 401
    assert instance.client.get("/api/auth/status").json()["initialized"] is False


def test_public_registration_is_closed_before_and_after_initialization(instance):
    for path in ("/api/auth/setup", "/api/auth/register"):
        assert instance.client.post(path, json={"password": "attacker-password"}).status_code == 404
    response = instance.client.post("/api/auth/login", json={"password": "any-password"})
    assert response.status_code == 503
    assert response.json()["code"] == "ADMIN_NOT_INITIALIZED"
    assert not instance.app.state.db.get("admin_password")
    response = initialize(instance)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    for path in ("/api/auth/setup", "/api/auth/register"):
        assert instance.client.post(path, json={"password": "attacker-password"}).status_code == 404
    assert instance.client.get("/api/state").json()["tasks"] == []
    assert not (instance.config.data_dir / "setup.token").exists()


def test_operator_initialization_cannot_overwrite_existing_administrator(instance):
    import pytest
    from shike.admin import initialize_admin
    initialize(instance)
    original = instance.app.state.db.get("admin_password")
    with pytest.raises(ValueError, match="不会覆盖"):
        initialize_admin(instance.app.state.db, "different-password", "different space")
    assert instance.app.state.db.get("admin_password") == original
    assert instance.app.state.db.get("settings")["workspace"] == "测试空间"


def test_csrf_and_origin_are_checked(instance):
    initialize(instance)
    body = instance.client.get("/api/settings").json()
    for key in ("hasApi", "hasNotificationToken", "lastSummaryStatus"):
        body.pop(key)
    assert instance.client.put("/api/settings", json=body, headers={"X-CSRF-Token": "incorrect"}).status_code == 403
    assert instance.client.put("/api/settings", json=body, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
    assert instance.client.put("/api/settings", json=body).status_code == 200


def test_login_logout_and_password_rotation_revoke_old_sessions(instance):
    initialize(instance)
    old_cookie = instance.client.cookies.get(COOKIE)
    assert instance.client.post("/api/auth/password", json={"current": "wrong", "password": "updated-password"}).status_code == 403
    rotated = instance.client.post("/api/auth/password", json={"current": "test-admin-password", "password": "updated-password"})
    assert rotated.status_code == 200
    instance.client.headers["X-CSRF-Token"] = rotated.json()["csrfToken"]
    assert instance.client.cookies.get(COOKIE) != old_cookie
    response = instance.client.get("/api/state", headers={"Cookie": COOKIE + "=" + old_cookie})
    assert response.status_code == 401
    assert instance.client.post("/api/auth/logout").status_code == 200
    assert instance.client.get("/api/state").status_code == 401
    assert instance.client.post("/api/auth/login", json={"password": "test-admin-password"}).status_code == 401
    assert instance.client.post("/api/auth/login", json={"password": "updated-password"}).status_code == 200


def test_bruteforce_rate_limit(instance):
    initialize(instance)  # The successful login also counts toward the eight-attempt limit.
    for _ in range(7):
        assert instance.client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert instance.client.post("/api/auth/login", json={"password": "wrong"}).status_code == 429


def test_password_hash_and_vault_are_not_plaintext(instance):
    initialize(instance)
    assert "test-admin-password" not in instance.app.state.db.path.read_bytes().decode(errors="ignore")
    hashed = password_hash("a proper password")
    assert check_password("a proper password", hashed)
    assert not check_password("wrong", hashed)
    secret = "credential-only-used-in-tests"
    encrypted = instance.app.state.vault.encrypt(secret)
    assert secret not in encrypted
    assert instance.app.state.vault.decrypt(encrypted) == secret
    assert os.stat(instance.config.data_dir / "master.key").st_mode & 0o777 == 0o600


def test_second_worker_is_rejected(instance):
    import pytest
    with pytest.raises(RuntimeError, match="单实例"):
        InstanceLock(instance.config.data_dir)


def test_validation_never_echoes_credentials(instance):
    initialize(instance)
    response = instance.client.put("/api/settings/telegram", json={"apiId": 123, "apiHash": "do-not-echo-this-secret"})
    assert response.status_code == 422
    assert "do-not-echo-this-secret" not in response.text


def test_setup_state_and_settings_persist(instance):
    initialize(instance)
    assert instance.app.state.db.get("settings")["workspace"] == "测试空间"
    # Instantiate the repository again, as a restart would, with the original key.
    from shike.database import Database
    assert Database(instance.config.data_dir).get("admin_password")
    assert Vault(instance.config.data_dir).decrypt(instance.app.state.vault.encrypt("still-decrypts")) == "still-decrypts"
