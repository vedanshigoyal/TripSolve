from app.solver import Problem, Stop, simulate, solve
from app.solver.aggregation import MemberPrefs, PoiInfo, aggregate, member_score, satisfaction, score_matrix


def h(hh, mm=0):
    return hh * 60 + mm


def square_problem(stops, day_windows=None, return_to_start=True):
    """Everything 10 minutes apart, which keeps expected schedules easy to reason about."""
    n = len(stops) + 1
    travel = [[0 if i == j else 10 for j in range(n)] for i in range(n)]
    return Problem(stops=stops, travel=travel, day_windows=day_windows or [(h(9), h(18))],
                   return_to_start=return_to_start)


def assert_all_within_windows(problem, solution):
    by_id = {s.id: s for s in problem.stops}
    for day in solution.days:
        for v in day.visits:
            stop = by_id[v.stop_id]
            assert any(o <= v.start and v.end <= c for o, c in stop.windows), (stop.name, v)
        assert day.end_time <= problem.day_windows[day.day][1]


def test_all_stops_fit():
    stops = [Stop(i, f"P{i}", 60, [(h(9), h(18))], 0.5) for i in range(1, 4)]
    p = square_problem(stops)
    sol = solve(p, time_limit_s=0.5)
    assert sorted(sol.visited_ids) == [1, 2, 3]
    assert sol.dropped == []
    assert_all_within_windows(p, sol)


def test_time_budget_forces_drop_of_lowest_utility():
    # 3 x 120 min visits + travel cannot fit in 5 hours; the low-utility one goes.
    stops = [
        Stop(1, "High", 120, [(h(9), h(18))], 0.9),
        Stop(2, "Mid", 120, [(h(9), h(18))], 0.6),
        Stop(3, "Low", 120, [(h(9), h(18))], 0.1),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(14))])
    sol = solve(p, time_limit_s=0.5)
    assert sorted(sol.visited_ids) == [1, 2]
    assert sol.dropped == [3]
    assert_all_within_windows(p, sol)


def test_time_windows_dictate_order():
    # "Morning" closes at 11:00 and "Evening" opens at 16:00: order must be Morning -> Evening.
    stops = [
        Stop(1, "Evening", 60, [(h(16), h(20))], 0.5),
        Stop(2, "Morning", 60, [(h(9), h(11))], 0.5),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(21))])
    sol = solve(p, time_limit_s=0.5)
    assert sol.visited_ids == [2, 1]
    evening = sol.days[0].visits[1]
    assert evening.start == h(16) and evening.wait > 0
    assert_all_within_windows(p, sol)


def test_visit_must_finish_before_closing():
    # Open 09:00-10:00 but the visit needs 90 minutes: never schedulable.
    stops = [Stop(1, "Short window", 90, [(h(9), h(10))], 1.0, must_visit=True)]
    sol = solve(square_problem(stops), time_limit_s=0.5)
    assert sol.visited_ids == []
    assert sol.dropped == [1]


def test_split_opening_hours():
    # Temple-style hours: 08-12 and 16-20. Arriving at 13:00 must wait until 16:00.
    stops = [
        Stop(1, "Long museum", 180, [(h(9), h(18))], 0.9, must_visit=True),
        Stop(2, "Temple", 40, [(h(8), h(12)), (h(16), h(20))], 0.5),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(21))])
    sol = solve(p, time_limit_s=0.5)
    assert sorted(sol.visited_ids) == [1, 2]
    assert_all_within_windows(p, sol)


def test_multi_day_uses_both_days_and_respects_closed_day():
    day2 = 1440
    stops = [
        Stop(1, "A", 240, [(h(9), h(18)), (day2 + h(9), day2 + h(18))], 0.8),
        Stop(2, "B", 240, [(h(9), h(18)), (day2 + h(9), day2 + h(18))], 0.8),
        Stop(3, "Closed day 1", 120, [(day2 + h(9), day2 + h(18))], 0.8),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(17)), (day2 + h(9), day2 + h(17))])
    sol = solve(p, time_limit_s=1)
    assert sorted(sol.visited_ids) == [1, 2, 3]
    assert 3 in [v.stop_id for v in sol.days[1].visits]
    assert_all_within_windows(p, sol)


def test_must_visit_beats_higher_utility():
    stops = [
        Stop(1, "Popular", 240, [(h(9), h(18))], 1.0),
        Stop(2, "Requested", 240, [(h(9), h(18))], 0.1, must_visit=True),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(14))])
    sol = solve(p, time_limit_s=0.5)
    assert sol.visited_ids == [2]


def test_simulate_reports_violations_for_manual_order():
    stops = [
        Stop(1, "Evening", 60, [(h(16), h(20))], 0.5),
        Stop(2, "Morning", 60, [(h(9), h(11))], 0.5),
    ]
    p = square_problem(stops, day_windows=[(h(9), h(21))])
    day = simulate(p, [[0, 1]])[0]  # Evening first, then Morning (too late)
    assert day.visits[0].violation is None
    assert day.visits[1].violation is not None
    assert not day.feasible


def test_free_end_does_not_charge_return_trip():
    stops = [Stop(1, "A", 60, [(h(9), h(18))], 0.5)]
    p = square_problem(stops, return_to_start=False)
    sol = solve(p, time_limit_s=0.5)
    assert sol.days[0].return_travel == 0
    assert sol.total_travel == 10


def test_aggregation_strategies():
    pois = [PoiInfo(1, ["fort"], 1.0), PoiInfo(2, ["shopping"], 0.5)]
    alice = MemberPrefs("alice", {"fort": 5})
    bob = MemberPrefs("bob", {"shopping": 5}, avoid={1})
    scores = score_matrix([alice, bob], pois)
    assert scores["alice"][1] == 1.0
    assert scores["bob"][1] == 0.0
    avg = aggregate(scores, "average")
    lm = aggregate(scores, "least_misery")
    fair = aggregate(scores, "fair")
    assert lm[1] == 0.0
    assert avg[1] == 0.5
    assert lm[1] < fair[1] < avg[1]
    # Up-weighting bob moves the mean towards his scores.
    assert aggregate(scores, "average", {"alice": 1, "bob": 3})[2] > avg[2]


def test_member_score_bounds_and_satisfaction():
    poi = PoiInfo(1, ["museum"], 0.4)
    assert member_score(MemberPrefs("x", {"museum": 5}), poi) == 0.85
    assert member_score(MemberPrefs("x", {}, must_visit={1}), poi) == 1.0
    assert satisfaction({1: 1.0, 2: 0.5, 3: 0.2}, [1, 2]) == 1.0
    assert satisfaction({1: 1.0, 2: 0.5, 3: 0.2}, [3]) == 0.2


def test_multi_day_with_must_visits_is_not_empty():
    # Regression: PATH_CHEAPEST_ARC returned an empty 2-day route for the "two-day-family" scenario.
    day2 = 1440
    both_days = lambda o, c: [(h(o), h(c)), (day2 + h(o), day2 + h(c))]  # noqa: E731
    stops = [Stop(i, f"P{i}", 30 + 15 * (i % 6), both_days(9, 17), 0.3 + 0.03 * i, must_visit=i in (1, 7))
             for i in range(1, 21)]
    n = len(stops) + 1
    travel = [[0 if i == j else 8 + (i * 7 + j * 3) % 25 for j in range(n)] for i in range(n)]
    p = Problem(stops, travel, [(h(9), h(18, 30)), (day2 + h(9), day2 + h(18, 30))])
    sol = solve(p, time_limit_s=1)
    assert {1, 7} <= set(sol.visited_ids)
    assert all(d.visits for d in sol.days)
    assert_all_within_windows(p, sol)
