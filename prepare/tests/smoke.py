"""Smoke test: run against a live server. python tests/smoke.py http://localhost:8999"""
import sys
from datetime import date, timedelta

import httpx

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8999"
c = httpx.Client(base_url=B, follow_redirects=True, timeout=10)
d = lambda n: (date.today() + timedelta(days=n)).isoformat()


def ok(r, *needles):
    assert r.status_code == 200, (r.request.url, r.status_code, r.text[:500])
    for n in needles:
        assert n in r.text, (r.request.url, n)
    return r


for p in ["/", "/items", "/meds", "/kit", "/plans", "/contacts", "/household", "/print", "/settings", "/offline"]:
    ok(c.get(p))
ok(c.get("/plans"), "Power cut", "105")

# household
ok(c.post("/members", data={"name": "Pete", "type": "adult"}))
ok(c.post("/members", data={"name": "Sam", "type": "adult"}))
ok(c.post("/members", data={"name": "Kid", "type": "child", "dietary": "no nuts"}))
ok(c.post("/members", data={"name": "Rex", "type": "pet"}))
ok(c.post("/members/1", data={"name": "Pete B", "type": "adult"}), "Pete B")
ok(c.post("/household", data={"household_name": "Bondy household", "meeting_near": "Village hall"}), "Village hall")

# items
ok(c.post("/items", data={"name": "Water 2L", "category": "water", "quantity": "12", "best_before": d(400)}))
ok(c.post("/items", data={"name": "Beans", "category": "food", "quantity": "10", "best_before": d(10)}))
ok(c.post("/items", data={"name": "Old soup", "category": "food", "quantity": "2", "best_before": d(-5)}))
ok(c.post("/items", data={"name": "Torch", "category": "torch", "quantity": "1"}))
ok(c.post("/items", data={"name": "Rice", "category": "food", "quantity": "8", "best_before": d(200), "next": "/"}), "How ready")
s = c.get("/api/summary").json()
print("summary", {k: s[k] for k in ("readiness", "days_covered", "items_expiring", "items_expired", "people", "pets")})
assert s["people"] == 3 and s["pets"] == 1
assert s["items_expired"] == 1 and s["items_expiring"] == 1
# water 12L / (3L x 3 people) = 1.3 days; food (10+8)=18 meals / 9 per day = 2.0
assert s["days_covered"] == 1.3, s["days_covered"]

items = c.get("/api/items").json()
beans = [i for i in items if i["name"] == "Beans"][0]
ok(c.post(f"/items/{beans['id']}/used", data={"qty": "4"}))
assert [i for i in c.get("/api/items").json() if i["name"] == "Beans"][0]["quantity"] == 6
soup = [i for i in items if i["name"] == "Old soup"][0]
ok(c.post(f"/items/{soup['id']}/discard", data={}))
rice = [i for i in items if i["name"] == "Rice"][0]
ok(c.post(f"/items/{rice['id']}/used", data={"qty": "3"}))
r = c.get("/api/items").json()
assert [i for i in r if i["name"] == "Rice"][0]["quantity"] == 5
ok(c.get(f"/items/{rice['id']}"), "Edit: Rice")
ok(c.post(f"/items/{rice['id']}", data={"name": "Rice 1kg", "category": "food", "quantity": "6", "best_before": d(150)}))
ok(c.get("/items?show=all"), "used", "discarded")

# API add/consume
j = c.post("/api/items", json={"name": "Batteries AA", "category": "batteries", "quantity": 1}).json()
assert c.post(f"/api/items/{j['id']}/consume", json={}).json()["left"] == 0

# meds
ok(c.post("/meds", data={"name": "Paracetamol", "strength": "500mg", "dose": "2 tabs up to 4x/day", "expiry": d(20)}), "Paracetamol")
ok(c.post("/meds", data={"name": "Inhaler", "owner_id": "2", "dose": "2 puffs", "repeat_due": d(3), "expiry": d(300)}), "Inhaler")
ok(c.get("/meds/2"), "Edit: Inhaler")
ok(c.post("/meds/2", data={"name": "Inhaler (blue)", "owner_id": "2", "dose": "2 puffs", "repeat_due": d(3)}), "Inhaler (blue)")
ok(c.get("/"), "Request repeat prescription", "Medication expires soon")

# contacts
ok(c.post("/contacts", data={"name": "Gran", "role": "family", "phone": "01747 000000"}), "Gran")
ok(c.post("/contacts/1", data={"name": "Granny", "role": "family", "phone": "01747 000001"}), "Granny")

# plans
ok(c.post("/plans", data={"scenario": "Heatwave"}), "Edit plan: Heatwave")
pid = 8
ok(c.post(f"/plans/{pid}", data={"scenario": "Heatwave", "steps": "Close curtains\nDrink water", "roles": "Pete: check on neighbours"}), "Close curtains")
ok(c.post("/plans/1/reviewed"))

# kit + settings
ok(c.post("/kit", data={"amount_water": "4", "score_water": "1", "amount_car": "1"}))
ok(c.post("/kit/checked"), "Last checked: " + date.today().isoformat())
ok(c.post("/settings", data={"warning_days": "14", "target_days": "3", "review_months": "6"}))
assert c.get("/api/summary").json()["warning_days"] == 14

# print
assert c.get("/api/summary").json()["pack_out_of_date"] is True
ok(c.get("/print"), "EMERGENCY PACK: Bondy household", "Granny", "Inhaler (blue)", "Heatwave", "Village hall")
ok(c.post("/print/mark"))
s = c.get("/api/summary").json()
assert s["pack_out_of_date"] is False, s
ok(c.post("/contacts", data={"name": "Neighbour", "role": "neighbour"}))
assert c.get("/api/summary").json()["pack_out_of_date"] is True

# ingress base path
r = ok(c.get("/items", headers={"X-Ingress-Path": "/api/hassio_ingress/abc"}), 'href="/api/hassio_ingress/abc/plans"')
r = c.post("/members", data={"name": "X", "type": "adult"}, headers={"X-Ingress-Path": "/api/hassio_ingress/abc"}, follow_redirects=False)
assert r.headers["location"] == "/api/hassio_ingress/abc/household", r.headers
ok(c.get("/manifest.webmanifest"), "Prepare")
ok(c.get("/sw.js"), "CACHE")
print("ALL OK")
print(c.get("/api/summary").json())
