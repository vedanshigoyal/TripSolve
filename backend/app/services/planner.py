"""End-to-end planning pipeline (SRS section 4.2):

candidate POIs (PostGIS) -> travel matrix (OSRM) -> group utility (aggregation)
-> TOPTW (OR-Tools) -> verified schedule -> explanation facts -> LLM / template text.
"""

import datetime as dt
from dataclasses import dataclass

from fastapi import HTTPException
from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm.explainer import llm_explanation, template_explanation
from ..models import City, Poi
from ..routing.osrm import route_geometry, travel_matrix
from ..schemas import (CheckRequest, DayOut, Metrics, PlanRequest, PlanResponse, PoiOut, SkippedOut,
                       StopOut, hhmm_to_min, min_to_hhmm)
from ..solver import MINUTES_PER_DAY, DayRoute, Problem, Solution, Stop, simulate, solve
from ..solver.aggregation import MemberPrefs, PoiInfo, aggregate, satisfaction, score_matrix
from .matrix_cache import DbMatrixCache

MAX_CANDIDATES = 30  # NFR 3.2.1: interactive solve for ~30 POIs
FAIRNESS_ROUNDS = 3
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---------- data loading ----------

def get_city(db: Session, slug: str) -> City:
    city = db.scalar(select(City).where(City.slug == slug))
    if city is None:
        raise HTTPException(404, f"Unknown city '{slug}'")
    return city


def pois_within(db: Session, city: City, lat: float, lon: float, radius_km: float) -> list[Poi]:
    point = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
    return list(db.scalars(
        select(Poi).where(Poi.city_id == city.id, func.ST_DWithin(Poi.location, point, radius_km * 1000))
    ))


def poi_out(p: Poi) -> PoiOut:
    return PoiOut(id=p.id, slug=p.slug, name=p.name, description=p.description, lat=p.lat, lon=p.lon,
                  categories=list(p.categories), visit_minutes=p.visit_minutes, popularity=p.popularity,
                  opening_hours=p.opening_hours, entry_fee_inr=p.entry_fee_inr)


def opening_windows(hours: dict, start_date: dt.date, days: int) -> list[tuple[int, int]]:
    """Weekly hours -> absolute-minute intervals over the trip days."""
    out = []
    for d in range(days):
        weekday = WEEKDAYS[(start_date + dt.timedelta(days=d)).weekday()]
        for open_, close in hours.get(weekday, hours.get("daily", [])):
            out.append((d * MINUTES_PER_DAY + hhmm_to_min_24(open_), d * MINUTES_PER_DAY + hhmm_to_min_24(close)))
    return out


def hhmm_to_min_24(s: str) -> int:
    return 1440 if s == "24:00" else hhmm_to_min(s)


def members_of(req: PlanRequest) -> list[MemberPrefs]:
    return [MemberPrefs(m.name, dict(m.interests), set(m.must_visit), set(m.avoid)) for m in req.members]


# ---------- context shared by /plan and /plan/check ----------

@dataclass
class Context:
    req: PlanRequest
    pois: list[Poi]  # candidate order == Problem.stops order
    scores: dict[str, dict[int, float]]
    problem: Problem
    travel_source: str
    must_ids: set[int]
    outside: list[Poi]  # must-visits that could not be candidates


def build_context(db: Session, req: PlanRequest, forced_ids: list[int] | None = None) -> Context:
    city = get_city(db, req.city)
    loc = req.start_location
    in_radius = {p.id: p for p in pois_within(db, city, loc.lat, loc.lon, req.radius_km)}
    members = members_of(req)
    must_ids = (set().union(*(m.must_visit for m in members)) | set(req.include)) - set(req.exclude)
    forced = set(forced_ids or []) | must_ids

    all_city = {p.id: p for p in db.scalars(select(Poi).where(Poi.city_id == city.id))}
    unknown = forced - set(all_city)
    if unknown:
        raise HTTPException(422, f"Unknown POI ids: {sorted(unknown)}")
    outside = [all_city[i] for i in forced if i not in in_radius and forced_ids is None]
    pool = dict(in_radius)
    if forced_ids is not None:  # a manual route may include anything the user picked
        pool.update({i: all_city[i] for i in forced})
    for i in req.exclude:
        if i not in forced:
            pool.pop(i, None)

    infos = [PoiInfo(p.id, list(p.categories), p.popularity) for p in pool.values()]
    scores = score_matrix(members, infos)
    base_util = aggregate(scores, req.strategy)
    ranked = sorted(pool.values(), key=lambda p: (p.id not in forced, -base_util[p.id], p.id))
    chosen = [p for p in ranked if p.id in forced] + [p for p in ranked if p.id not in forced]
    chosen = chosen[:max(MAX_CANDIDATES, len(forced))]

    points = [(loc.lat, loc.lon)] + [(p.lat, p.lon) for p in chosen]
    matrix = travel_matrix(points, DbMatrixCache(db))

    start, end = hhmm_to_min(req.start_time), hhmm_to_min(req.end_time)
    day_windows = [(d * MINUTES_PER_DAY + start, d * MINUTES_PER_DAY + end) for d in range(req.days)]
    stops = [
        Stop(id=p.id, name=p.name, visit_minutes=p.visit_minutes,
             windows=opening_windows(p.opening_hours, req.date, req.days),
             utility=base_util[p.id], must_visit=p.id in must_ids)
        for p in chosen
    ]
    problem = Problem(stops=stops, travel=matrix.minutes, day_windows=day_windows,
                      return_to_start=req.return_to_start)
    return Context(req=req, pois=chosen, scores=scores, problem=problem, travel_source=matrix.source,
                   must_ids=must_ids, outside=outside)


def _with_utilities(problem: Problem, util: dict[int, float]) -> Problem:
    stops = [Stop(s.id, s.name, s.visit_minutes, s.windows, util[s.id], s.must_visit) for s in problem.stops]
    return Problem(stops, problem.travel, problem.day_windows, problem.return_to_start)


# ---------- optimisation ----------

def plan(db: Session, req: PlanRequest) -> PlanResponse:
    ctx = build_context(db, req)
    time_limit = get_settings().solver_time_limit_seconds
    sats = None

    if len(req.members) == 1:
        sol = solve(ctx.problem, time_limit_s=time_limit)
        problem = ctx.problem
    else:
        sol, problem, sats = _solve_fairly(ctx, time_limit)

    return _response(ctx, problem, sol, sats, explain=req.explain)


def _solve_fairly(ctx: Context, time_limit: float):
    """Re-weight under-served members and keep the route whose worst-off member is best off."""
    names = list(ctx.scores)
    weights = {n: 1.0 for n in names}
    best = None
    per_round = max(0.5, time_limit / FAIRNESS_ROUNDS)
    for _ in range(FAIRNESS_ROUNDS):
        problem = _with_utilities(ctx.problem, aggregate(ctx.scores, ctx.req.strategy, weights))
        sol = solve(problem, time_limit_s=per_round)
        route = sol.visited_ids
        sats = {n: satisfaction(ctx.scores[n], route) for n in names}
        total = sum(s.utility for s in problem.stops if s.id in set(route))
        key = (min(sats.values()), total)
        if best is None or key > best[0]:
            best = (key, sol, problem, sats)
        mean = sum(sats.values()) / len(sats)
        if max(sats.values()) - min(sats.values()) < 0.1 or ctx.req.strategy == "least_misery":
            break
        weights = {n: weights[n] * mean / max(sats[n], 0.05) for n in names}
    _, sol, problem, sats = best
    return sol, problem, sats


def check(db: Session, req: CheckRequest) -> PlanResponse:
    """Evaluate a hand-edited route without changing it (FR-9)."""
    if len(req.route) != req.days:
        raise HTTPException(422, f"route must have one list per day ({req.days})")
    ids = [i for day in req.route for i in day]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "a POI appears more than once in the route")
    ctx = build_context(db, req, forced_ids=ids)
    index = {s.id: i for i, s in enumerate(ctx.problem.stops)}
    orders = [[index[i] for i in day] for day in req.route]
    days = simulate(ctx.problem, orders)
    visited = set(ids)
    sol = Solution(days=days, dropped=[s.id for s in ctx.problem.stops if s.id not in visited],
                   status="manual", solve_ms=0)
    sats = None
    if len(req.members) > 1:
        sats = {n: satisfaction(ctx.scores[n], ids) for n in ctx.scores}
    return _response(ctx, ctx.problem, sol, sats, explain=req.explain)


# ---------- response & explanation ----------

def _response(ctx: Context, problem: Problem, sol: Solution, sats, explain: bool) -> PlanResponse:
    req = ctx.req
    by_id = {p.id: p for p in ctx.pois}
    util = {s.id: s.utility for s in problem.stops}
    loc = (req.start_location.lat, req.start_location.lon)

    days_out = []
    for d in sol.days:
        coords = [loc] + [(by_id[v.stop_id].lat, by_id[v.stop_id].lon) for v in d.visits]
        if req.return_to_start and d.visits:
            coords.append(loc)
        geometry, _ = route_geometry(coords) if d.visits else ([], "none")
        days_out.append(DayOut(
            day=d.day,
            date=req.date + dt.timedelta(days=d.day),
            start=min_to_hhmm(d.start_time),
            end=min_to_hhmm(d.end_time),
            travel_minutes=d.travel_minutes,
            return_travel_minutes=d.return_travel,
            stops=[StopOut(poi=poi_out(by_id[v.stop_id]), arrival=min_to_hhmm(v.arrival),
                           start=min_to_hhmm(v.start), end=min_to_hhmm(v.end), wait_minutes=v.wait,
                           travel_minutes=v.travel_from_prev, utility=util[v.stop_id], violation=v.violation)
                   for v in d.visits],
            geometry=geometry,
            violations=d.violations,
        ))

    skipped = _skipped(ctx, problem, sol)
    violations = sum(1 for d in sol.days for v in d.visits if v.violation) + sum(len(d.violations) for d in sol.days)
    visited = set(sol.visited_ids)
    metrics = Metrics(
        stops=len(visited),
        total_travel_minutes=sol.total_travel,
        total_utility=round(sum(util[i] for i in visited), 3),
        time_window_violations=violations,
        solve_ms=sol.solve_ms,
        candidates=len(problem.stops),
        travel_time_source=ctx.travel_source,
        must_visit_missed=len(ctx.must_ids - visited),
    )
    resp = PlanResponse(feasible=violations == 0, days=days_out, skipped=skipped, metrics=metrics,
                        member_satisfaction=sats)
    if explain:
        facts = explanation_facts(resp, ctx)
        text = llm_explanation(facts)
        resp.explanation, resp.explanation_source = (text, "llm") if text else (template_explanation(facts), "template")
    return resp


def _skipped(ctx: Context, problem: Problem, sol: Solution) -> list[SkippedOut]:
    visited = set(sol.visited_ids)
    index = {s.id: i for i, s in enumerate(problem.stops)}
    orders = [[index[v.stop_id] for v in d.visits] for d in sol.days]
    avoided = set().union(*(set(m.avoid) for m in ctx.req.members))
    out = [SkippedOut(poi_id=p.id, name=p.name, utility=0.0, reason="it is outside your search radius")
           for p in ctx.outside]
    dropped = sorted((s for s in problem.stops if s.id not in visited), key=lambda s: -s.utility)
    for s in dropped:
        if sol.status == "manual":
            reason = "you removed it from the route"
        elif s.id in avoided and s.utility < 0.2:
            reason = "someone in your group asked to skip it"
        elif not _open_during_trip(problem, s):
            reason = "it is closed, or not open long enough for a visit, during your trip"
        elif _fits_somewhere(problem, orders, index[s.id]):
            reason = "there was room, but the detour costs more time than it is worth for your interests"
        elif s.id in ctx.must_ids:
            reason = "no schedule could include it together with the opening hours and your time budget"
        elif any(problem.stops[i].utility < s.utility for o in orders for i in o):
            reason = (f"the visit takes about {s.visit_minutes} minutes, and that time covers other stops "
                      "that are worth more to you together")
        else:
            reason = "there was no time left without dropping a stop that matters more to you"
        out.append(SkippedOut(poi_id=s.id, name=s.name, utility=s.utility, reason=reason))
    return out


def _open_during_trip(problem: Problem, stop: Stop) -> bool:
    for lo, hi in stop.start_windows():
        for ds, de in problem.day_windows:
            if max(lo, ds) <= min(hi, de - stop.visit_minutes):
                return True
    return False


def _fits_somewhere(problem: Problem, orders: list[list[int]], idx: int) -> bool:
    for d, order in enumerate(orders):
        for pos in range(len(order) + 1):
            trial = simulate(problem, [o if k != d else order[:pos] + [idx] + order[pos:]
                                       for k, o in enumerate(orders)])
            if trial[d].feasible:
                return True
    return False


def explanation_facts(resp: PlanResponse, ctx: Context) -> dict:
    multi_day = ctx.req.days > 1
    included = [
        {"name": s.poi.name, "day": d.day + 1 if multi_day else None, "start": s.start, "end": s.end,
         "wait_minutes": s.wait_minutes, "value": s.utility, "must_visit": s.poi.id in ctx.must_ids}
        for d in resp.days for s in d.stops
    ]
    musts = [k for k in resp.skipped if k.poi_id in ctx.must_ids]
    others = [k for k in resp.skipped if k.poi_id not in ctx.must_ids][: max(0, 6 - len(musts))]
    return {
        "time_budget": f"{ctx.req.start_time}-{ctx.req.end_time}" + (f" for {ctx.req.days} days" if multi_day else ""),
        "group_size": len(ctx.req.members),
        "included": included,
        "skipped": [{"name": k.name, "reason": k.reason, "was_must_visit": k.poi_id in ctx.must_ids}
                    for k in musts + others],
        "total_travel_minutes": resp.metrics.total_travel_minutes,
        "member_satisfaction": resp.member_satisfaction,
        "travel_time_source": ctx.travel_source,
    }
