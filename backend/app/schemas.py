import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
Strategy = Literal["fair", "average", "least_misery"]


def hhmm_to_min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------- auth ----------

class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- POIs ----------

class PoiOut(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    lat: float
    lon: float
    categories: list[str]
    visit_minutes: int
    popularity: float
    opening_hours: dict
    entry_fee_inr: int | None


class CityOut(BaseModel):
    slug: str
    name: str
    center_lat: float
    center_lon: float


# ---------- planning ----------

class LatLonIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = "Start"


class MemberIn(BaseModel):
    name: str = Field(default="You", min_length=1, max_length=100)
    interests: dict[str, float] = Field(default_factory=dict)
    must_visit: list[int] = Field(default_factory=list)
    avoid: list[int] = Field(default_factory=list)

    @field_validator("interests")
    @classmethod
    def _clamp(cls, v):
        return {k: max(0.0, min(5.0, float(w))) for k, w in v.items()}


class TripParams(BaseModel):
    """Everything about a trip except who is in it."""

    city: str = "jaipur"
    date: dt.date = Field(default_factory=dt.date.today)
    days: int = Field(default=1, ge=1, le=5)
    start_time: str = "09:00"
    end_time: str = "18:00"
    start_location: LatLonIn
    return_to_start: bool = True
    strategy: Strategy = "fair"
    radius_km: float = Field(default=40, gt=0, le=200)
    exclude: list[int] = Field(default_factory=list)  # removed by the user on the map
    include: list[int] = Field(default_factory=list)  # kept by the user when re-optimising

    @field_validator("start_time", "end_time")
    @classmethod
    def _hhmm(cls, v):
        if not HHMM.match(v):
            raise ValueError("expected HH:MM (24-hour)")
        return v

    @model_validator(mode="after")
    def _order(self):
        if hhmm_to_min(self.end_time) - hhmm_to_min(self.start_time) < 60:
            raise ValueError("end_time must be at least an hour after start_time")
        return self


class PlanRequest(TripParams):
    members: list[MemberIn] = Field(default_factory=lambda: [MemberIn()], min_length=1, max_length=12)
    explain: bool = True

    @model_validator(mode="after")
    def _unique_names(self):
        names = [m.name for m in self.members]
        if len(set(names)) != len(names):
            raise ValueError("member names must be unique")
        return self


class CheckRequest(PlanRequest):
    """A user-edited route: POI ids in visiting order, one list per day (FR-9)."""

    route: list[list[int]]
    explain: bool = False


class StopOut(BaseModel):
    poi: PoiOut
    arrival: str
    start: str
    end: str
    wait_minutes: int
    travel_minutes: int
    utility: float
    violation: str | None = None


class DayOut(BaseModel):
    day: int
    date: dt.date
    start: str
    end: str
    travel_minutes: int
    return_travel_minutes: int
    stops: list[StopOut]
    geometry: list[tuple[float, float]]
    violations: list[str]


class SkippedOut(BaseModel):
    poi_id: int
    name: str
    utility: float
    reason: str


class Metrics(BaseModel):
    stops: int
    total_travel_minutes: int
    total_utility: float
    time_window_violations: int
    solve_ms: int
    candidates: int
    travel_time_source: str
    must_visit_missed: int


class PlanResponse(BaseModel):
    feasible: bool
    days: list[DayOut]
    skipped: list[SkippedOut]
    metrics: Metrics
    member_satisfaction: dict[str, float] | None = None
    explanation: str | None = None
    explanation_source: Literal["llm", "template"] | None = None


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    city: str = "jaipur"


# ---------- trips ----------

class MemberPrefsIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    interests: dict[str, float] = Field(default_factory=dict)
    must_visit: list[int] = Field(default_factory=list)
    avoid: list[int] = Field(default_factory=list)


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    is_group: bool = False
    params: TripParams
    members: list[MemberPrefsIn] = Field(default_factory=list)
    result: PlanResponse | None = None


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    params: TripParams | None = None
    result: PlanResponse | None = None


class MemberOut(MemberPrefsIn):
    id: int


class TripOut(BaseModel):
    id: str
    title: str
    is_group: bool
    city: str
    params: TripParams
    members: list[MemberOut]
    result: PlanResponse | None
    owner_name: str
    role: Literal["owner", "editor", "viewer"]
    view_token: str | None = None
    edit_token: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class TripSummary(BaseModel):
    id: str
    title: str
    is_group: bool
    date: dt.date
    days: int
    members: int
    stops: int | None
    updated_at: dt.datetime
