"""Baseline comparison (FR-14, SRS 4.4).

The same scenario (same candidates, same travel matrix, same utilities) is planned by:
  * toptw  - the OR-Tools solver;
  * naive  - "manual" planning: pick the highest-value places whose visit durations fit
             the budget, visit them nearest-first, ignoring opening hours;
  * llm    - a pure-LLM itinerary: the model sees the same POI list with hours and
             durations and returns an ordered plan.
Every plan is then executed by the same simulator on real travel times, so the metrics
(travel time, time-window violations, requested POIs included) are directly comparable.
"""

import re
import time

from sqlalchemy.orm import Session

from ..llm.client import chat_json
from ..models import EvalRun
from ..schemas import PlanRequest
from ..solver import Problem, simulate, solve
from .planner import Context, build_context

METHODS = ("toptw", "naive", "llm")


def _metrics(ctx: Context, orders: list[list[int]], runtime_ms: int, note: str = "") -> dict:
    days = simulate(ctx.problem, orders)
    ids = [ctx.problem.stops[i].id for o in orders for i in o]
    util = {s.id: s.utility for s in ctx.problem.stops}
    violations = sum(1 for d in days for v in d.visits if v.violation) + sum(len(d.violations) for d in days)
    return {
        "stops": len(ids),
        "total_travel_minutes": sum(d.travel_minutes for d in days),
        "time_window_violations": violations,
        "requested_included": len(ctx.must_ids & set(ids)),
        "requested_total": len(ctx.must_ids),
        "total_utility": round(sum(util[i] for i in ids), 3),
        "runtime_ms": runtime_ms,
        "note": note,
    }


def run_toptw(ctx: Context, time_limit: float) -> dict:
    t0 = time.perf_counter()
    sol = solve(ctx.problem, time_limit_s=time_limit)
    index = {s.id: i for i, s in enumerate(ctx.problem.stops)}
    orders = [[index[v.stop_id] for v in d.visits] for d in sol.days]
    return _metrics(ctx, orders, int((time.perf_counter() - t0) * 1000))


def run_naive(ctx: Context) -> dict:
    t0 = time.perf_counter()
    p: Problem = ctx.problem
    ranked = sorted(range(p.n), key=lambda i: (not p.stops[i].must_visit, -p.stops[i].utility))
    orders = []
    remaining = list(ranked)
    for ds, de in p.day_windows:
        budget, picked = de - ds, []
        for i in list(remaining):
            if p.stops[i].visit_minutes <= budget:
                picked.append(i)
                budget -= p.stops[i].visit_minutes + 15  # rough allowance for travel
                remaining.remove(i)
        order, cur = [], 0
        while picked:  # nearest neighbour from the current position
            nxt = min(picked, key=lambda i: p.travel[cur][i + 1])
            order.append(nxt)
            picked.remove(nxt)
            cur = nxt + 1
        orders.append(order)
    return _metrics(ctx, orders, int((time.perf_counter() - t0) * 1000))


LLM_SYSTEM = """You are a travel planner. Build a sightseeing itinerary.
Return ONLY JSON: {"days": [[{"name": "<exact attraction name>", "start": "HH:MM"}, ...], ...]} with one list per day, in visiting order.
Respect opening hours, visit durations, travel between places and the daily time window. Prefer places matching the interests; include all must-visit places."""


def run_llm(ctx: Context) -> dict | None:
    p = ctx.problem
    req = ctx.req
    lines = []
    for s, poi in zip(p.stops, ctx.pois):
        hours = "; ".join(f"{k}: " + ", ".join(f"{a}-{b}" for a, b in v) for k, v in poi.opening_hours.items()) or "closed"
        lines.append(f"- {s.name} | visit {s.visit_minutes} min | hours {hours} | categories {', '.join(poi.categories)}"
                     + (" | MUST VISIT" if s.must_visit else ""))
    interests = {k: v for m in req.members for k, v in m.interests.items()}
    user = (f"City: {req.city}. Start date {req.date.isoformat()} ({req.date.strftime('%A')}), {req.days} day(s), "
            f"each day {req.start_time}-{req.end_time}, starting from {req.start_location.label} "
            f"({req.start_location.lat:.4f},{req.start_location.lon:.4f}).\n"
            f"Interests (0-5): {interests or 'none given'}\nAttractions:\n" + "\n".join(lines))
    t0 = time.perf_counter()
    data = chat_json([{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}],
                     temperature=0.2, max_tokens=1200, rate_limit_retries=4)
    runtime = int((time.perf_counter() - t0) * 1000)
    if data is None or not isinstance(data.get("days"), list):
        return None

    by_name = {_norm(s.name): i for i, s in enumerate(p.stops)}
    orders, unknown, seen = [], 0, set()
    for day in data["days"][: len(p.day_windows)]:
        order = []
        for item in day if isinstance(day, list) else []:
            i = by_name.get(_norm(str(item.get("name", "")))) if isinstance(item, dict) else None
            if i is None:
                unknown += 1
            elif i not in seen:
                order.append(i)
                seen.add(i)
        orders.append(order)
    orders += [[] for _ in range(len(p.day_windows) - len(orders))]
    return _metrics(ctx, orders, runtime, note=f"{unknown} unrecognised place name(s)" if unknown else "")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def compare(db: Session, req: PlanRequest, scenario: str = "adhoc", time_limit: float = 3.0,
            save: bool = True) -> dict:
    ctx = build_context(db, req)
    results = {"toptw": run_toptw(ctx, time_limit), "naive": run_naive(ctx), "llm": run_llm(ctx)}
    if save:
        for method, m in results.items():
            if m is not None:
                db.add(EvalRun(scenario=scenario, method=method, metrics=m))
        db.commit()
    return {"scenario": scenario, "candidates": ctx.problem.n, "travel_time_source": ctx.travel_source,
            "day_window": f"{req.start_time}-{req.end_time}", "results": results}
