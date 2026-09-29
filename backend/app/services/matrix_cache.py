from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import TravelTimeCache


class DbMatrixCache:
    """Pairwise OSRM duration cache in PostgreSQL (implements routing.osrm.MatrixCache)."""

    def __init__(self, db: Session):
        self.db = db

    def get_many(self, pairs, profile):
        if not pairs:
            return {}
        keys = {k for pair in pairs for k in pair}
        rows = self.db.execute(
            select(TravelTimeCache.src, TravelTimeCache.dst, TravelTimeCache.seconds).where(
                TravelTimeCache.profile == profile,
                TravelTimeCache.src.in_(keys),
                TravelTimeCache.dst.in_(keys),
            )
        ).all()
        wanted = set(pairs)
        return {(r.src, r.dst): r.seconds for r in rows if (r.src, r.dst) in wanted}

    def put_many(self, values, profile):
        if not values:
            return
        rows = [{"src": s, "dst": d, "profile": profile, "seconds": sec} for (s, d), sec in values.items()]
        stmt = insert(TravelTimeCache).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[TravelTimeCache.src, TravelTimeCache.dst, TravelTimeCache.profile],
            set_={"seconds": stmt.excluded.seconds},
        )
        self.db.execute(stmt)
        self.db.commit()
