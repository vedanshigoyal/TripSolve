"""Free text -> structured preferences (FR-2).

The LLM output is validated against a strict schema and every category / POI it names
is checked against the database. Anything unknown is discarded, and if the output is
unusable the caller gets `ok=False` and must fall back to the structured form
(NFR 3.2.2): invalid data never reaches the solver.
"""

import re

from pydantic import BaseModel, Field, ValidationError, field_validator

from .client import chat_json

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class LlmPreferences(BaseModel):
    interests: dict[str, float] = Field(default_factory=dict)
    must_visit: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None
    days: int | None = Field(default=None, ge=1, le=5)

    @field_validator("start_time", "end_time")
    @classmethod
    def _hhmm(cls, v):
        return v if v is None or HHMM.match(v) else None


class ParseResult(BaseModel):
    ok: bool
    used_llm: bool
    interests: dict[str, float] = Field(default_factory=dict)
    must_visit: list[int] = Field(default_factory=list)
    avoid: list[int] = Field(default_factory=list)
    start_time: str | None = None
    end_time: str | None = None
    days: int | None = None
    message: str = ""


SYSTEM = """You convert a tourist's trip description into JSON for a route planner.
Return ONLY a JSON object with these keys:
  "interests": object mapping category -> importance 0-5 (5 = loves it, 0 = not interested). Use only the allowed categories.
  "must_visit": list of attraction names the user explicitly insists on. Use only names from the allowed list, spelled exactly.
  "avoid": list of attraction names the user explicitly wants to skip, from the allowed list.
  "start_time": "HH:MM" 24-hour if the user states when they start, else null.
  "end_time": "HH:MM" 24-hour if the user states when they must finish, else null.
  "days": integer number of days if stated, else null.
Do not invent preferences the user did not express. Do not plan a route."""


def parse_preferences(text: str, categories: list[str], pois: dict[str, int]) -> ParseResult:
    """`pois` maps attraction name -> id for the city being planned."""
    user = (
        f"Allowed categories: {', '.join(categories)}\n"
        f"Allowed attractions: {'; '.join(pois)}\n\n"
        f"Traveller's description:\n{text.strip()[:2000]}"
    )
    data = chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    if data is None:
        return _keyword_fallback(text, categories, pois)
    try:
        parsed = LlmPreferences.model_validate(data)
    except ValidationError:
        return ParseResult(ok=False, used_llm=True,
                           message="Couldn't understand that description. Please use the form below.")

    allowed = set(categories)
    by_lower = {name.lower(): pid for name, pid in pois.items()}
    interests = {c: max(0.0, min(5.0, float(w))) for c, w in parsed.interests.items() if c in allowed and w > 0}
    return ParseResult(
        ok=True,
        used_llm=True,
        interests=interests,
        must_visit=[by_lower[n.lower()] for n in parsed.must_visit if n.lower() in by_lower],
        avoid=[by_lower[n.lower()] for n in parsed.avoid if n.lower() in by_lower],
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        days=parsed.days,
    )


def _keyword_fallback(text: str, categories: list[str], pois: dict[str, int]) -> ParseResult:
    """No LLM available: match category words and attraction names literally."""
    low = text.lower()
    interests = {c: 4.0 for c in categories if re.search(rf"\b{re.escape(c)}", low)}
    must = [pid for name, pid in pois.items() if name.split(" (")[0].lower() in low]
    ok = bool(interests or must)
    return ParseResult(
        ok=ok,
        used_llm=False,
        interests=interests,
        must_visit=must,
        message="" if ok else "AI parsing is unavailable and no known interests were found. Please use the form below.",
    )
