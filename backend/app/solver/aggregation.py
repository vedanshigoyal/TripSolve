"""Group preference aggregation (FR-5).

Each member rates interest categories 0..5 and may mark POIs as must-visit or avoid.
A member's score for a POI is

    s_m(p) = 0.75 * max_{c in categories(p)} w_m(c) / 5  +  0.25 * popularity(p)

(1.0 for must-visit, 0.0 for avoid). Scores are combined into one utility per POI:

  * "average"       U(p) = weighted mean of s_m(p)                  (utilitarian)
  * "least_misery"  U(p) = min_m s_m(p)                              (egalitarian)
  * "fair" (default) U(p) = 0.5 * weighted mean + 0.5 * min          (compromise)

Member weights start equal. The planner then measures each member's satisfaction with
the solved route and re-weights under-served members (see planner.plan_group), which
is what stops one person's interests from dominating the route.
"""

from dataclasses import dataclass, field

INTEREST_SHARE = 0.75
POPULARITY_SHARE = 0.25
STRATEGIES = ("fair", "average", "least_misery")


@dataclass
class MemberPrefs:
    name: str
    interests: dict[str, float] = field(default_factory=dict)  # category -> 0..5
    must_visit: set[int] = field(default_factory=set)
    avoid: set[int] = field(default_factory=set)


@dataclass
class PoiInfo:
    id: int
    categories: list[str]
    popularity: float  # 0..1


def member_score(prefs: MemberPrefs, poi: PoiInfo) -> float:
    if poi.id in prefs.avoid:
        return 0.0
    if poi.id in prefs.must_visit:
        return 1.0
    if prefs.interests:
        interest = max((prefs.interests.get(c, 0.0) for c in poi.categories), default=0.0) / 5.0
    else:
        interest = 0.5  # no stated interests: neutral
    return round(INTEREST_SHARE * min(interest, 1.0) + POPULARITY_SHARE * poi.popularity, 4)


def score_matrix(members: list[MemberPrefs], pois: list[PoiInfo]) -> dict[str, dict[int, float]]:
    return {m.name: {p.id: member_score(m, p) for p in pois} for m in members}


def aggregate(
    scores: dict[str, dict[int, float]],
    strategy: str = "fair",
    weights: dict[str, float] | None = None,
) -> dict[int, float]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    names = list(scores)
    if not names:
        return {}
    weights = weights or {n: 1.0 for n in names}
    total_w = sum(weights[n] for n in names)
    poi_ids = scores[names[0]].keys()
    out = {}
    for pid in poi_ids:
        vals = [scores[n][pid] for n in names]
        mean = sum(weights[n] * scores[n][pid] for n in names) / total_w
        low = min(vals)
        if strategy == "average":
            u = mean
        elif strategy == "least_misery":
            u = low
        else:
            u = 0.5 * mean + 0.5 * low
        out[pid] = round(u, 4)
    return out


def satisfaction(member_scores: dict[int, float], route_ids: list[int]) -> float:
    """Share of the best score the member could have got from a route of the same length.

    1.0 means the route contains that member's top-|route| POIs.
    """
    if not route_ids:
        return 0.0
    got = sum(member_scores.get(pid, 0.0) for pid in route_ids)
    best = sum(sorted(member_scores.values(), reverse=True)[: len(route_ids)])
    return round(got / best, 4) if best > 0 else 1.0
