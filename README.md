# TripSolve

Optimization-grade group itinerary planner for Jaipur. It models the trip as a Team Orienteering Problem with Time Windows and solves it with Google OR-Tools. An LLM (served by Groq; default `openai/gpt-oss-120b`, since Llama 3.3 is no longer offered there) is used only to parse free text and to explain the route.

BIT Mesra (Off-Campus Jaipur), Minor Project, Semester 7. See `TripSolve_SRS_Report.pdf`.

## Architecture

```
frontend/  Next.js 16 + Leaflet     planner, group trips, share links, evaluation page
backend/   FastAPI
  app/solver/       TOPTW model (OR-Tools), schedule simulator, group aggregation   ← no DB/HTTP deps
  app/routing/      OSRM travel-time matrix + route geometry (cached in Postgres)
  app/llm/          Groq client, NL parser, explainer (all with non-LLM fallbacks)
  app/services/     planning pipeline, evaluation baselines
  app/routers/      REST API (auth, cities, plan, trips/shared, eval)
  seed/             Jaipur POI dataset (31 places) + loader
  eval/             scenarios + batch evaluation script
docs/solver.md      mathematical formulation (for the SDS)
docker-compose.yml  PostgreSQL 16 + PostGIS
```

## Running locally

Prerequisites: Docker Desktop, Python 3.12, Node 20+.

```bash
# 1. Database (host port 5433, because 5432 is taken by a local PostgreSQL)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env                                  # then set JWT_SECRET, and GROQ_API_KEY if you have one
python -m seed.seed                                     # load Jaipur POIs
uvicorn app.main:app --reload --port 8000               # API docs: http://localhost:8000/docs

# 3. Frontend
cd ../frontend
npm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
npm run dev                                             # http://localhost:3000
```

### Tests

```bash
docker exec tripsolve-db psql -U tripsolve -c "CREATE DATABASE tripsolve_test"   # once
cd backend && python -m pytest -q
```

There are 26 tests: solver unit tests (time windows, split hours, closed days, multi-day, must-visit, aggregation) and API tests (auth/401s, feasibility of every returned stop against raw opening hours, group share links, manual-edit checks, evaluation). The API tests mock OSRM, so they need no network.

### Evaluation (FR-14)

```bash
cd backend && python -m eval.run_eval      # writes eval/results/summary.md and results.csv
```

You can also use the **Evaluation** page in the UI. Results on the 6 scenarios (LLM = `openai/gpt-oss-120b` on Groq):

| Method | Time-window violations | Travel (min) | Requested stops included |
|---|---|---|---|
| TripSolve (OR-Tools) | **0** | **733** | 8/9 |
| Pure LLM | 10 | 738 | 9/9 |
| Naive manual plan | 18 | 869 | 9/9 |

The one requested stop TripSolve misses is Anokhi Museum in the `monday-museums` scenario, which is closed on Mondays. The LLM and naive plans "include" it by arriving at a closed museum. LLM output varies from run to run, so for the report, run the evaluation a few times and give the mean.

## Configuration notes

* **OSRM**: development uses the public demo server (`router.project-osrm.org`). For production, self-host OSRM with the Rajasthan/India extract and set `OSRM_URL`. If OSRM is unreachable, the API falls back to straight-line estimates and labels them `travel_time_source: "estimate"` in the response and the UI.
* **Traffic**: OSRM gives free-flow times. `TRAFFIC_FACTOR` (1.3) and `LEG_OVERHEAD_MINUTES` (5) adjust them for Jaipur traffic and parking.
* **LLM**: any OpenAI-compatible endpoint works (`LLM_BASE_URL`, `LLM_MODEL`). Without a key, parsing falls back to keyword matching and explanations use a template.

## Deployment (AWS)

TripSolve runs on a single EC2 `t3.small` using `docker-compose.prod.yml`: PostGIS, FastAPI, Next.js, and Caddy for automatic HTTPS. The browser only talks to Caddy, which forwards `/api/*` to FastAPI.
Follow [deploy/AWS_SETUP.md](deploy/AWS_SETUP.md), then run `bash deploy/deploy.sh <elastic-ip> <key.pem>`.

## Before evaluation: verify the data

The coordinates, opening hours and fees in `backend/seed/jaipur.json` are approximations. Check them against official or Google Maps listings, then re-run `python -m seed.seed` (it upserts by slug).
