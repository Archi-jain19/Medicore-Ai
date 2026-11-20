from datetime import datetime, timedelta, timezone

import jwt

from app.core.security import hash_password, verify_password
from app.models import User


def test_password_hashing_roundtrip():
    h = hash_password("Secret123")
    assert h != "Secret123" and h.startswith("$2")
    assert verify_password("Secret123", h)
    assert not verify_password("wrong", h)


def test_register_stores_hash_not_plaintext(client, db_session):
    r = client.post("/api/auth/register", json={"email": "Bob@Example.com", "password": "Passw0rd!"})
    assert r.status_code == 201
    user = db_session.query(User).one()
    assert user.email == "bob@example.com"
    assert "Passw0rd!" not in user.hashed_password
    assert verify_password("Passw0rd!", user.hashed_password)


def test_register_duplicate_email_conflict(client):
    body = {"email": "dup@example.com", "password": "Passw0rd!"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    r = client.post("/api/auth/register", json={**body, "email": "DUP@example.com"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_register_validation_errors(client):
    r = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short"})
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"email", "password"} <= fields
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "onlyletters"})
    assert r.status_code == 422


def test_login_and_me(client, auth_headers):
    auth_headers("carol@example.com", "Passw0rd!")
    r = client.post("/api/auth/login", json={"email": "carol@example.com", "password": "Passw0rd!"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "carol@example.com"
    assert me.json()["full_name"] == "Alice"


def test_login_wrong_password(client, auth_headers):
    auth_headers("dave@example.com", "Passw0rd!")
    r = client.post("/api/auth/login", json={"email": "dave@example.com", "password": "nope1234"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope1234"})
    assert r.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = jwt.encode(
        {"sub": "1", "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        "test-secret-key-for-pytest-only-000000",
        algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and "educational" in r.json()["disclaimer"]


def test_password_reset_flow(client, auth_headers, db_session, monkeypatch):
    from app.core.security import create_reset_token
    from app.services import email_service

    sent = {}
    monkeypatch.setattr(email_service, "send_password_reset", lambda to, link: sent.update(to=to, link=link) or True)
    auth_headers("erin@example.com", "Passw0rd!")
    # Unknown email: same generic response, nothing sent
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and not sent
    r = client.post("/api/auth/forgot-password", json={"email": "erin@example.com"})
    assert r.status_code == 200 and sent["to"] == "erin@example.com"
    token = sent["link"].split("token=")[1]
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "NewPassw0rd"})
    assert r.status_code == 200
    # Token is single-use: it is bound to the previous password hash
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Another1pw"})
    assert r.status_code == 401
    assert client.post("/api/auth/login", json={"email": "erin@example.com", "password": "NewPassw0rd"}).status_code == 200
    # An access token cannot be used as a reset token and vice versa
    user = db_session.query(User).filter_by(email="erin@example.com").one()
    reset = create_reset_token(user.id, user.hashed_password)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {reset}"}).status_code == 401


def test_change_password(client, auth_headers):
    h = auth_headers("frank@example.com", "Passw0rd!")
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": "wrong", "new_password": "NewPassw0rd"})
    assert r.status_code == 400
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": "Passw0rd!", "new_password": "NewPassw0rd"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": "frank@example.com", "password": "NewPassw0rd"}).status_code == 200
