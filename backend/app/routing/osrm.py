"""Road-network travel times from OSRM (FR-4).

`travel_matrix` asks the OSRM `table` service for a duration matrix between all points,
with a pluggable pairwise cache so repeated queries over the same POIs don't hit OSRM
(NFR 3.2.1). If OSRM is unreachable the matrix falls back to a haversine estimate and
is clearly labelled `source="estimate"`, so the API can tell the user instead of
silently pretending to have road times.
"""

import logging
import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

LatLon = tuple[float, float]

# Estimate used only when OSRM is down: city roads are ~1.4x longer than a straight
# line and average ~22 km/h in Jaipur traffic.
_DETOUR_FACTOR = 1.4
_ESTIMATE_KMH = 22.0


def point_key(p: LatLon) -> str:
    return f"{p[0]:.5f},{p[1]:.5f}"


class MatrixCache(Protocol):
    def get_many(self, pairs: list[tuple[str, str]], profile: str) -> dict[tuple[str, str], float]: ...
    def put_many(self, values: dict[tuple[str, str], float], profile: str) -> None: ...


@dataclass
class TravelMatrix:
    minutes: list[list[int]]  # includes the traffic factor and per-leg overhead
    source: str  # "osrm" | "cache" | "estimate"


def haversine_km(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(d))


def _estimate_seconds(a: LatLon, b: LatLon) -> float:
    return haversine_km(a, b) * _DETOUR_FACTOR / _ESTIMATE_KMH * 3600


def _fetch_table_seconds(points: list[LatLon]) -> list[list[float]]:
    s = get_settings()
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = f"{s.osrm_url.rstrip('/')}/table/v1/{s.osrm_profile}/{coords}"
    r = httpx.get(url, params={"annotations": "duration"}, timeout=s.osrm_timeout_seconds)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM table error: {data.get('code')} {data.get('message')}")
    return [[(d if d is not None else _estimate_seconds(points[i], points[j])) for j, d in enumerate(row)]
            for i, row in enumerate(data["durations"])]


def travel_matrix(points: list[LatLon], cache: MatrixCache | None = None) -> TravelMatrix:
    s = get_settings()
    keys = [point_key(p) for p in points]
    n = len(points)
    pairs = [(keys[i], keys[j]) for i in range(n) for j in range(n) if i != j]

    seconds: dict[tuple[str, str], float] = {}
    source = "cache"
    if cache is not None:
        seconds = cache.get_many(pairs, s.osrm_profile)
    if len(seconds) < len(pairs):
        try:
            table = _fetch_table_seconds(points)
            seconds = {(keys[i], keys[j]): table[i][j] for i in range(n) for j in range(n) if i != j}
            source = "osrm"
            if cache is not None:
                cache.put_many(seconds, s.osrm_profile)
        except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
            log.warning("OSRM unavailable, using straight-line estimate: %s", exc)
            seconds = {(keys[i], keys[j]): _estimate_seconds(points[i], points[j])
                       for i in range(n) for j in range(n) if i != j}
            source = "estimate"

    minutes = [[0 if i == j else to_minutes(seconds[(keys[i], keys[j])]) for j in range(n)] for i in range(n)]
    return TravelMatrix(minutes=minutes, source=source)


def to_minutes(seconds: float) -> int:
    """Driving seconds -> planning minutes, adding traffic and parking/boarding overhead."""
    s = get_settings()
    return math.ceil(seconds * s.traffic_factor / 60) + s.leg_overhead_minutes


def route_geometry(points: list[LatLon]) -> tuple[list[LatLon], str]:
    """Road path through `points` in order, as [(lat, lon), ...]. Falls back to straight lines."""
    if len(points) < 2:
        return list(points), "none"
    s = get_settings()
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = f"{s.osrm_url.rstrip('/')}/route/v1/{s.osrm_profile}/{coords}"
    try:
        r = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=s.osrm_timeout_seconds)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(data.get("code"))
        return [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]], "osrm"
    except (httpx.HTTPError, RuntimeError, KeyError, IndexError, ValueError) as exc:
        log.warning("OSRM route geometry unavailable: %s", exc)
        return list(points), "straight"
