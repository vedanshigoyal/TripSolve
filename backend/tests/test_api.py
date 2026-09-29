from app.schemas import hhmm_to_min

START = {"lat": 26.9124, "lon": 75.7873, "label": "Jaipur Junction"}
MONDAY = "2026-10-05"


def plan_body(**kw):
    body = {"date": MONDAY, "start_time": "09:00", "end_time": "18:00", "start_location": START,
            "members": [{"name": "You", "interests": {"fort": 5, "palace": 4}}]}
    body.update(kw)
    return body


def assert_feasible(client, resp, poi_by_id):
    """Independent check of FR-7: every visit starts and ends inside a declared opening interval."""
    assert resp["feasible"] and resp["metrics"]["time_window_violations"] == 0
    for day in resp["days"]:
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][
            __import__("datetime").date.fromisoformat(day["date"]).weekday()]
        for s in day["stops"]:
            hours = poi_by_id[s["poi"]["id"]]["opening_hours"][weekday]
            start, end = hhmm_to_min(s["start"]), hhmm_to_min(s["end"])
            assert any(hhmm_to_min(a) <= start and end <= hhmm_to_min(b) for a, b in hours), s


def test_health_and_catalogue(client):
    assert client.get("/health").json()["status"] == "ok"
    cats = client.get("/cities/jaipur/categories").json()
    assert "fort" in cats and "food" in cats
    assert client.get("/cities/atlantis/pois").status_code == 404


def test_guest_solo_plan_is_feasible(client):
    pois = {p["id"]: p for p in client.get("/cities/jaipur/pois").json()}
    r = client.post("/plan", json=plan_body())
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["metrics"]["stops"] >= 3
    assert resp["metrics"]["travel_time_source"] == "estimate"
    assert resp["explanation_source"] == "template" and resp["explanation"]
    assert_feasible(client, resp, pois)


def test_closed_monday_poi_is_skipped_with_reason(client, poi_ids):
    anokhi = poi_ids["anokhi-museum"]
    r = client.post("/plan", json=plan_body(members=[{"name": "You", "must_visit": [anokhi]}])).json()
    assert anokhi not in [s["poi"]["id"] for d in r["days"] for s in d["stops"]]
    skipped = {k["poi_id"]: k["reason"] for k in r["skipped"]}
    assert "closed" in skipped[anokhi]
    assert r["metrics"]["must_visit_missed"] == 1


def test_must_visit_is_honoured(client, poi_ids):
    galta = poi_ids["galta-ji"]
    r = client.post("/plan", json=plan_body(members=[{"name": "You", "interests": {"fort": 5},
                                                       "must_visit": [galta]}])).json()
    assert galta in [s["poi"]["id"] for d in r["days"] for s in d["stops"]]


def test_group_plan_reports_satisfaction(client):
    pois = {p["id"]: p for p in client.get("/cities/jaipur/pois").json()}
    body = plan_body(members=[
        {"name": "Asha", "interests": {"fort": 5, "heritage": 4}},
        {"name": "Ravi", "interests": {"food": 5, "shopping": 4}},
    ])
    resp = client.post("/plan", json=body).json()
    sat = resp["member_satisfaction"]
    assert set(sat) == {"Asha", "Ravi"} and all(v > 0.3 for v in sat.values())
    assert_feasible(client, resp, pois)


def test_duplicate_member_names_rejected(client):
    body = plan_body(members=[{"name": "A"}, {"name": "A"}])
    assert client.post("/plan", json=body).status_code == 422


def test_check_reports_violation_for_bad_manual_order(client, poi_ids):
    # Chokhi Dhani opens at 17:00 for 150 minutes; putting it first in a 09:00-14:00 day is infeasible.
    body = plan_body(end_time="14:00", route=[[poi_ids["chokhi-dhani"], poi_ids["hawa-mahal"]]])
    r = client.post("/plan/check", json=body).json()
    assert r["feasible"] is False
    assert r["days"][0]["stops"][0]["violation"]


def test_check_accepts_good_manual_order(client, poi_ids):
    body = plan_body(route=[[poi_ids["hawa-mahal"], poi_ids["city-palace"]]])
    r = client.post("/plan/check", json=body).json()
    assert r["feasible"] is True


def test_parse_fallback_without_llm(client):
    r = client.post("/plan/parse", json={"text": "We love forts and food, must see Hawa Mahal"}).json()
    assert r["used_llm"] is False
    assert {"fort", "food"} <= set(r["interests"])
    assert len(r["must_visit"]) == 1


def test_auth_rejects_bad_tokens(client):
    assert client.get("/trips").status_code == 401
    assert client.get("/trips", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_login_flow(client):
    client.post("/auth/register", json={"email": "login@example.com", "name": "L", "password": "password1"})
    assert client.post("/auth/login", json={"email": "login@example.com", "password": "wrong-pass"}).status_code == 401
    r = client.post("/auth/login", json={"email": "LOGIN@example.com", "password": "password1"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_group_trip_via_share_links(client, auth_headers):
    params = {k: v for k, v in plan_body().items() if k != "members"}
    trip = client.post("/trips", headers=auth_headers, json={
        "title": "Family weekend", "is_group": True, "params": params,
        "members": [{"name": "Organizer", "interests": {"palace": 5}}],
    }).json()
    assert trip["role"] == "owner" and trip["edit_token"] and trip["view_token"]

    # A member joins through the editable link and adds preferences.
    edit = trip["edit_token"]
    r = client.put(f"/shared/{edit}/members", json={"name": "Cousin", "interests": {"food": 5}})
    assert r.status_code == 200 and len(r.json()["members"]) == 2
    assert r.json()["edit_token"] is None  # editors can't see/escalate owner secrets

    solved = client.post(f"/shared/{edit}/solve").json()
    assert solved["result"]["member_satisfaction"].keys() == {"Organizer", "Cousin"}

    # The read-only link can see the route but not change anything.
    view = trip["view_token"]
    assert client.get(f"/shared/{view}").json()["role"] == "viewer"
    assert client.put(f"/shared/{view}/members", json={"name": "X"}).status_code == 403

    listing = client.get("/trips", headers=auth_headers).json()
    assert listing[0]["id"] == trip["id"] and listing[0]["members"] == 2

    assert client.delete(f"/trips/{trip['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/shared/{view}").status_code == 404


def test_other_users_cannot_see_trip(client, auth_headers):
    params = {k: v for k, v in plan_body().items() if k != "members"}
    trip = client.post("/trips", headers=auth_headers, json={"title": "Mine", "params": params}).json()
    other = client.post("/auth/register", json={"email": "other@example.com", "name": "O", "password": "password1"})
    if other.status_code == 409:
        other = client.post("/auth/login", json={"email": "other@example.com", "password": "password1"})
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/trips/{trip['id']}", headers=headers).status_code == 404


def test_eval_compare(client, poi_ids):
    body = plan_body(scenario="pytest", members=[{"name": "You", "interests": {"fort": 5, "museum": 3},
                                                  "must_visit": [poi_ids["albert-hall-museum"]]}])
    r = client.post("/eval/compare", json=body).json()
    res = r["results"]
    assert res["toptw"]["time_window_violations"] == 0
    assert res["naive"] is not None and res["llm"] is None  # no API key in tests
    assert res["toptw"]["requested_included"] == 1
