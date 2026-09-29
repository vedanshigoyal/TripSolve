from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import City, Poi
from ..schemas import CityOut, PoiOut
from ..services.planner import get_city, poi_out

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("", response_model=list[CityOut])
def list_cities(db: Session = Depends(get_db)):
    return [CityOut(slug=c.slug, name=c.name, center_lat=c.center_lat, center_lon=c.center_lon)
            for c in db.scalars(select(City).order_by(City.name))]


@router.get("/{slug}/pois", response_model=list[PoiOut])
def list_pois(slug: str, db: Session = Depends(get_db)):
    city = get_city(db, slug)
    return [poi_out(p) for p in db.scalars(select(Poi).where(Poi.city_id == city.id).order_by(Poi.name))]


@router.get("/{slug}/categories", response_model=list[str])
def list_categories(slug: str, db: Session = Depends(get_db)):
    city = get_city(db, slug)
    cats = {c for p in db.scalars(select(Poi).where(Poi.city_id == city.id)) for c in p.categories}
    return sorted(cats)
