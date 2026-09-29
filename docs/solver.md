# TOPTW formulation used by TripSolve

This is the optimisation model implemented in `backend/app/solver/toptw.py`. It is written so it can be pasted into the System Design Specification.

## Inputs

| Symbol | Meaning | Source |
|---|---|---|
| $V = \{1..n\}$ | candidate POIs (at most 30) | PostGIS radius query, ranked by group utility; must-visits always included |
| $0$ | the traveller's start point | user input |
| $K = \{1..D\}$ | one route ("team member") per trip day | `days` |
| $[a_k, b_k]$ | day $k$ time budget (absolute minutes) | `start_time`, `end_time` |
| $t_{ij}$ | travel minutes $i \to j$ | OSRM `table` × traffic factor (1.3) + 5 min per leg |
| $s_i$ | visit duration of POI $i$ | seed data |
| $W_i = \{[o_{i}^{r}, c_{i}^{r}]\}$ | opening intervals of $i$ on the trip dates (split hours and closed days allowed) | seed data by weekday |
| $u_i \in [0,1]$ | aggregated group utility | `aggregation.py` |
| $M \subseteq V$ | must-visit POIs | members' must-visit list and POIs kept in the editor |

## Decision variables (as OR-Tools models them)

* $x_{ijk} \in \{0,1\}$: route $k$ goes directly from $i$ to $j$ (OR-Tools `NextVar` / `VehicleVar`)
* $y_i \in \{0,1\}$: POI $i$ is visited (OR-Tools `ActiveVar`, via a disjunction)
* $T_i \ge 0$: time the visit to $i$ starts (the `Time` dimension cumul)

## Objective

$$\min \; \sum_{k}\sum_{i,j} t_{ij}\,x_{ijk} \;+\; \sum_{i \in V \setminus M} P\,u_i^{3}\,(1-y_i) \;+\; \sum_{i \in M} P_M (1-y_i)$$

where $P = 1000$ and $P_M = 10^7$. Because the utility term dominates, minimising the objective maximises the value of the POIs visited. Travel time only breaks ties between plans of equal value, which is the orienteering objective.

The cube ($u^3$) is a deliberate modelling choice. With a linear value, a 150-minute headline attraction (Amber Fort for a fort lover) lost to three short stops of middling interest, simply because their values summed higher. With $u^3$, one place scored 1.0 is worth eight places scored 0.5. We tested exponents 1, 2 and 3 on the Jaipur data; only 3 kept Amber Fort.

## Constraints

1. Each route starts at $0$ at or after $a_k$ and ends (at $0$ if `return_to_start`, otherwise at a zero-cost dummy node) by $b_k$.
2. Each POI is visited at most once over all routes (disjunction).
3. Time propagation: $x_{ijk}=1 \Rightarrow T_j \ge T_i + s_i + t_{ij}$. Waiting is allowed (dimension slack).
4. **Time windows:** $y_i = 1 \Rightarrow \exists r: o_i^r \le T_i \le c_i^r - s_i$. The visit must *start and finish* inside one opening interval. This is modelled by restricting the cumul's domain and removing the gaps between intervals (`CumulVar.RemoveInterval`).

## Solving

* First solution: `PARALLEL_CHEAPEST_INSERTION`. `PATH_CHEAPEST_ARC` stalled on the "visit nothing" solution for multi-day trips with must-visits; a regression test covers this.
* Improvement: Guided Local Search with a 2 s limit (NFR: < 5 s for ~30 POIs).

## Feasibility guarantee (FR-7)

The solver's visiting order is re-simulated independently by `schedule.py`, using earliest feasible start times. If that simulation ever finds a violation, the offending stop is removed and the route is simulated again, so the API never returns a violating route even if the solver had a bug. The API tests check every returned visit against the raw opening hours a third time.

## Group fairness (FR-5)

For each member $m$: $s_m(p) = 0.75\,\max_{c \in cat(p)} w_m(c)/5 + 0.25\,\text{popularity}(p)$. This is 1 for must-visit and 0 for avoid.

* `average`: $u_p = \sum_m \lambda_m s_m(p) / \sum_m \lambda_m$
* `least_misery`: $u_p = \min_m s_m(p)$
* `fair` (default): $u_p = \tfrac12\,\text{average} + \tfrac12\,\text{least\_misery}$

After solving, the satisfaction of each member is measured as $\text{sat}_m = \sum_{p \in \text{route}} s_m(p) \,/\, \sum_{p \in \text{top-}|route|(m)} s_m(p)$. Weights $\lambda_m$ of under-served members are then scaled by $\overline{\text{sat}} / \text{sat}_m$ and the model is re-solved, for up to 3 rounds. The route with the best worst-off member wins (leximin on min satisfaction, then total utility). Satisfaction percentages are shown to users and fed to the explanation.

## Explanations (FR-10)

The explanation is built from facts, not opinions. For each skipped POI, the reason comes from checks the code actually runs:

* whether the POI is open during the trip at all;
* whether it could be inserted anywhere in the final route without breaking a time window or the budget;
* whether it is outranked by what was chosen.

The LLM only turns those facts into prose. It receives no way to alter the route, and a deterministic template is used when no LLM is configured.
