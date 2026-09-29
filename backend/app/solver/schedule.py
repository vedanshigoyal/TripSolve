"""Deterministic schedule simulation.

Used in two places:
  * after OR-Tools returns a visiting order, to compute concrete earliest-start times
    and to re-verify feasibility independently of the solver (FR-7, defence in depth);
  * to check a route the user edited by hand (FR-9), reporting every violation
    instead of silently fixing it.
"""

from .model import DayRoute, Problem, ScheduledVisit, Stop


def earliest_start(stop: Stop, arrival: int) -> int | None:
    """Earliest time >= arrival at which a visit to `stop` can start and still finish in time."""
    for open_, latest in stop.start_windows():
        if arrival <= latest:
            return max(arrival, open_)
    return None


def simulate_day(problem: Problem, day: int, order: list[int]) -> DayRoute:
    """Simulate visiting `order` (indices into problem.stops) on route `day`."""
    day_start, day_end = problem.day_windows[day]
    route = DayRoute(day=day, start_time=day_start, end_time=day_start)
    t = day_start
    prev = 0  # matrix index of the start location
    for idx in order:
        stop = problem.stops[idx]
        node = idx + 1
        leg = problem.travel[prev][node]
        arrival = t + leg
        start = earliest_start(stop, arrival)
        violation = None
        if start is None:
            violation = _explain_miss(stop, arrival)
            start = arrival
        end = start + stop.visit_minutes
        if violation is None and end > day_end:
            violation = "runs past the end of the day's time budget"
        route.visits.append(
            ScheduledVisit(
                stop_id=stop.id,
                arrival=arrival,
                start=start,
                end=end,
                wait=start - arrival,
                travel_from_prev=leg,
                violation=violation,
            )
        )
        t = end
        prev = node

    if problem.return_to_start and order:
        route.return_travel = problem.travel[prev][0]
        t += route.return_travel
    route.end_time = t
    if t > day_end:
        route.violations.append("the day ends after the available time budget")
    return route


def _explain_miss(stop: Stop, arrival: int) -> str:
    windows = stop.start_windows()
    if not windows:
        return "closed on this day (or open for less time than the visit takes)"
    if arrival > windows[-1][1]:
        return "arrives too late to finish the visit before closing"
    return "no opening slot fits this arrival time"


def simulate(problem: Problem, orders: list[list[int]]) -> list[DayRoute]:
    return [simulate_day(problem, d, order) for d, order in enumerate(orders)]
