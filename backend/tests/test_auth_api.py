import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.db.database as db_module

# HTTPS base URL so the Secure session cookie is stored and sent back.
client = TestClient(app, base_url="https://testserver")
bob_client = TestClient(app, base_url="https://testserver")


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
    assert "funcassist_session" in resp1.cookies
    assert "token" not in data1
    assert data1["user"]["role"] == "admin"
    assert data1["user"]["username"] == "adminuser"
    assert "password_hash" not in data1["user"]

    # 2. Second user registers -> becomes pending without token
    resp2 = bob_client.post(
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
    assert "funcassist_session" not in resp2.cookies
    bob_id = data2["user"]["id"]

    # 3. Bob tries to login while pending -> 403 Forbidden
    login_fail = bob_client.post(
        "/api/auth/login",
        json={"username": "testerbob", "password": "TesterPassword123!"},
    )
    assert login_fail.status_code == 403
    assert "pendiente" in login_fail.json()["detail"].lower()

    # 4. Admin lists access requests
    reqs_resp = client.get(
        "/api/auth/access-requests",
    )
    assert reqs_resp.status_code == 200
    pending_list = reqs_resp.json()["requests"]
    assert len(pending_list) == 1
    assert pending_list[0]["username"] == "testerbob"

    # 5. Admin approves Bob's request
    approve_resp = client.post(
        f"/api/auth/access-requests/{bob_id}/approve",
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # 6. Bob can now login successfully
    login_bob = bob_client.post(
        "/api/auth/login",
        json={"username": "testerbob", "password": "TesterPassword123!"},
    )
    assert login_bob.status_code == 200
    bob_data = login_bob.json()
    assert bob_data["status"] == "approved"
    assert "funcassist_session" in login_bob.cookies

    # 7. Bob checks /me
    me_resp = bob_client.get("/api/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == "testerbob"

    # 8. Bob cannot approve requests (not admin)
    forbidden_resp = bob_client.get("/api/auth/access-requests")
    assert forbidden_resp.status_code == 403

    # 9. Non-authenticated access to /me fails
    unauth_resp = TestClient(app, base_url="https://testserver").get("/api/auth/me")
    assert unauth_resp.status_code == 401

    # 10. Bearer headers are not accepted (cookie-only session)
    bearer_resp = TestClient(app, base_url="https://testserver").get(
        "/api/auth/me", headers={"Authorization": "Bearer whatever"}
    )
    assert bearer_resp.status_code == 401

    # 11. Logout clears the session cookie
    assert bob_client.post("/api/auth/logout").status_code == 204
    assert bob_client.get("/api/auth/me").status_code == 401


