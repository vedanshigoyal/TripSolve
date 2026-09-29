"""Plain-language explanation of a solved route (FR-10).

The planner computes the *facts* (what was included, what was dropped and the verified
reason, member satisfaction). The LLM only rewrites those facts into friendly prose; it
never sees a way to change the route. Without an LLM, `template_explanation` renders
the same facts directly.
"""

import json

from .client import chat

SYSTEM = """You explain a sightseeing plan that an optimisation solver has ALREADY computed.
Write for a tourist with no technical background, in 90-170 words, second person, short paragraphs or bullet points.
Rules:
- Use ONLY the facts in the JSON. Do not add attractions, times, prices or opinions that are not given.
- Do not suggest a different order or new stops; the route is final.
- Mention why the most important skipped places were left out, using the reason given.
- For groups, say briefly how everyone's interests were balanced, using the satisfaction numbers as percentages.
- Plain text only: no markdown (no **, #, or backticks). Use "- " at the start of a line for bullet points."""


def llm_explanation(facts: dict) -> str | None:
    text = chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        temperature=0.3,
        max_tokens=450,
    )
    return text.strip() if text else None


def template_explanation(facts: dict) -> str:
    lines = []
    visits = facts["included"]
    if not visits:
        lines.append("No attraction could be fitted into your time window with its opening hours. "
                     "Try a longer time budget or a different day.")
    else:
        top = sorted(visits, key=lambda v: -v["value"])[:3]
        lines.append(
            f"Your plan covers {len(visits)} stop{'s' if len(visits) != 1 else ''} with about "
            f"{facts['total_travel_minutes']} minutes of travel. The highest-value picks for you were "
            + ", ".join(v["name"] for v in top) + "."
        )
        waits = [v for v in visits if v["wait_minutes"] >= 10]
        if waits:
            w = waits[0]
            lines.append(f"There is a {w['wait_minutes']}-minute wait before {w['name']} because it opens at {w['start']}.")
    for d in facts["skipped"][:4]:
        lines.append(f"{d['name']} was left out: {d['reason']}.")
    if len(facts["skipped"]) > 4:
        lines.append(f"{len(facts['skipped']) - 4} lower-priority places were also skipped.")
    sat = facts.get("member_satisfaction")
    if sat:
        parts = ", ".join(f"{name} {round(v * 100)}%" for name, v in sat.items())
        lines.append(f"To keep things fair, the route balances everyone's interests (how well each person's "
                     f"top picks are covered: {parts}).")
    if facts.get("travel_time_source") == "estimate":
        lines.append("Note: live road travel times were unavailable, so travel times are estimates.")
    return "\n\n".join(lines)
