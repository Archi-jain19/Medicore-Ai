from typing import Literal

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.services import locator_service

router = APIRouter(tags=["locator"])


@router.get("/locations")
@limiter.limit("20/minute")
def locations(
    request: Request,
    user: CurrentUser,
    category: Literal["hospital", "pharmacy", "clinic"] = "hospital",
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    q: str | None = Query(None, min_length=2, max_length=120, description="Place name to search around"),
    radius_m: int = Query(5000, ge=200, le=locator_service.MAX_RADIUS_M),
):
    """Nearby facilities from OpenStreetMap. Provide either lat/lon or a place name `q`.
    Coordinates are used only for this query and are not stored."""
    place = None
    if lat is None or lon is None:
        if not q:
            raise AppError("Tell us where to look: allow location access, or type a city or address.", code="location_required")
        place = locator_service.geocode(q)
        lat, lon = place["lat"], place["lon"]
    result = locator_service.search(lat, lon, category, radius_m)
    return {**result, "place": place}
