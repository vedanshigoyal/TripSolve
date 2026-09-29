"""Saved trips, group members and share links (FR-11, FR-12, UC-2, UC-5).

A trip is reachable in two ways:
  * /trips/{id}        by its owner (JWT);
  * /shared/{token}    by anyone with a link: view_token = read-only, edit_token = can add
                       their preferences, re-solve and save route edits.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Trip, TripMember, User
from ..schemas import (MemberOut, MemberPrefsIn, PlanRequest, PlanResponse, TripCreate, TripOut, TripParams,
                       TripSummary, TripUpdate)
from ..services import planner

router = APIRouter(tags=["trips"])


# ---------- helpers ----------

def _trip_out(trip: Trip, role: str) -> TripOut:
    return TripOut(
        id=trip.id,
        title=trip.title,
        is_group=trip.is_group,
        city=trip.city.slug,
        params=TripParams.model_validate(trip.params),
        members=[MemberOut(id=m.id, name=m.name, **m.preferences) for m in trip.members],
        result=PlanResponse.model_validate(trip.result) if trip.result else None,
        owner_name=trip.owner.name,
        role=role,
        view_token=trip.view_token if role != "viewer" else None,
        edit_token=trip.edit_token if role == "owner" else None,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
    )


def _owned(db: Session, trip_id: str, user: User) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.owner_id != user.id:
        raise HTTPException(404, "Trip not found")
    return trip


def _by_token(db: Session, token: str, need_edit: bool = False) -> tuple[Trip, str]:
    trip = db.scalar(select(Trip).where(or_(Trip.view_token == token, Trip.edit_token == token)))
    if trip is None:
        raise HTTPException(404, "This link is invalid or the trip was deleted")
    role = "editor" if trip.edit_token == token else "viewer"
    if need_edit and role != "editor":
        raise HTTPException(403, "This is a read-only link")
    return trip, role


def _prefs(m: MemberPrefsIn) -> dict:
    return {"interests": m.interests, "must_visit": m.must_visit, "avoid": m.avoid}


def _upsert_member(db: Session, trip: Trip, body: MemberPrefsIn) -> None:
    existing = next((m for m in trip.members if m.name == body.name), None)
    if existing:
        existing.preferences = _prefs(body)
    else:
        trip.members.append(TripMember(name=body.name, preferences=_prefs(body)))
    db.commit()


def _solve(db: Session, trip: Trip) -> None:
    if not trip.members:
        raise HTTPException(422, "Add at least one member's preferences before planning")
    req = PlanRequest(**trip.params, members=[{"name": m.name, **m.preferences} for m in trip.members])
    trip.result = planner.plan(db, req).model_dump(mode="json")
    db.commit()


def _apply_update(db: Session, trip: Trip, body: TripUpdate) -> None:
    if body.title is not None:
        trip.title = body.title
    if body.params is not None:
        planner.get_city(db, body.params.city)
        trip.params = body.params.model_dump(mode="json")
    if body.result is not None:
        trip.result = body.result.model_dump(mode="json")
    db.commit()


# ---------- owner endpoints ----------

@router.post("/trips", response_model=TripOut, status_code=201)
def create_trip(body: TripCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    city = planner.get_city(db, body.params.city)
    trip = Trip(owner_id=user.id, city_id=city.id, title=body.title, is_group=body.is_group,
                params=body.params.model_dump(mode="json"),
                result=body.result.model_dump(mode="json") if body.result else None,
                members=[TripMember(name=m.name, preferences=_prefs(m)) for m in body.members])
    db.add(trip)
    db.commit()
    return _trip_out(trip, "owner")


@router.get("/trips", response_model=list[TripSummary])
def my_trips(db: Session = Depends(get_db), user: User = Depends(current_user)):
    trips = db.scalars(select(Trip).where(Trip.owner_id == user.id).order_by(Trip.updated_at.desc()))
    out = []
    for t in trips:
        p = TripParams.model_validate(t.params)
        stops = t.result["metrics"]["stops"] if t.result else None
        out.append(TripSummary(id=t.id, title=t.title, is_group=t.is_group, date=p.date, days=p.days,
                               members=len(t.members), stops=stops, updated_at=t.updated_at))
    return out


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _trip_out(_owned(db, trip_id, user), "owner")


@router.patch("/trips/{trip_id}", response_model=TripOut)
def update_trip(trip_id: str, body: TripUpdate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    trip = _owned(db, trip_id, user)
    _apply_update(db, trip, body)
    return _trip_out(trip, "owner")


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_owned(db, trip_id, user))
    db.commit()
    return Response(status_code=204)


@router.put("/trips/{trip_id}/members", response_model=TripOut)
def owner_upsert_member(trip_id: str, body: MemberPrefsIn, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    trip = _owned(db, trip_id, user)
    _upsert_member(db, trip, body)
    return _trip_out(trip, "owner")


@router.delete("/trips/{trip_id}/members/{member_id}", response_model=TripOut)
def owner_remove_member(trip_id: str, member_id: int, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    trip = _owned(db, trip_id, user)
    trip.members = [m for m in trip.members if m.id != member_id]
    db.commit()
    return _trip_out(trip, "owner")


@router.post("/trips/{trip_id}/solve", response_model=TripOut)
def owner_solve(trip_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    trip = _owned(db, trip_id, user)
    _solve(db, trip)
    return _trip_out(trip, "owner")


# ---------- share-link endpoints ----------

@router.get("/shared/{token}", response_model=TripOut)
def shared_trip(token: str, db: Session = Depends(get_db)):
    trip, role = _by_token(db, token)
    return _trip_out(trip, role)


@router.put("/shared/{token}/members", response_model=TripOut)
def shared_upsert_member(token: str, body: MemberPrefsIn, db: Session = Depends(get_db)):
    trip, role = _by_token(db, token, need_edit=True)
    _upsert_member(db, trip, body)
    return _trip_out(trip, role)


@router.delete("/shared/{token}/members/{member_id}", response_model=TripOut)
def shared_remove_member(token: str, member_id: int, db: Session = Depends(get_db)):
    trip, role = _by_token(db, token, need_edit=True)
    trip.members = [m for m in trip.members if m.id != member_id]
    db.commit()
    return _trip_out(trip, role)


@router.post("/shared/{token}/solve", response_model=TripOut)
def shared_solve(token: str, db: Session = Depends(get_db)):
    trip, role = _by_token(db, token, need_edit=True)
    _solve(db, trip)
    return _trip_out(trip, role)


@router.patch("/shared/{token}", response_model=TripOut)
def shared_update(token: str, body: TripUpdate, db: Session = Depends(get_db)):
    trip, role = _by_token(db, token, need_edit=True)
    _apply_update(db, trip, body)
    return _trip_out(trip, role)
