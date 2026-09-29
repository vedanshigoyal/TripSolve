"""Run every scenario in eval/scenarios.json through TOPTW, naive and pure-LLM planners.

    python -m eval.run_eval            # from backend/, with the DB running

Writes eval/results/results.csv and eval/results/summary.md (a table for the report).
Set GROQ_API_KEY in .env to include the pure-LLM baseline.
"""

import csv
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.routers.evaluation import load_scenarios, scenario_request
from app.services.evaluation import METHODS, compare

OUT = Path(__file__).with_name("results")
FIELDS = ["stops", "total_travel_minutes", "time_window_violations", "requested_included", "requested_total",
          "total_utility", "runtime_ms", "note"]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []
    with SessionLocal() as db:
        for sc in load_scenarios():
            res = compare(db, scenario_request(db, sc), scenario=sc["name"],
                          time_limit=get_settings().solver_time_limit_seconds)
            print(f"{sc['name']:<24} candidates={res['candidates']} travel={res['travel_time_source']}")
            for method in METHODS:
                m = res["results"][method]
                if m is None:
                    print(f"   {method:<6} skipped (no GROQ_API_KEY, or the LLM call failed; see log)")
                    continue
                rows.append({"scenario": sc["name"], "method": method, **m})
                print(f"   {method:<6} stops={m['stops']:<3} travel={m['total_travel_minutes']:<4} "
                      f"violations={m['time_window_violations']:<3} requested={m['requested_included']}/{m['requested_total']}")

    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["scenario", "method", *FIELDS])
        w.writeheader()
        w.writerows(rows)

    lines = [f"# TripSolve evaluation ({datetime.now():%Y-%m-%d %H:%M})", "",
             "| Scenario | Method | Stops | Travel (min) | Time-window violations | Requested included | Utility |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['method']} | {r['stops']} | {r['total_travel_minutes']} | "
                     f"{r['time_window_violations']} | {r['requested_included']}/{r['requested_total']} | {r['total_utility']} |")
    lines += ["", "## Totals", "", "| Method | Violations | Travel (min) | Requested included |", "|---|---|---|---|"]
    for method in METHODS:
        mr = [r for r in rows if r["method"] == method]
        if mr:
            lines.append(f"| {method} | {sum(r['time_window_violations'] for r in mr)} | "
                         f"{sum(r['total_travel_minutes'] for r in mr)} | "
                         f"{sum(r['requested_included'] for r in mr)}/{sum(r['requested_total'] for r in mr)} |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT / 'results.csv'} and {OUT / 'summary.md'}")


if __name__ == "__main__":
    main()
