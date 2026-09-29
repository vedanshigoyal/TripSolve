"""Load a city dataset into the database (idempotent: upserts by slug).

    python -m seed.seed                 # seeds seed/jaipur.json
    python -m seed.seed seed/other.json # any city in the same format
"""

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import City, Poi

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def expand_hours(hours: dict) -> dict:
    daily = hours.get("daily")
    return {d: hours.get(d, daily or []) for d in DAYS}


def seed(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    init_db()
    with SessionLocal() as db:
        c = data["city"]
        city = db.scalar(select(City).where(City.slug == c["slug"])) or City(slug=c["slug"])
        city.name, city.center_lat, city.center_lon = c["name"], c["center_lat"], c["center_lon"]
        city.timezone = c.get("timezone", "UTC")
        db.add(city)
        db.flush()

        existing = {p.slug: p for p in db.scalars(select(Poi).where(Poi.city_id == city.id))}
        for item in data["pois"]:
            poi = existing.get(item["slug"]) or Poi(city_id=city.id, slug=item["slug"])
            poi.name = item["name"]
            poi.description = item.get("description", "")
            poi.lat, poi.lon = item["lat"], item["lon"]
            poi.location = f"SRID=4326;POINT({item['lon']} {item['lat']})"
            poi.categories = item["categories"]
            poi.visit_minutes = item["visit_minutes"]
            poi.popularity = item["popularity"]
            poi.opening_hours = expand_hours(item["hours"])
            poi.entry_fee_inr = item.get("entry_fee_inr")
            db.add(poi)
        db.commit()
        print(f"Seeded {len(data['pois'])} POIs for {city.name}")


if __name__ == "__main__":
    seed(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("jaipur.json")))
