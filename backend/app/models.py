"""Database schema. City-agnostic: every POI belongs to a City, and nothing in the
solver or explanation code knows about Jaipur specifically (NFR 3.2.4)."""

import secrets
import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Json = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return secrets.token_urlsafe(16)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    center_lat: Mapped[float] = mapped_column(Float)
    center_lon: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")

    pois: Mapped[list["Poi"]] = relationship(back_populates="city")


class Poi(Base):
    __tablename__ = "pois"
    __table_args__ = (UniqueConstraint("city_id", "slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    slug: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    location = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    visit_minutes: Mapped[int] = mapped_column(Integer)
    popularity: Mapped[float] = mapped_column(Float, default=0.5)
    # {"mon": [["09:00", "17:00"]], "tue": [...], ...}; missing/empty day = closed.
    opening_hours: Mapped[dict] = mapped_column(Json)
    entry_fee_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)

    city: Mapped[City] = relationship(back_populates="pois")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    trips: Mapped[list["Trip"]] = relationship(back_populates="owner")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    title: Mapped[str] = mapped_column(String(200))
    is_group: Mapped[bool] = mapped_column(default=False)
    # PlanRequest fields (dates, times, start point, strategy, ...), minus members.
    params: Mapped[dict] = mapped_column(Json)
    # Last PlanResponse (route, schedule, explanation), or null before the first solve.
    result: Mapped[dict | None] = mapped_column(Json, nullable=True)
    view_token: Mapped[str] = mapped_column(String(32), unique=True, default=_token)
    edit_token: Mapped[str] = mapped_column(String(32), unique=True, default=_token)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    owner: Mapped[User] = relationship(back_populates="trips")
    city: Mapped[City] = relationship()
    members: Mapped[list["TripMember"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripMember.id"
    )


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (UniqueConstraint("trip_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # {"interests": {category: 0..5}, "must_visit": [poi_id], "avoid": [poi_id]}
    preferences: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    trip: Mapped[Trip] = relationship(back_populates="members")


class TravelTimeCache(Base):
    """Pairwise OSRM durations keyed by rounded coordinates."""

    __tablename__ = "travel_time_cache"

    src: Mapped[str] = mapped_column(String(40), primary_key=True)
    dst: Mapped[str] = mapped_column(String(40), primary_key=True)
    profile: Mapped[str] = mapped_column(String(16), primary_key=True)
    seconds: Mapped[float] = mapped_column(Float)


class EvalRun(Base):
    """One method's result on one evaluation scenario (FR-14)."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario: Mapped[str] = mapped_column(String(100), index=True)
    method: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
