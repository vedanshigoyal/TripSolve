"""Team Orienteering Problem with Time Windows, solved with the OR-Tools routing solver.

Formulation (see docs/solver.md for the maths):
  * one vehicle per trip day, starting (and optionally ending) at the traveller's start point;
  * every POI is optional: dropping it costs a penalty proportional to its utility, so
    minimising (travel time + penalties of dropped POIs) maximises collected utility and
    uses travel time only as a tie-breaker;
  * must-visit POIs get a penalty so large that they are dropped only when no feasible
    schedule contains them;
  * a "Time" dimension accumulates travel + visit duration; each POI's cumul (visit start)
    is restricted to its opening intervals, shortened by the visit length so the visit
    finishes before closing. Waiting (slack) is allowed.
"""

import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .model import Problem, Solution
from .schedule import simulate

UTILITY_PENALTY_SCALE = 1000  # 1.0 utility == 1000 minutes of travel
# Value of a stop = utility ** VALUE_EXPONENT. With 3, one place scored 1.0 is worth eight
# places scored 0.5, so the solver doesn't trade a headline attraction (e.g. Amber Fort's
# 150-minute visit for a fort lover) for a handful of so-so short stops that merely sum
# higher. Tuned on the Jaipur data: exponents 1 and 2 both dropped Amber Fort in that case.
VALUE_EXPONENT = 3
MUST_VISIT_PENALTY = 10_000_000


def stop_value(utility: float) -> float:
    return utility ** VALUE_EXPONENT


def _allowed_start_windows(problem: Problem, i: int) -> list[tuple[int, int]]:
    """Visit-start intervals of stop i that also fall inside some trip day."""
    stop = problem.stops[i]
    out = []
    for lo, hi in stop.start_windows():
        for day_start, day_end in problem.day_windows:
            a, b = max(lo, day_start), min(hi, day_end - stop.visit_minutes)
            if a <= b:
                out.append((a, b))
    out.sort()
    return out


def solve(problem: Problem, time_limit_s: float = 3.0) -> Solution:
    t0 = time.perf_counter()
    n = problem.n
    num_days = len(problem.day_windows)
    windows = [_allowed_start_windows(problem, i) for i in range(n)]
    candidates = [i for i in range(n) if windows[i]]
    unreachable = [problem.stops[i].id for i in range(n) if not windows[i]]

    if not candidates:
        days = simulate(problem, [[] for _ in range(num_days)])
        return Solution(days=days, dropped=unreachable, status="optimal_or_feasible",
                        solve_ms=_ms(t0), objective=0)

    # Solver nodes: 0 = start, 1..k = candidate stops, optional k+1 = free end.
    k = len(candidates)
    matrix_idx = [0] + [i + 1 for i in candidates]  # solver node -> problem.travel index
    free_end = not problem.return_to_start
    num_nodes = k + 1 + (1 if free_end else 0)
    end_node = k + 1 if free_end else 0

    manager = pywrapcp.RoutingIndexManager(num_nodes, num_days, [0] * num_days, [end_node] * num_days)
    routing = pywrapcp.RoutingModel(manager)

    def travel(a: int, b: int) -> int:
        if free_end and (a == end_node or b == end_node):
            return 0
        return problem.travel[matrix_idx[a]][matrix_idx[b]]

    def service(a: int) -> int:
        if 1 <= a <= k:
            return problem.stops[candidates[a - 1]].visit_minutes
        return 0

    def travel_cb(fi: int, ti: int) -> int:
        return travel(manager.IndexToNode(fi), manager.IndexToNode(ti))

    def time_cb(fi: int, ti: int) -> int:
        a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
        return service(a) + travel(a, b)

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(travel_cb))

    horizon = max(end for _, end in problem.day_windows)
    routing.AddDimension(routing.RegisterTransitCallback(time_cb), horizon, horizon, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")

    for node in range(1, k + 1):
        i = candidates[node - 1]
        index = manager.NodeToIndex(node)
        cumul = time_dim.CumulVar(index)
        w = windows[i]
        cumul.SetRange(w[0][0], w[-1][1])
        for (_, prev_hi), (next_lo, _) in zip(w, w[1:]):
            if next_lo - 1 >= prev_hi + 1:
                cumul.RemoveInterval(prev_hi + 1, next_lo - 1)
        stop = problem.stops[i]
        penalty = MUST_VISIT_PENALTY if stop.must_visit else max(1, round(stop_value(stop.utility) * UTILITY_PENALTY_SCALE))
        routing.AddDisjunction([index], penalty)

    for v, (day_start, day_end) in enumerate(problem.day_windows):
        time_dim.CumulVar(routing.Start(v)).SetRange(day_start, day_end)
        time_dim.CumulVar(routing.End(v)).SetRange(day_start, day_end)

    params = pywrapcp.DefaultRoutingSearchParameters()
    # PATH_CHEAPEST_ARC got stuck on the all-dropped solution for multi-day trips with
    # must-visits; insertion heuristics handle optional nodes + time windows well.
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(max(100, int(time_limit_s * 1000)))

    assignment = routing.SolveWithParameters(params)
    if assignment is None:
        days = simulate(problem, [[] for _ in range(num_days)])
        return Solution(days=days, dropped=[s.id for s in problem.stops], status="no_solution",
                        solve_ms=_ms(t0))

    orders: list[list[int]] = []
    for v in range(num_days):
        order = []
        index = assignment.Value(routing.NextVar(routing.Start(v)))
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if 1 <= node <= k:
                order.append(candidates[node - 1])
            index = assignment.Value(routing.NextVar(index))
        orders.append(order)

    days = _verified_schedule(problem, orders)
    visited = {v.stop_id for d in days for v in d.visits}
    dropped = [s.id for s in problem.stops if s.id not in visited]
    return Solution(days=days, dropped=dropped, status="optimal_or_feasible",
                    solve_ms=_ms(t0), objective=assignment.ObjectiveValue())


def _verified_schedule(problem: Problem, orders: list[list[int]]):
    """Re-simulate the solver's orders and strip anything infeasible (should never trigger)."""
    while True:
        days = simulate(problem, orders)
        bad = next(((d.day, j) for d in days for j, v in enumerate(d.visits) if v.violation), None)
        if bad is None:
            late_day = next((d.day for d in days if d.violations and orders[d.day]), None)
            if late_day is None:
                return days
            bad = (late_day, len(orders[late_day]) - 1)
        day, j = bad
        orders[day] = orders[day][:j] + orders[day][j + 1:]


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
