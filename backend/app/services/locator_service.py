"""Nearby healthcare facilities from OpenStreetMap (Overpass API) with Nominatim geocoding.

* Real provider data only. When the provider fails, the API returns an explicit error and never sample places.
* Usage-policy friendly: identifying User-Agent, results cached for 10 minutes, and Nominatim limited to
  1 request per second.
* User locations are used for the query only and are never stored.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import OrderedDict

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, ServiceUnavailableError

log = logging.getLogger("medicore.locator")

CATEGORIES = {
    "hospital": ['nwr["amenity"="hospital"]', 'nwr["healthcare"="hospital"]'],
    "pharmacy": ['nwr["amenity"="pharmacy"]', 'nwr["healthcare"="pharmacy"]'],
    "clinic": ['nwr["amenity"~"^(clinic|doctors)$"]', 'nwr["healthcare"~"^(clinic|doctor|centre)$"]'],
}
MAX_RADIUS_M = 25_000
MAX_RESULTS = 60
_CACHE_TTL = 600


class _TTLCache:
    def __init__(self, size=256):
        self._d: OrderedDict = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def get(self, k):
        with self._lock:
            v = self._d.get(k)
            if v and time.time() - v[0] < _CACHE_TTL:
                self._d.move_to_end(k)
                return v[1]
            self._d.pop(k, None)
            return None

    def set(self, k, val):
        with self._lock:
            self._d[k] = (time.time(), val)
            self._d.move_to_end(k)
            while len(self._d) > self._size:
                self._d.popitem(last=False)


_cache = _TTLCache()
_nominatim_lock = threading.Lock()
_last_nominatim = 0.0


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": get_settings().osm_user_agent}, timeout=httpx.Timeout(15, connect=5))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nominatim(path: str, params: dict) -> list[dict]:
    """GET against Nominatim, honouring its 1 request/second policy across threads."""
    global _last_nominatim
    with _nominatim_lock:
        wait = 1.0 - (time.time() - _last_nominatim)
        if wait > 0:
            time.sleep(wait)
        try:
            with _client() as c:
                r = c.get(f"{get_settings().nominatim_url}{path}", params={"format": "jsonv2", **params})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Nominatim failed: %s", exc)
            raise ServiceUnavailableError("We could not look up that place right now. Please try again in a minute.", code="geocoder_unavailable") from exc
        finally:
            _last_nominatim = time.time()


def geocode(query: str) -> dict:
    key = ("geo", query.strip().lower())
    if (hit := _cache.get(key)) is not None:
        return hit
    data = _nominatim("/search", {"q": query, "limit": 1, "addressdetails": 0})
    if not data:
        raise AppError(f"We could not find “{query}”. Try a city name or a full address.", code="place_not_found", status_code=404)
    out = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "display_name": data[0]["display_name"]}
    _cache.set(key, out)
    return out


def _address(tags: dict) -> str | None:
    parts = [" ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
             tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
    s = ", ".join(p for p in parts if p)
    return s or tags.get("addr:full")


def _kind(tags: dict) -> str:
    a, h = tags.get("amenity"), tags.get("healthcare")
    if a == "hospital" or h == "hospital":
        return "hospital"
    if a == "pharmacy" or h == "pharmacy":
        return "pharmacy"
    return "clinic"


_FAIL_TTL = 30
_last_failure: dict[str, float] = {}


def _overpass(query: str) -> list[dict]:
    """Try each configured Overpass endpoint in order (public instances are often overloaded).
    A failing endpoint is skipped for 30 s so a struggling provider is not hammered."""
    urls = [u.strip() for u in get_settings().overpass_url.split(",") if u.strip()]
    errors, rate_limited = [], False
    for url in urls:
        if time.time() - _last_failure.get(url, 0) < _FAIL_TTL:
            errors.append(f"{url}: recently failed")
            continue
        try:
            with _client() as c:
                r = c.post(url, data={"data": query})
            if r.status_code == 429:
                rate_limited = True
                raise httpx.HTTPStatusError("rate limited", request=r.request, response=r)
            r.raise_for_status()
            return r.json().get("elements", [])
        except (httpx.HTTPError, ValueError) as exc:
            _last_failure[url] = time.time()
            errors.append(f"{url}: {exc}")
            log.warning("Overpass endpoint failed: %s (%s)", url, exc)
    if rate_limited:
        raise ServiceUnavailableError("The map service is busy right now. Please try again in a minute.",
                                      code="locator_rate_limited")
    raise ServiceUnavailableError("We could not load nearby places right now. This is usually temporary, so please try again in a minute. "
                                  "If it is urgent, call your local emergency number.", code="locator_unavailable")


def _place(pid: str, osm_url: str, name: str, kind: str, plat: float, plon: float, lat: float, lon: float,
           tags: dict, address: str | None) -> dict:
    return {
        "id": pid, "name": name, "kind": kind, "lat": plat, "lon": plon,
        "distance_m": round(haversine_m(lat, lon, plat, plon)),
        "address": address, "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website"),
        "opening_hours": tags.get("opening_hours"), "emergency": tags.get("emergency"),
        "osm_url": osm_url,
        "directions_url": (f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_car"
                           f"&route={lat:.5f}%2C{lon:.5f}%3B{plat:.5f}%2C{plon:.5f}"),
    }


def _from_overpass(lat: float, lon: float, category: str, radius_m: int) -> list[dict]:
    sel = "".join(f"{s}(around:{radius_m},{lat:.6f},{lon:.6f});" for s in CATEGORIES[category])
    q = f"[out:json][timeout:20];({sel});out center tags {MAX_RESULTS * 2};"
    places = []
    for el in _overpass(q):
        tags = el.get("tags", {})
        plat = el.get("lat", el.get("center", {}).get("lat"))
        plon = el.get("lon", el.get("center", {}).get("lon"))
        name = tags.get("name") or tags.get("name:en")
        if plat is None or plon is None or not name:
            continue
        places.append(_place(f"{el['type']}/{el['id']}", f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                             name, _kind(tags), plat, plon, lat, lon, tags, _address(tags)))
    return places


NOMINATIM_TERMS = {"hospital": [("hospital", {"hospital"})], "pharmacy": [("pharmacy", {"pharmacy"})],
                   "clinic": [("clinic", {"clinic"}), ("doctors", {"doctors"})]}


def _from_nominatim(lat: float, lon: float, category: str, radius_m: int) -> list[dict]:
    """Fallback provider: Nominatim amenity search inside the radius' bounding box (max 40 per term)."""
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    box = f"{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f},{lat - dlat:.5f}"
    places = []
    for term, types in NOMINATIM_TERMS[category]:
        rows = _nominatim("/search", {"q": term, "viewbox": box, "bounded": 1, "limit": 40,
                                      "extratags": 1, "addressdetails": 1})
        for x in rows:
            if x.get("category") not in ("amenity", "healthcare") or x.get("type") not in types:
                continue
            plat, plon = float(x["lat"]), float(x["lon"])
            if haversine_m(lat, lon, plat, plon) > radius_m:
                continue
            name = x.get("name") or (x.get("display_name") or "").split(",")[0]
            a = x.get("address") or {}
            addr = ", ".join(p for p in (" ".join(q for q in (a.get("house_number"), a.get("road")) if q),
                                         a.get("suburb"), a.get("city") or a.get("town"), a.get("postcode")) if p)
            kind = "hospital" if x["type"] == "hospital" else "pharmacy" if x["type"] == "pharmacy" else "clinic"
            osm = f"{x.get('osm_type', 'node')}/{x.get('osm_id')}"
            places.append(_place(osm, f"https://www.openstreetmap.org/{osm}", name, kind, plat, plon, lat, lon,
                                 x.get("extratags") or {}, addr or None))
    return places


def search(lat: float, lon: float, category: str, radius_m: int) -> dict:
    """Overpass (complete tag data) first; Nominatim if every Overpass endpoint is down."""
    if category not in CATEGORIES:
        raise AppError("Unknown category", code="bad_category")
    radius_m = max(200, min(int(radius_m), MAX_RADIUS_M))
    key = ("near", round(lat, 3), round(lon, 3), category, radius_m)
    if (hit := _cache.get(key)) is not None:
        return hit
    provider, note = "overpass", None
    try:
        places = _from_overpass(lat, lon, category, radius_m)
    except ServiceUnavailableError as primary:
        log.warning("Overpass unavailable (%s); falling back to Nominatim", primary.code)
        try:
            places = _from_nominatim(lat, lon, category, radius_m)
        except ServiceUnavailableError:
            raise primary from None
        provider = "nominatim"
        note = ("The main map service is busy, so this list may be shorter than usual.")
    uniq, seen = [], set()
    for pl in sorted(places, key=lambda p: p["distance_m"]):
        k = (pl["name"].lower(), round(pl["lat"], 4), round(pl["lon"], 4))
        if k not in seen:
            seen.add(k)
            uniq.append(pl)
    out = {"center": {"lat": lat, "lon": lon}, "category": category, "radius_m": radius_m,
           "count": len(uniq[:MAX_RESULTS]), "places": uniq[:MAX_RESULTS], "provider": provider, "note": note,
           "attribution": "Data © OpenStreetMap contributors (ODbL). Details may be incomplete or out of date; "
                          "call ahead to confirm opening hours and services."}
    _cache.set(key, out)
    return out
