"""Planning endpoints. Open to guests (FR-13); saving requires login (see trips router)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..llm.parser import ParseResult, parse_preferences
from ..models import Poi
from ..schemas import CheckRequest, ParseIn, PlanRequest, PlanResponse
from ..services import planner

router = APIRouter(prefix="/plan", tags=["plan"])


@router.post("", response_model=PlanResponse)
def create_plan(req: PlanRequest, db: Session = Depends(get_db)):
    return planner.plan(db, req)


@router.post("/check", response_model=PlanResponse)
def check_route(req: CheckRequest, db: Session = Depends(get_db)):
    return planner.check(db, req)


@router.post("/parse", response_model=ParseResult)
def parse(body: ParseIn, db: Session = Depends(get_db)):
    city = planner.get_city(db, body.city)
    pois = list(db.scalars(select(Poi).where(Poi.city_id == city.id)))
    categories = sorted({c for p in pois for c in p.categories})
    return parse_preferences(body.text, categories, {p.name: p.id for p in pois})
