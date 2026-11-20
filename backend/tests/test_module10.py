"""Reminders, settings/privacy and locator tests."""
from datetime import date, timedelta

import httpx
import pytest

from app.services import locator_service

TODAY = date.today()


def reminder(**kw):
    body = {"medication_name": "Metformin", "dosage_note": "as prescribed: 500 mg", "frequency": "daily",
            "times": ["20:00", "08:00"], "start_date": TODAY.isoformat(), "end_date": None, "is_active": True}
    body.update(kw)
    return body


# ------------------------------------------------------------------ reminders
def test_reminder_crud_schedule_and_logging(client, auth_headers):
    h = auth_headers()
    r = client.post("/api/reminders", json=reminder(), headers=h)
    assert r.status_code == 201, r.text
    rem = r.json()
    assert rem["times"] == ["08:00", "20:00"] and rem["status"] == "active" and rem["days_of_week"] is None

    sched = client.get(f"/api/reminders/schedule?day={TODAY}", headers=h).json()
    assert [(d["scheduled_time"], d["status"]) for d in sched] == [("08:00", "pending"), ("20:00", "pending")]

    log = {"scheduled_date": TODAY.isoformat(), "scheduled_time": "08:00", "status": "taken"}
    assert client.post(f"/api/reminders/{rem['id']}/events", json=log, headers=h).status_code == 201
    # re-logging the same dose updates it instead of duplicating
    client.post(f"/api/reminders/{rem['id']}/events", json={**log, "status": "skipped"}, headers=h)
    sched = client.get(f"/api/reminders/schedule?day={TODAY}", headers=h).json()
    assert sched[0]["status"] == "skipped"
    hist = client.get("/api/reminders/history", headers=h).json()
    assert len(hist) == 1 and hist[0]["medication_name"] == "Metformin"

    # a time that is not in the schedule cannot be logged
    bad = client.post(f"/api/reminders/{rem['id']}/events", json={**log, "scheduled_time": "13:00"}, headers=h)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "not_scheduled"

    upd = client.put(f"/api/reminders/{rem['id']}", json=reminder(is_active=False), headers=h).json()
    assert upd["status"] == "paused"
    assert client.get(f"/api/reminders/schedule?day={TODAY}", headers=h).json() == []
    assert client.delete(f"/api/reminders/{rem['id']}", headers=h).status_code == 204
    assert client.get("/api/reminders", headers=h).json() == []


def test_reminder_frequencies():
    from types import SimpleNamespace

    from app.api.reminders import occurs_on

    start = date(2026, 1, 5)  # a Monday
    r = SimpleNamespace(is_active=True, start_date=start, end_date=date(2026, 1, 20), frequency="every_other_day",
                        days_of_week=None)
    assert occurs_on(r, start) and not occurs_on(r, start + timedelta(1)) and occurs_on(r, start + timedelta(2))
    assert not occurs_on(r, date(2026, 1, 4)) and not occurs_on(r, date(2026, 1, 22))
    r.frequency, r.days_of_week = "weekly", [0, 3]
    assert occurs_on(r, start) and occurs_on(r, date(2026, 1, 8)) and not occurs_on(r, date(2026, 1, 6))
    r.frequency = "as_needed"
    assert not occurs_on(r, start)


def test_reminder_validation(client, auth_headers):
    h = auth_headers()
    cases = [
        reminder(times=[]),                                            # scheduled without times
        reminder(times=["25:00"]),                                     # invalid time
        reminder(times=["08:00", "08:00"]),                            # duplicate time
        reminder(frequency="weekly"),                                  # weekly without days
        reminder(end_date=(TODAY - timedelta(days=1)).isoformat()),    # end before start
        reminder(medication_name="   "),                               # blank name
        reminder(frequency="hourly"),                                  # unsupported
    ]
    for body in cases:
        assert client.post("/api/reminders", json=body, headers=h).status_code == 422, body
    ok = client.post("/api/reminders", json=reminder(frequency="as_needed", times=[]), headers=h)
    assert ok.status_code == 201


def test_as_needed_logging(client, auth_headers):
    h = auth_headers()
    rid = client.post("/api/reminders", json=reminder(frequency="as_needed", times=[]), headers=h).json()["id"]
    r = client.post(f"/api/reminders/{rid}/events", headers=h,
                    json={"scheduled_date": TODAY.isoformat(), "scheduled_time": "14:35", "status": "taken"})
    assert r.status_code == 201
    future = (TODAY + timedelta(days=5)).isoformat()
    r = client.post(f"/api/reminders/{rid}/events", headers=h,
                    json={"scheduled_date": future, "scheduled_time": "14:35", "status": "taken"})
    assert r.status_code == 400


def test_reminders_are_private(client, auth_headers):
    a, b = auth_headers("a@example.com"), auth_headers("b@example.com")
    rid = client.post("/api/reminders", json=reminder(), headers=a).json()["id"]
    assert client.get("/api/reminders", headers=b).json() == []
    assert client.put(f"/api/reminders/{rid}", json=reminder(), headers=b).status_code == 404
    assert client.delete(f"/api/reminders/{rid}", headers=b).status_code == 404
    log = {"scheduled_date": TODAY.isoformat(), "scheduled_time": "08:00", "status": "taken"}
    assert client.post(f"/api/reminders/{rid}/events", json=log, headers=b).status_code == 404


# ------------------------------------------------------------------ settings / privacy
def test_profile_update_and_validation(client, auth_headers):
    h = auth_headers()
    p = client.get("/api/users/me/profile", headers=h).json()
    assert p["full_name"] == "Alice" and p["data_retention_days"] is None
    r = client.put("/api/users/me/profile", headers=h,
                   json={"full_name": " Alice B ", "notify_reminders": False, "data_retention_days": 90})
    assert r.status_code == 200 and r.json()["full_name"] == "Alice B" and r.json()["data_retention_days"] == 90
    bad = client.put("/api/users/me/profile", headers=h, json={"notify_reminders": True, "data_retention_days": 7})
    assert bad.status_code == 422


def test_retention_deletes_old_history_only(client, auth_headers, db_session):
    from app.models import ActivityLog, Conversation, Reminder, User
    from app.models.entities import utcnow

    h = auth_headers()
    user = db_session.query(User).one()
    old = utcnow() - timedelta(days=200)
    db_session.add_all([Conversation(user_id=user.id, title="old", created_at=old, updated_at=old),
                        Conversation(user_id=user.id, title="new")])
    db_session.commit()
    client.post("/api/reminders", json=reminder(), headers=h)
    client.put("/api/users/me/profile", headers=h, json={"notify_reminders": True, "data_retention_days": 180})
    titles = [c.title for c in db_session.query(Conversation).all()]
    assert titles == ["new"]
    assert db_session.query(Reminder).count() == 1   # schedules are not history
    assert db_session.query(ActivityLog).count() >= 1


def test_export_purge_and_delete_account(client, auth_headers, db_session):
    from app.models import Reminder, User

    h = auth_headers("del@example.com", "Passw0rd!")
    client.post("/api/reminders", json=reminder(), headers=h)
    exp = client.get("/api/users/me/export", headers=h)
    assert exp.status_code == 200 and "attachment" in exp.headers["content-disposition"]
    data = exp.json()
    assert data["account"]["email"] == "del@example.com" and data["reminders"][0]["medication_name"] == "Metformin"
    assert "hashed_password" not in exp.text

    assert client.post("/api/users/me/purge", json={"scope": "reminders"}, headers=h).json()["deleted"] == 1
    assert db_session.query(Reminder).count() == 0

    wrong = client.request("DELETE", "/api/users/me", headers=h, json={"password": "nope", "confirm": "DELETE"})
    assert wrong.status_code == 400
    no_confirm = client.request("DELETE", "/api/users/me", headers=h, json={"password": "Passw0rd!", "confirm": "yes"})
    assert no_confirm.status_code == 422
    ok = client.request("DELETE", "/api/users/me", headers=h, json={"password": "Passw0rd!", "confirm": "DELETE"})
    assert ok.status_code == 204
    assert db_session.query(User).filter_by(email="del@example.com").count() == 0
    assert client.get("/api/auth/me", headers=h).status_code == 401


# ------------------------------------------------------------------ locator (provider mocked; no live calls)
OVERPASS = {"elements": [
    {"type": "node", "id": 1, "lat": 12.98, "lon": 77.60,
     "tags": {"amenity": "hospital", "name": "Far Hospital", "phone": "+91 1", "addr:street": "Main Rd"}},
    {"type": "way", "id": 2, "center": {"lat": 12.972, "lon": 77.595},
     "tags": {"amenity": "hospital", "name": "Near Hospital", "emergency": "yes"}},
    {"type": "node", "id": 3, "lat": 12.973, "lon": 77.596, "tags": {"amenity": "hospital"}},   # unnamed: dropped
    {"type": "node", "id": 4, "lat": 12.972, "lon": 77.595, "tags": {"amenity": "hospital", "name": "Near Hospital"}},
]}


NOMINATIM_POIS = [
    {"category": "amenity", "type": "hospital", "name": "Fallback Hospital", "lat": "12.9720", "lon": "77.5950",
     "osm_type": "node", "osm_id": 9, "extratags": {"phone": "+91 2"}, "address": {"road": "MG Road", "city": "Bengaluru"}},
    {"category": "amenity", "type": "hospital", "name": "Outside Radius", "lat": "13.5", "lon": "78.5",
     "osm_type": "node", "osm_id": 10, "extratags": {}},
    {"category": "shop", "type": "chemist", "name": "Not a hospital", "lat": "12.9718", "lon": "77.5947",
     "osm_type": "node", "osm_id": 11, "extratags": {}},
]


@pytest.fixture()
def osm(monkeypatch):
    calls = {"overpass": 0, "nominatim": 0, "mode": "ok"}

    def handler(request: httpx.Request):
        if "nominatim" in str(request.url):
            calls["nominatim"] += 1
            if calls["mode"] == "all_down":
                return httpx.Response(503)
            if "Nowhere" in str(request.url):
                return httpx.Response(200, json=[])
            if "viewbox" in str(request.url):   # amenity search used as the fallback provider
                return httpx.Response(200, json=NOMINATIM_POIS)
            return httpx.Response(200, json=[{"lat": "12.9716", "lon": "77.5946", "display_name": "Bengaluru"}])
        calls["overpass"] += 1
        if calls["mode"] in ("down", "all_down") or (calls["mode"] == "primary_down" and "primary" in str(request.url)):
            return httpx.Response(504)
        if calls["mode"] == "busy":
            return httpx.Response(429)
        assert b"around" in request.content
        return httpx.Response(200, json=OVERPASS)

    monkeypatch.setattr(locator_service, "_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=5))
    monkeypatch.setattr(locator_service, "_cache", locator_service._TTLCache())
    monkeypatch.setattr(locator_service, "_last_nominatim", 0.0)
    monkeypatch.setattr(locator_service, "_last_failure", {})
    monkeypatch.setattr(locator_service.get_settings(), "overpass_url", "https://primary.test/api,https://mirror.test/api")
    return calls


def test_locator_returns_normalised_sorted_places(client, auth_headers, osm):
    h = auth_headers()
    r = client.get("/api/locations?lat=12.9716&lon=77.5946&category=hospital&radius_m=3000", headers=h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert [p["name"] for p in b["places"]] == ["Near Hospital", "Far Hospital"]       # deduped, sorted, unnamed dropped
    near = b["places"][0]
    assert near["distance_m"] < b["places"][1]["distance_m"] and near["emergency"] == "yes"
    assert near["directions_url"].startswith("https://www.openstreetmap.org/directions")
    assert "OpenStreetMap" in b["attribution"]
    client.get("/api/locations?lat=12.9716&lon=77.5946&category=hospital&radius_m=3000", headers=h)
    assert osm["overpass"] == 1                                                          # cached


def test_locator_geocodes_place_names(client, auth_headers, osm):
    h = auth_headers()
    r = client.get("/api/locations?q=Bengaluru&category=pharmacy", headers=h)
    assert r.status_code == 200 and r.json()["place"]["display_name"] == "Bengaluru"
    assert client.get("/api/locations?q=Nowhere%20Land", headers=h).status_code == 404
    assert client.get("/api/locations?category=clinic", headers=h).status_code == 400   # no location given


def test_locator_falls_back_to_mirror(client, auth_headers, osm):
    osm["mode"] = "primary_down"
    r = client.get("/api/locations?lat=12.9716&lon=77.5946", headers=auth_headers())
    assert r.status_code == 200 and r.json()["count"] == 2
    assert osm["overpass"] == 2       # primary failed, mirror answered


def test_locator_falls_back_to_nominatim_when_overpass_is_down(client, auth_headers, osm):
    osm["mode"] = "down"
    r = client.get("/api/locations?lat=12.9716&lon=77.5946&category=hospital&radius_m=3000", headers=auth_headers())
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["provider"] == "nominatim" and b["note"]
    assert [p["name"] for p in b["places"]] == ["Fallback Hospital"]       # out-of-radius and non-hospital dropped
    assert b["places"][0]["phone"] == "+91 2" and "MG Road" in b["places"][0]["address"]


def test_locator_reports_failure_when_all_providers_are_down(client, auth_headers, osm):
    osm["mode"] = "all_down"
    r = client.get("/api/locations?lat=1&lon=1", headers=auth_headers())
    assert r.status_code == 503 and r.json()["error"]["code"] == "locator_unavailable"


def test_locator_requires_auth_and_valid_coords(client, auth_headers, osm):
    assert client.get("/api/locations?lat=1&lon=1").status_code == 401
    assert client.get("/api/locations?lat=200&lon=1", headers=auth_headers()).status_code == 422


def test_haversine():
    assert locator_service.haversine_m(0, 0, 0, 1) == pytest.approx(111_195, rel=1e-3)
