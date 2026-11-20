"""Production-hardening behaviour: session revocation, config validation, headers, readiness, rate limits."""
import pytest

from app.core.config import ConfigError, Settings, validate_production


def test_password_change_revokes_old_sessions(client, auth_headers):
    old = auth_headers("rev@example.com", "Passw0rd!")
    second_device = {"Authorization": "Bearer " + client.post(
        "/api/auth/login", json={"email": "rev@example.com", "password": "Passw0rd!"}).json()["access_token"]}
    r = client.post("/api/auth/change-password", headers=old,
                    json={"current_password": "Passw0rd!", "new_password": "N3wPassword"})
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=second_device).status_code == 401
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_tokens_without_password_binding_are_rejected(client, auth_headers, db_session):
    from app.core.security import create_access_token
    from app.models import User

    auth_headers("legacy@example.com")
    uid = db_session.query(User).filter_by(email="legacy@example.com").one().id
    legacy = create_access_token(uid)            # no pwv claim
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401


@pytest.mark.parametrize("override, fragment", [
    ({"jwt_secret_key": "change-me"}, "JWT_SECRET_KEY"),
    ({"database_url": "sqlite:///x.db"}, "PostgreSQL"),
    ({"cors_origins": "*"}, "CORS_ORIGINS"),
    ({"redis_url": None, "web_concurrency": 2}, "REDIS_URL"),
])
def test_production_config_refuses_unsafe_settings(override, fragment):
    good = dict(app_env="production", jwt_secret_key="x" * 48, database_url="postgresql+psycopg://u:p@db/medicore",
                cors_origins="https://medicore.example", redis_url="redis://redis:6379/0", web_concurrency=2,
                rate_limit_enabled=True)
    assert validate_production(Settings(**good)) == []
    problems = validate_production(Settings(**{**good, **override}))
    assert any(fragment in p for p in problems)


def test_get_settings_raises_in_unsafe_production(monkeypatch):
    from app.core import config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.db")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(ConfigError):
            config.get_settings()
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


def test_security_headers_and_request_id(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert len(r.headers["x-request-id"]) >= 8
    echoed = client.get("/api/health", headers={"X-Request-ID": "abc123def456"})
    assert echoed.headers["x-request-id"] == "abc123def456"
    bad = client.get("/api/health", headers={"X-Request-ID": "<script>"})
    assert bad.headers["x-request-id"] != "<script>"


def test_readiness_reports_dependencies(client, monkeypatch):
    r = client.get("/api/ready")
    body = r.json()
    assert set(body["checks"]) == {"database", "risk_model", "knowledge_base", "llm"}
    assert r.status_code == (200 if body["checks"]["risk_model"] == "ok" else 503)


def test_rate_limit_uses_error_envelope(client):
    from app.core.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    try:
        codes = [client.post("/api/auth/forgot-password", json={"email": "x@example.com"}).status_code for _ in range(7)]
        assert 429 in codes
        r = client.post("/api/auth/forgot-password", json={"email": "x@example.com"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and r.headers["retry-after"]
    finally:
        limiter.reset()
        limiter.enabled = False


def test_upload_and_errors_do_not_leak_internals(client, auth_headers, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import report_service

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /etc/passwd")

    monkeypatch.setattr(report_service, "analyse_upload", boom)
    h = auth_headers()
    real = TestClient(app, raise_server_exceptions=False)   # what a browser actually receives
    r = real.post("/api/reports/upload", headers=h, files={"file": ("r.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 500 and "secret" not in r.text and r.json()["error"]["code"] == "internal_error"
