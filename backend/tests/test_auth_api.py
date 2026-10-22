from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.db.database as db_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db():
    from tests.fake_session import GLOBAL_FAKE_STORAGE, fake_async_db, fake_sync_db
    GLOBAL_FAKE_STORAGE.clear()
    db_module.set_session_override(fake_async_db)
    db_module.set_sync_session_override(fake_sync_db)
    yield
    GLOBAL_FAKE_STORAGE.clear()
    db_module.set_session_override(None)
    db_module.set_sync_session_override(None)


def test_auth_full_lifecycle():
    # 1. First user registers -> becomes admin and approved
    resp1 = client.post(
        "/api/auth/register",
        json={
            "username": "adminuser",
            "password": "AdminPassword123!",
            "email": "admin@example.com",
            "full_name": "Admin Principal",
        },
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["status"] == "approved"
    assert data1["token"] is not None
    assert data1["user"]["role"] == "admin"
    assert data1["user"]["username"] == "adminuser"
    assert "password_hash" not in data1["user"]

    admin_token = data1["token"]

    # 2. Second user registers -> becomes pending without token
    resp2 = client.post(
        "/api/auth/register",
        json={
            "username": "testerbob",
            "password": "TesterPassword123!",
            "email": "bob@example.com",
            "full_name": "Bob Tester",
            "role": "qa",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "pending"
    assert data2["token"] is None
    bob_id = data2["user"]["id"]

    # 3. Bob tries to login while pending -> 403 Forbidden
    login_fail = client.post(
        "/api/auth/login",
        json={"username": "testerbob", "password": "TesterPassword123!"},
    )
    assert login_fail.status_code == 403
    assert "pendiente" in login_fail.json()["detail"].lower()

    # 4. Admin lists access requests
    reqs_resp = client.get(
        "/api/auth/access-requests",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reqs_resp.status_code == 200
    pending_list = reqs_resp.json()["requests"]
    assert len(pending_list) == 1
    assert pending_list[0]["username"] == "testerbob"

    # 5. Admin approves Bob's request
    approve_resp = client.post(
        f"/api/auth/access-requests/{bob_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # 6. Bob can now login successfully
    login_bob = client.post(
        "/api/auth/login",
        json={"username": "testerbob", "password": "TesterPassword123!"},
    )
    assert login_bob.status_code == 200
    bob_data = login_bob.json()
    assert bob_data["token"] is not None
    bob_token = bob_data["token"]

    # 7. Bob checks /me
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == "testerbob"

    # 8. Bob cannot approve requests (not admin)
    forbidden_resp = client.get(
        "/api/auth/access-requests",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert forbidden_resp.status_code == 403

    # 9. Non-authenticated access to /me fails
    unauth_resp = client.get("/api/auth/me")
    assert unauth_resp.status_code == 401


def test_auth_validations():
    # 1. Username > 20 characters should fail
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "usuariodemasiadolargoquesuperaveintecaracteres",
            "password": "ValidPassword123!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 2. Full name > 80 characters should fail
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "ValidPassword123!",
            "email": "user@example.com",
            "full_name": "A" * 81,
        },
    )
    assert resp.status_code in (400, 422)

    # 3. Invalid email should fail
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "ValidPassword123!",
            "email": "correo-invalido-sin-arroba",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 4. Weak password: less than 10 characters
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "Short1!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 5. Weak password: missing uppercase
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "lowercase123!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 6. Weak password: missing number
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "NoDigitsPassword!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 7. Weak password: missing special character
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "userok",
            "password": "NoSpecialChar123",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)

    # 8. Username with spaces should fail
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "Funcional Test",
            "password": "ValidPassword123!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)
    assert "El nombre de usuario admite solo letras y números" in resp.text

    # 9. Username with special characters should fail
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "user_test",
            "password": "ValidPassword123!",
            "email": "user@example.com",
            "full_name": "Nombre Valido",
        },
    )
    assert resp.status_code in (400, 422)
    assert "El nombre de usuario admite solo letras y números" in resp.text

    # 10. Valid registration passes
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "validuser20",
            "password": "StrongPassword123!",
            "email": "valid@example.com",
            "full_name": "Usuario Valido",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in ("approved", "pending")
