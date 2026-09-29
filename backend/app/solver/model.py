"""Plain data structures shared by the solver, the schedule simulator and the planner.

All times are integer minutes measured from 00:00 on the first day of the trip, so
day 2 at 09:00 is 1440 + 540 = 1980. This lets one route per day (the "team" in
TOPTW) share a single time dimension in OR-Tools.
"""

from dataclasses import dataclass, field

MINUTES_PER_DAY = 1440


@dataclass
class Stop:
    """A candidate POI as the solver sees it."""

    id: int
    name: str
    visit_minutes: int
    # Opening intervals (absolute minutes). A visit must start and finish inside one interval.
    windows: list[tuple[int, int]]
    utility: float  # 0..1, already aggregated across group members
    must_visit: bool = False

    def start_windows(self) -> list[tuple[int, int]]:
        """Intervals in which a visit may *start* so that it ends before closing."""
        out = []
        for open_, close in self.windows:
            latest = close - self.visit_minutes
            if latest >= open_:
                out.append((open_, latest))
        return out


@dataclass
class Problem:
    stops: list[Stop]
    # (n+1) x (n+1) minutes; index 0 is the start location, index i+1 is stops[i].
    travel: list[list[int]]
    # One (start, end) per day/route, absolute minutes.
    day_windows: list[tuple[int, int]]
    return_to_start: bool = True

    @property
    def n(self) -> int:
        return len(self.stops)


@dataclass
class ScheduledVisit:
    stop_id: int
    arrival: int
    start: int
    end: int
    wait: int
    travel_from_prev: int
    violation: str | None = None  # only ever set by check_route on user-edited routes


@dataclass
class DayRoute:
    day: int
    start_time: int
    end_time: int
    visits: list[ScheduledVisit] = field(default_factory=list)
    return_travel: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def travel_minutes(self) -> int:
        return sum(v.travel_from_prev for v in self.visits) + self.return_travel

    @property
    def feasible(self) -> bool:
        return not self.violations and all(v.violation is None for v in self.visits)


@dataclass
class Solution:
    days: list[DayRoute]
    dropped: list[int]  # stop ids not visited
    status: str  # "optimal_or_feasible" | "no_solution"
    solve_ms: int
    objective: int | None = None

    @property
    def visited_ids(self) -> list[int]:
        return [v.stop_id for d in self.days for v in d.visits]

    @property
    def total_travel(self) -> int:
        return sum(d.travel_minutes for d in self.days)

    @property
    def feasible(self) -> bool:
        return all(d.feasible for d in self.days)
