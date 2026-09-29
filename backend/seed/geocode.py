"""Cross-check seed coordinates against OpenStreetMap Nominatim.

    python -m seed.geocode              # report POIs whose coordinates look off
    python -m seed.geocode --write      # also update jaipur.json with Nominatim's position

Respects Nominatim's usage policy: 1 request per second with an identifying User-Agent.
"""

import json
import sys
import time
from pathlib import Path

import httpx

from app.routing.osrm import haversine_km

SEED = Path(__file__).with_name("jaipur.json")
URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "TripSolve/0.1 (BIT Mesra minor project)"}
THRESHOLD_KM = 0.5


def main(write: bool) -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    city = data["city"]["name"]
    changed = 0
    for poi in data["pois"]:
        query = f"{poi['name'].split(' (')[0]}, {city}"
        r = httpx.get(URL, params={"q": query, "format": "json", "limit": 1}, headers=HEADERS, timeout=15)
        time.sleep(1.1)
        hits = r.json() if r.status_code == 200 else []
        if not hits:
            print(f"?  {poi['name']:<40} not found on Nominatim; check manually")
            continue
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        d = haversine_km((poi["lat"], poi["lon"]), (lat, lon))
        flag = "!!" if d > THRESHOLD_KM else "ok"
        print(f"{flag} {poi['name']:<40} {d:6.2f} km off  (nominatim: {lat:.5f}, {lon:.5f})")
        if write and d > THRESHOLD_KM:
            poi["lat"], poi["lon"] = round(lat, 5), round(lon, 5)
            changed += 1
    if write and changed:
        SEED.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {changed} POIs in {SEED.name}; re-run `python -m seed.seed`.")


if __name__ == "__main__":
    main("--write" in sys.argv)
