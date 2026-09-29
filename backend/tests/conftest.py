import os
import uuid
from pathlib import Path

# Must be set before the app (and its engine) is imported.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://tripsolve:tripsolve@localhost:5433/tripsolve_test"
)
os.environ["GROQ_API_KEY"] = ""  # tests exercise the deterministic fallbacks

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from seed.seed import seed

    seed(Path(__file__).parents[1] / "seed" / "jaipur.json")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def offline_osrm(monkeypatch):
    """No network in tests: OSRM 'fails', so travel times use the labelled estimate."""
    from app.routing import osrm

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    monkeypatch.setattr(osrm, "_fetch_table_seconds", boom)
    monkeypatch.setattr("app.services.planner.route_geometry", lambda pts: (list(pts), "straight"))


@pytest.fixture
def auth_headers(client):
    email = f"u{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={"email": email, "name": "Tester", "password": "s3cret-pass"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def poi_ids(client):
    return {p["slug"]: p["id"] for p in client.get("/cities/jaipur/pois").json()}
