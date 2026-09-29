import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import EvalRun, Poi
from ..schemas import PlanRequest
from ..services.evaluation import compare

router = APIRouter(prefix="/eval", tags=["evaluation"])

SCENARIOS_FILE = Path(__file__).resolve().parents[2] / "eval" / "scenarios.json"


class CompareIn(PlanRequest):
    scenario: str = Field(default="adhoc", max_length=100)


def load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))


def scenario_request(db: Session, scenario: dict) -> PlanRequest:
    """Resolve POI slugs (stable across databases) into ids."""
    ids = {p.slug: p.id for p in db.scalars(select(Poi))}
    body = json.loads(json.dumps(scenario["request"]))
    for m in body["members"]:
        m["must_visit"] = [ids[s] for s in m.pop("must_visit_slugs", [])]
        m["avoid"] = [ids[s] for s in m.pop("avoid_slugs", [])]
    body["explain"] = False
    return PlanRequest.model_validate(body)


@router.get("/scenarios")
def list_scenarios():
    return [{"name": s["name"], "description": s["description"]} for s in load_scenarios()]


@router.post("/scenarios/{name}/run")
def run_scenario(name: str, db: Session = Depends(get_db)):
    scenario = next((s for s in load_scenarios() if s["name"] == name), None)
    if scenario is None:
        raise HTTPException(404, "Unknown scenario")
    req = scenario_request(db, scenario)
    return compare(db, req, scenario=name, time_limit=get_settings().solver_time_limit_seconds)


@router.post("/compare")
def compare_methods(body: CompareIn, db: Session = Depends(get_db)):
    return compare(db, body, scenario=body.scenario, time_limit=get_settings().solver_time_limit_seconds)


@router.get("/runs")
def list_runs(limit: int = 100, db: Session = Depends(get_db)):
    runs = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(min(limit, 500)))
    return [{"scenario": r.scenario, "method": r.method, "metrics": r.metrics, "created_at": r.created_at}
            for r in runs]
