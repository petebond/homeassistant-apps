"""Prepare - household emergency preparedness. Deliberately plain: server-rendered HTML forms."""
import asyncio
import json
import logging
import os
import re
import socket
import ssl
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, installer, logic, products, tls

log = logging.getLogger("prepare")
HERE = Path(__file__).parent
VERSION = "0.3.2"

app = FastAPI(title="Prepare", version=VERSION, docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _nicedate(value) -> str:
    """'2026-10-23' -> '23 Oct', with the year added when it isn't this year."""
    d = logic.parse_date(value) if value else None
    if not d:
        return ""
    out = f"{d.day} {MONTHS[d.month - 1]}"
    return out if d.year == logic.today().year else f"{out} {d.year}"


def _monthyear(value) -> str:
    d = logic.parse_date(value) if value else None
    return f"{MONTHS[d.month - 1]} {d.year}" if d else ""


templates.env.filters["nicedate"] = _nicedate
templates.env.filters["monthyear"] = _monthyear

MEMBER_TYPES = ["adult", "child", "infant", "pet"]
CONTACT_ROLES = ["family", "neighbour", "friend", "school / childcare", "GP / medical", "utility", "work", "other"]


# ---------- helpers ----------

@app.middleware("http")
async def middleware(request: Request, call_next):
    # Ingress serves the app under a path prefix; direct ports serve it at /.
    request.state.base = request.headers.get("X-Ingress-Path", "").rstrip("/")
    response = await call_next(request)
    path = request.url.path
    # Anything that changes what the printed pack shows makes the pack out of date.
    if (request.method == "POST" and response.status_code < 400
            and not path.endswith(("/mark", "/checked", "/reviewed")) and path != "/settings"):
        db.mark_changed()
    return response


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.update(
        request=request,
        b=request.state.base,
        today=logic.today().isoformat(),
        version=VERSION,
        pack=logic.pack_status(),
        household_name=db.settings().get("household_name", ""),
    )
    return templates.TemplateResponse(request, name, ctx)


def back(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(request.state.base + path, status_code=303)


async def form(request: Request) -> dict:
    f = await request.form()
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in f.items()}


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def opt_date(v) -> str | None:
    return v if v and logic.parse_date(v) else None


def categories() -> list[dict]:
    return db.rows("SELECT * FROM categories ORDER BY sort, name")


def members() -> list[dict]:
    return db.rows("SELECT * FROM members ORDER BY CASE type WHEN 'adult' THEN 0 WHEN 'child' THEN 1 WHEN 'infant' THEN 2 ELSE 3 END, name")


# ---------- dashboard ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    r = logic.readiness()
    return render(
        request, "dashboard.html", sections=logic.sections(r),
        r=r, e=logic.expiring_items(), m=logic.medication_alerts(),
        v=logic.reviews(), first=logic.use_first(10), waste=logic.waste_stats(),
    )


# ---------- inventory ----------

@app.get("/items", response_class=HTMLResponse)
def items_page(request: Request, show: str = "active", cat: str = "", group: str = "", view: str = "products"):
    cats = categories()
    groups = db.checklist_groups()
    group_keys = {g["key"] for g in groups}
    in_group = {g["key"]: [c["key"] for c in cats if c.get("grp") == g["key"]] for g in groups}
    in_group["other"] = [c["key"] for c in cats if c.get("grp") not in group_keys]
    sql = "SELECT * FROM items WHERE 1=1"
    args: list = []
    if show != "all":
        sql += " AND status='active'"
    if cat:
        sql += " AND category=?"
        args.append(cat)
    elif group in in_group:
        keys = in_group[group] or ["-"]
        sql += f" AND category IN ({','.join('?' * len(keys))})"
        args += keys
    else:
        group = ""
    sql += " ORDER BY CASE WHEN best_before IS NULL OR best_before='' THEN 1 ELSE 0 END, best_before, name"
    items = db.rows(sql, args)
    for i in items:
        i["days_left"] = logic.days_until(i["best_before"])
    # How many in-stock rows each button would show, so empty sections are obvious.
    active = db.rows("SELECT category FROM items WHERE status='active'")
    counts = {k: sum(1 for i in active if i["category"] in keys) for k, keys in in_group.items()}
    cmap = {c["key"]: c for c in cats}
    default_cat = cat or (in_group.get(group) or [""])[0]
    sec = next((x for x in logic.sections() if x["key"] == group), None)
    if sec is None and group in group_keys:  # e.g. Baby with no infant in the household
        g = next(g for g in groups if g["key"] == group)
        sec = {**g, "pct": 0, "note": "Not counted for this household"}
    view = "batches" if view == "batches" else "products"
    here = "/items" + (f"?group={group}" if group else f"?cat={cat}" if cat else "")
    return render(request, "items.html", items=items, cats=cats, cmap=cmap, show=show, cat=cat, group=group,
                  groups=groups, counts=counts, total=len(active), default_cat=default_cat, sec=sec, here=here,
                  view=view, bundles=bundle(items), generics=products.known_generics(),
                  warning=int(db.settings().get("warning_days") or 30))


def bundle(items: list[dict]) -> list[dict]:
    """Group batches by product type: every brand of chopped tomatoes under one heading.

    Each batch keeps its own row (and best-before date); the heading adds them up
    and shows the earliest date, which is the one to act on."""
    groups: dict[str, dict] = {}
    for i in items:
        label = (i.get("generic") or i["name"]).strip()
        key = f"{label.lower()}|{i['unit']}"
        g = groups.setdefault(key, {"label": label, "unit": i["unit"], "category": i["category"], "batches": [],
                                    "quantity": 0.0, "brands": [], "first": None})
        g["batches"].append(i)
        if i["status"] == "active":
            g["quantity"] += i["quantity"] or 0
        brand = i.get("brand") or ""
        if brand and brand not in g["brands"]:
            g["brands"].append(brand)
        if i["status"] == "active" and i["days_left"] is not None and (g["first"] is None or i["days_left"] < g["first"]["days_left"]):
            g["first"] = i
    out = list(groups.values())
    for g in out:
        g["brands"].sort(key=str.lower)
    out.sort(key=lambda g: (g["first"] is None, g["first"]["days_left"] if g["first"] else 0, g["label"].lower()))
    return out


def item_values(f: dict) -> tuple:
    cat = db.row("SELECT unit FROM categories WHERE key=?", (f.get("category"),))
    unit = f.get("unit") or (cat["unit"] if cat else "")
    generic = (f.get("generic") or "").strip()
    return (f.get("name") or "Unnamed", f.get("category") or "other", num(f.get("quantity"), 1), unit,
            f.get("location", ""), opt_date(f.get("best_before")), 1 if f.get("perishable") else 0,
            f.get("notes", ""), (f.get("brand") or "").strip(), match_generic(generic),
            products.normalise_barcode(f.get("barcode") or "") or None)


ITEM_COLS = "name, category, quantity, unit, location, best_before, perishable, notes, brand, generic, barcode"


def match_generic(name: str) -> str:
    """Use the household's existing spelling of a product type, so case and spacing never split a group."""
    name = " ".join((name or "").split())
    if not name:
        return ""
    for g in products.known_generics():
        if g.lower() == name.lower():
            return g
    return name[:1].upper() + name[1:]


@app.post("/items")
async def item_add(request: Request):
    f = await form(request)
    vals = item_values(f)
    db.execute(f"INSERT INTO items({ITEM_COLS}, added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", vals + (db.now_iso(),))
    db.log("added", f"{vals[0]} {vals[2]:g} {vals[3]}")
    return back(request, f.get("next") or "/items")


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item_edit_page(request: Request, item_id: int):
    item = db.row("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        return back(request, "/items")
    return render(request, "item_edit.html", item=item, cats=categories(), generics=products.known_generics())


@app.post("/items/{item_id}")
async def item_edit(request: Request, item_id: int):
    f = await form(request)
    db.execute("UPDATE items SET name=?, category=?, quantity=?, unit=?, location=?, best_before=?, perishable=?, notes=?, "
               "brand=?, generic=?, barcode=? WHERE id=?", item_values(f) + (item_id,))
    return back(request, "/items")


# ---------- scanning ----------

@app.get("/scan", response_class=HTMLResponse)
def scan_page(request: Request, added: int = 0, loc: str = ""):
    last = db.row("SELECT * FROM items WHERE id=?", (added,)) if added else None
    recent = db.rows("SELECT * FROM items WHERE barcode IS NOT NULL AND barcode != '' ORDER BY id DESC LIMIT 6")
    return render(request, "scan.html", cats=categories(), generics=products.known_generics(), last=last, loc=loc,
                  recent=recent, cmap={c["key"]: c for c in categories()},
                  locations=[r["location"] for r in db.rows("SELECT DISTINCT location FROM items WHERE location != '' ORDER BY location")])


@app.get("/api/lookup/{code}")
async def api_lookup(code: str):
    # Network lookups block, so run them off the event loop.
    return await asyncio.get_running_loop().run_in_executor(None, products.lookup, code, VERSION)


@app.post("/scan/add")
async def scan_add(request: Request):
    f = await form(request)
    code = products.normalise_barcode(f.get("barcode") or "") or ""
    category = f.get("category") or "food"
    cat = db.row("SELECT unit FROM categories WHERE key=?", (category,))
    packs = max(num(f.get("packs"), 1), 0)
    each = max(num(f.get("pack_amount"), 1), 0)
    generic = match_generic(f.get("generic") or "")
    name = (f.get("name") or generic or "Unnamed").strip()
    brand = (f.get("brand") or "").strip()
    iid = db.execute(
        f"INSERT INTO items({ITEM_COLS}, added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, category, round(packs * each, 3), cat["unit"] if cat else "", f.get("location", ""),
         opt_date(f.get("best_before")), 0, "", brand, generic, code or None, db.now_iso()),
    )
    if code:
        products.remember(code, name, brand, generic, category, each, f.get("quantity_text", ""),
                          f.get("source") or "manual", f.get("image_url", ""))
    db.log("added", f"{name} x{packs:g} (scanned)")
    from urllib.parse import urlencode
    return back(request, "/scan?" + urlencode({"added": iid, "loc": f.get("location", "")}))


def consume(item_id: int, qty: float | None, action: str) -> dict | None:
    item = db.row("SELECT * FROM items WHERE id=?", (item_id,))
    if not item:
        return None
    take = item["quantity"] if qty is None or qty <= 0 or qty >= item["quantity"] else qty
    left = round(item["quantity"] - take, 3)
    if left <= 0:
        db.execute("UPDATE items SET status=?, quantity=0 WHERE id=?", ("used" if action == "used" else "discarded", item_id))
    else:
        db.execute("UPDATE items SET quantity=? WHERE id=?", (left, item_id))
    db.log(action, f"{item['name']} {take:g} {item['unit']}")
    return {"id": item_id, "name": item["name"], "taken": take, "left": max(left, 0)}


@app.post("/items/{item_id}/used")
async def item_used(request: Request, item_id: int):
    f = await form(request)
    consume(item_id, num(f.get("qty"), 0) or None, "used")
    return back(request, f.get("next") or "/items")


@app.post("/items/{item_id}/discard")
async def item_discard(request: Request, item_id: int):
    f = await form(request)
    consume(item_id, None, "discarded")
    return back(request, f.get("next") or "/items")


@app.post("/items/{item_id}/delete")
def item_delete(request: Request, item_id: int):
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    return back(request, "/items")


# ---------- medication ----------

@app.get("/meds", response_class=HTMLResponse)
def meds_page(request: Request):
    meds = db.rows("SELECT * FROM medications WHERE status='active' ORDER BY owner_id IS NOT NULL, owner_id, name")
    for m in meds:
        m["days_left"] = logic.days_until(m["expiry"])
        m["repeat_days"] = logic.days_until(m["repeat_due"])
    people = [x for x in members() if x["type"] != "pet"] + [x for x in members() if x["type"] == "pet"]
    return render(request, "meds.html", meds=meds, people=people, pmap={p["id"]: p["name"] for p in people})


def med_values(f: dict) -> tuple:
    owner = f.get("owner_id")
    return (f.get("name") or "Unnamed", f.get("strength", ""), f.get("dose", ""), f.get("quantity", ""),
            opt_date(f.get("expiry")), int(owner) if owner else None, opt_date(f.get("repeat_due")), f.get("notes", ""))


@app.post("/meds")
async def med_add(request: Request):
    f = await form(request)
    db.execute("INSERT INTO medications(name, strength, dose, quantity, expiry, owner_id, repeat_due, notes) VALUES (?,?,?,?,?,?,?,?)",
               med_values(f))
    return back(request, "/meds")


@app.get("/meds/{med_id}", response_class=HTMLResponse)
def med_edit_page(request: Request, med_id: int):
    med = db.row("SELECT * FROM medications WHERE id=?", (med_id,))
    if not med:
        return back(request, "/meds")
    return render(request, "med_edit.html", med=med, people=members())


@app.post("/meds/{med_id}")
async def med_edit(request: Request, med_id: int):
    f = await form(request)
    db.execute("UPDATE medications SET name=?, strength=?, dose=?, quantity=?, expiry=?, owner_id=?, repeat_due=?, notes=? WHERE id=?",
               med_values(f) + (med_id,))
    return back(request, "/meds")


@app.post("/meds/{med_id}/delete")
def med_delete(request: Request, med_id: int):
    db.execute("DELETE FROM medications WHERE id=?", (med_id,))
    return back(request, "/meds")


# ---------- household ----------

@app.get("/household", response_class=HTMLResponse)
def household_page(request: Request):
    return render(request, "household.html", members=members(), types=MEMBER_TYPES,
                  fields=db.HOUSEHOLD_FIELDS, s=db.settings())


@app.post("/members")
async def member_add(request: Request):
    f = await form(request)
    t = f.get("type") if f.get("type") in MEMBER_TYPES else "adult"
    db.execute("INSERT INTO members(name, type, dietary, notes) VALUES (?,?,?,?)",
               (f.get("name") or "Unnamed", t, f.get("dietary", ""), f.get("notes", "")))
    return back(request, "/household")


@app.post("/members/{mid}")
async def member_edit(request: Request, mid: int):
    f = await form(request)
    t = f.get("type") if f.get("type") in MEMBER_TYPES else "adult"
    db.execute("UPDATE members SET name=?, type=?, dietary=?, notes=? WHERE id=?",
               (f.get("name") or "Unnamed", t, f.get("dietary", ""), f.get("notes", ""), mid))
    return back(request, "/household")


@app.post("/members/{mid}/delete")
def member_delete(request: Request, mid: int):
    db.execute("UPDATE medications SET owner_id=NULL WHERE owner_id=?", (mid,))
    db.execute("DELETE FROM members WHERE id=?", (mid,))
    return back(request, "/household")


@app.post("/household")
async def household_save(request: Request):
    f = await form(request)
    for key, _, _ in db.HOUSEHOLD_FIELDS:
        if key in f:
            db.set_setting(key, f[key])
    return back(request, "/household")


# ---------- contacts ----------

@app.get("/contacts", response_class=HTMLResponse)
def contacts_page(request: Request, edit: int = 0):
    return render(request, "contacts.html", contacts=db.rows("SELECT * FROM contacts ORDER BY role, name"),
                  roles=CONTACT_ROLES, edit=edit)


@app.post("/contacts")
async def contact_add(request: Request):
    f = await form(request)
    db.execute("INSERT INTO contacts(name, role, phone, phone2, notes) VALUES (?,?,?,?,?)",
               (f.get("name") or "Unnamed", f.get("role", ""), f.get("phone", ""), f.get("phone2", ""), f.get("notes", "")))
    return back(request, "/contacts")


@app.post("/contacts/{cid}")
async def contact_edit(request: Request, cid: int):
    f = await form(request)
    db.execute("UPDATE contacts SET name=?, role=?, phone=?, phone2=?, notes=? WHERE id=?",
               (f.get("name") or "Unnamed", f.get("role", ""), f.get("phone", ""), f.get("phone2", ""), f.get("notes", ""), cid))
    return back(request, "/contacts")


@app.post("/contacts/{cid}/delete")
def contact_delete(request: Request, cid: int):
    db.execute("DELETE FROM contacts WHERE id=?", (cid,))
    return back(request, "/contacts")


# ---------- plans ----------

@app.get("/plans", response_class=HTMLResponse)
def plans_page(request: Request):
    return render(request, "plans.html", plans=db.rows("SELECT * FROM plans ORDER BY sort, id"),
                  general=db.general_actions(), s=db.settings(), v=logic.reviews())


@app.post("/plans")
async def plan_add(request: Request):
    f = await form(request)
    pid = db.execute("INSERT INTO plans(scenario, sort) VALUES (?, 999)", (f.get("scenario") or "New scenario",))
    return back(request, f"/plans/{pid}")


@app.get("/plans/{pid}", response_class=HTMLResponse)
def plan_edit_page(request: Request, pid: int):
    plan = db.row("SELECT * FROM plans WHERE id=?", (pid,))
    if not plan:
        return back(request, "/plans")
    return render(request, "plan_edit.html", plan=plan)


@app.post("/plans/{pid}")
async def plan_edit(request: Request, pid: int):
    f = await form(request)
    db.execute("UPDATE plans SET scenario=?, steps=?, meeting_point=?, roles=?, grab_bag=?, notes=?, info_url=?, last_reviewed=? WHERE id=?",
               (f.get("scenario") or "Unnamed", f.get("steps", ""), f.get("meeting_point", ""), f.get("roles", ""),
                f.get("grab_bag", ""), f.get("notes", ""), f.get("info_url", ""), logic.today().isoformat(), pid))
    return back(request, f"/plans#plan-{pid}")


@app.post("/plans/{pid}/reviewed")
def plan_reviewed(request: Request, pid: int):
    db.execute("UPDATE plans SET last_reviewed=? WHERE id=?", (logic.today().isoformat(), pid))
    return back(request, f"/plans#plan-{pid}")


@app.post("/plans/{pid}/delete")
def plan_delete(request: Request, pid: int):
    db.execute("DELETE FROM plans WHERE id=?", (pid,))
    return back(request, "/plans")


# ---------- kit targets ----------

@app.get("/kit", response_class=HTMLResponse)
def kit_page(request: Request):
    return render(request, "kit.html", r=logic.readiness(), v=logic.reviews())


@app.post("/kit")
async def kit_save(request: Request):
    f = await form(request)
    for c in categories():
        k = c["key"]
        if f"amount_{k}" in f:
            db.execute("UPDATE categories SET amount=?, in_score=? WHERE key=?",
                       (num(f.get(f"amount_{k}"), c["amount"]), 1 if f.get(f"score_{k}") else 0, k))
    return back(request, "/kit")


@app.post("/kit/checked")
def kit_checked(request: Request):
    db.set_setting("kit_last_checked", logic.today().isoformat())
    db.log("kit_checked")
    return back(request, "/kit")


# ---------- settings ----------

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    events = db.rows("SELECT * FROM events ORDER BY id DESC LIMIT 50")
    return render(request, "settings.html", s=db.settings(), events=events)


@app.post("/settings")
async def settings_save(request: Request):
    f = await form(request)
    for key in ("warning_days", "target_days", "review_months", "repeat_warning_days"):
        if key in f and num(f[key], -1) >= 0:
            db.set_setting(key, f"{num(f[key]):g}")
    return back(request, "/settings")


# ---------- print pack ----------

def pack_context() -> dict:
    meds = db.rows("SELECT * FROM medications WHERE status='active' ORDER BY owner_id IS NOT NULL, owner_id, name")
    items = db.rows("SELECT * FROM items WHERE status='active' ORDER BY category, best_before IS NULL, best_before, name")
    for i in items:
        i["days_left"] = logic.days_until(i["best_before"])
    return dict(
        s=db.settings(), members=members(), meds=meds, pmap={m["id"]: m["name"] for m in members()},
        contacts=db.rows("SELECT * FROM contacts ORDER BY role, name"),
        plans=db.rows("SELECT * FROM plans ORDER BY sort, id"), general=db.general_actions(),
        r=logic.readiness(), items=items, cmap={c["key"]: c for c in categories()},
        fields=db.HOUSEHOLD_FIELDS,
    )


@app.get("/print", response_class=HTMLResponse)
def print_page(request: Request):
    return render(request, "print.html", **pack_context())


@app.post("/print/mark")
def print_mark(request: Request):
    db.set_setting("pack_last_printed", db.now_iso())
    db.log("printed")
    return back(request, "/print")


@app.get("/offline", response_class=HTMLResponse)
def offline_page(request: Request):
    return render(request, "offline.html")


# ---------- PWA ----------

@app.get("/manifest.webmanifest")
def manifest(request: Request):
    b = request.state.base
    return JSONResponse({
        "name": "Prepare - Home Emergency System",
        "short_name": "Prepare",
        "start_url": f"{b}/",
        "scope": f"{b}/",
        "display": "standalone",
        "background_color": "#182889",
        "theme_color": "#182889",
        "icons": [
            {"src": f"{b}/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": f"{b}/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(HERE / "static" / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


# ---------- JSON API (used by the HA integration) ----------

@app.get("/api/summary")
def api_summary():
    return logic.summary()


@app.get("/api/items")
def api_items():
    return db.rows("SELECT * FROM items WHERE status='active' ORDER BY best_before IS NULL, best_before, name")


@app.post("/api/items")
async def api_item_add(request: Request):
    f = await request.json()
    iid = db.execute(f"INSERT INTO items({ITEM_COLS}, added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     item_values({k: str(v) if v is not None else "" for k, v in f.items()}) + (db.now_iso(),))
    db.log("added", f"{f.get('name')} (via HA)")
    return {"id": iid}


@app.post("/api/items/{item_id}/consume")
async def api_item_consume(request: Request, item_id: int):
    try:
        f = await request.json()
    except json.JSONDecodeError:
        f = {}
    res = consume(item_id, num(f.get("quantity"), 0) or None, "discarded" if f.get("discard") else "used")
    return res or JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/print/mark")
def api_print_mark():
    db.set_setting("pack_last_printed", db.now_iso())
    db.log("printed", "via HA")
    return {"pack_last_printed": db.settings()["pack_last_printed"]}


@app.get("/api/health")
def api_health():
    return {"ok": True, "version": VERSION}


# ---------- HTTPS with a private CA (same approach as the Meal Planner app) ----------
#
# Browsers only install a PWA and cache it for offline use on https. A home
# network has no public name for a real certificate, so the app runs a tiny CA
# of its own (kept in /data/certs) and each phone trusts it once, from /setup.

HTTPS_PORT = 8998
CERT_DIR = db.DATA_DIR / "certs"
LEARNED_HOSTS_FILE = CERT_DIR / "learned.hosts"
MAX_LEARNED_HOSTS = 12
BASE_HOSTS = ["127.0.0.1", "localhost", "homeassistant.local", "homeassistant", "prepare"]
TLS_STATE = {"ca": None, "config": None, "fingerprint": "", "hosts": [], "learned": []}
_tls_lock = threading.Lock()
_HOST_OK = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$")


def usable_host(host: str) -> bool:
    """The Host header is client-controlled and ends up in the certificate: hostname or IPv4 only."""
    return bool(host) and len(host) <= 253 and bool(_HOST_OK.match(host)) and not host.startswith("172.30.")


def load_learned_hosts() -> list[str]:
    try:
        lines = [x.strip() for x in LEARNED_HOSTS_FILE.read_text().splitlines()]
    except OSError:
        return []
    out = []
    for h in lines:
        if h and h not in out and usable_host(h):
            out.append(h)
    return out[:MAX_LEARNED_HOSTS]


def start_https(hosts: list[str]) -> "uvicorn.Server | None":
    """Make or reuse the certificate and return the HTTPS server. Never fatal."""
    learned = load_learned_hosts()
    hosts = list(dict.fromkeys(hosts + BASE_HOSTS + learned))
    try:
        crt, key, ca = tls.ensure(str(CERT_DIR), hosts)
    except (tls.TLSUnavailable, OSError) as exc:
        log.error("HTTPS could not start: %s. Plain http on 8999 is unaffected.", exc)
        return None
    config = uvicorn.Config(app, host="0.0.0.0", port=HTTPS_PORT, ssl_certfile=crt, ssl_keyfile=key,
                            proxy_headers=True, log_level="info")
    TLS_STATE.update(ca=ca, config=config, fingerprint=tls.fingerprint(ca), hosts=hosts, learned=learned)
    return uvicorn.Server(config)


def cover_host(host_header: str) -> bool:
    """Make sure the certificate covers the address the phone used for /setup.

    The app runs in a bridged container and can't see the address typed into the
    phone, so the moment a phone opens /setup over plain http is when it's learned."""
    if not TLS_STATE["config"]:
        return False
    host = (host_header or "").rsplit(":", 1)[0].strip().lower()
    if not usable_host(host) or host in TLS_STATE["hosts"]:
        return False
    with _tls_lock:
        if host in TLS_STATE["hosts"] or len(TLS_STATE["learned"]) >= MAX_LEARNED_HOSTS:
            return False
        hosts = TLS_STATE["hosts"] + [host]
        try:
            crt, key, _ca = tls.ensure(str(CERT_DIR), hosts)
            ctx = getattr(TLS_STATE["config"], "ssl", None)
            if ctx is not None:  # live reload: new connections get the new certificate
                ctx.load_cert_chain(crt, key)
        except (tls.TLSUnavailable, ssl.SSLError, OSError) as exc:
            log.warning("Could not add %s to the certificate: %s", host, exc)
            return False
        TLS_STATE["hosts"] = hosts
        TLS_STATE["learned"] = TLS_STATE["learned"] + [host]
        try:
            LEARNED_HOSTS_FILE.write_text("\n".join(TLS_STATE["learned"]) + "\n")
        except OSError as exc:
            log.warning("Could not remember certificate addresses: %s", exc)
        return True


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    host_header = request.headers.get("host", "")
    if request.url.scheme == "http":
        cover_host(host_header)
    host = host_header.rsplit(":", 1)[0] or lan_ip()
    ua = request.headers.get("user-agent", "").lower()
    apple = "iphone" in ua or "ipad" in ua
    return render(request, "setup.html", ready=bool(TLS_STATE["ca"]), host=host, https_port=HTTPS_PORT,
                  fingerprint=TLS_STATE["fingerprint"], apple=apple)


@app.get("/ca.crt")
def ca_cert():
    if not TLS_STATE["ca"]:
        return JSONResponse({"error": "https is not switched on"}, status_code=404)
    return FileResponse(TLS_STATE["ca"], media_type="application/x-x509-ca-cert", filename="prepare-ca.crt")


# ---------- startup ----------

def load_options() -> dict:
    path = Path(os.environ.get("PREPARE_OPTIONS", "/data/options.json"))
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def supervisor_discovery() -> None:
    """Tell HA the App exists so the companion integration can be set up with one click."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log.warning("No SUPERVISOR_TOKEN - can't announce the app for discovery")
        return
    body = json.dumps({"service": "prepare", "config": {"host": socket.gethostname(), "port": 8999}}).encode()
    req = urllib.request.Request("http://supervisor/discovery", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        log.info("Supervisor discovery sent")
    except Exception as exc:  # noqa: BLE001 - discovery is a convenience, never fatal
        log.warning("Supervisor discovery failed: %s", exc)


def lan_ip() -> str:
    """Best-effort local address (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def load_container_environment(path: str = "/run/s6/container_environment") -> None:
    """Pick up the variables Supervisor gave the container.

    The base image runs s6 as PID 1, and s6 starts the app with a cleaned
    environment: SUPERVISOR_TOKEN (needed to announce the app for discovery)
    and TZ (UK time rather than UTC) never reach it. s6 keeps them as one file
    per variable here, so read them back in."""
    folder = Path(path)
    if not folder.is_dir():
        return
    for f in folder.iterdir():
        if f.is_file() and f.name not in os.environ:
            try:
                os.environ[f.name] = f.read_text().strip()
            except OSError:
                pass
    if hasattr(time, "tzset"):
        time.tzset()


async def serve() -> None:
    load_container_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init()
    opts = load_options()
    if opts.get("install_integration", True):
        installer.install()
    servers = [uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8999, proxy_headers=True, log_level="info"))]
    log.info("Plain HTTP view on port 8999")
    if opts.get("https_enabled"):
        extra = [h.strip() for h in (opts.get("cert_hosts") or "").split(",") if h.strip()]
        https = start_https([lan_ip()] + extra)
        if https:
            servers.append(https)
            log.info("HTTPS view on port %d. Set phones up at http://<home assistant>:8999/setup", HTTPS_PORT)
    else:
        log.info("https_enabled is off - port %d (HTTPS/PWA) not started", HTTPS_PORT)
    await asyncio.get_running_loop().run_in_executor(None, supervisor_discovery)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(serve())
