import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import auth, cities, evaluation, plan, trips

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="TripSolve API",
    description="Optimization-grade group itinerary planner (TOPTW via OR-Tools).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, cities.router, plan.router, trips.router, evaluation.router):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health", tags=["meta"])
def health():
    s = get_settings()
    return {"status": "ok", "llm_enabled": s.llm_enabled, "osrm_url": s.osrm_url}
