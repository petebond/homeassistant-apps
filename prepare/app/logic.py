"""Readiness, expiry and reminder calculations. Pure functions over the database."""
from datetime import date, datetime, timedelta

from . import backup, db

PEOPLE_TYPES = ("adult", "child", "infant")


def today() -> date:
    return date.today()


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def days_until(s: str | None) -> int | None:
    d = parse_date(s)
    return (d - today()).days if d else None


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def household_counts() -> dict:
    members = db.rows("SELECT type FROM members")
    people = sum(1 for m in members if m["type"] in PEOPLE_TYPES)
    return {
        "people": people,
        "people_for_targets": max(people, 1),  # assume 1 until members are added
        "infants": sum(1 for m in members if m["type"] == "infant"),
        "pets": sum(1 for m in members if m["type"] == "pet"),
        "has_members": bool(members),
    }


def multiplier(basis: str, counts: dict, days: float) -> float:
    return {
        "person_day": counts["people_for_targets"] * days,
        "person": counts["people_for_targets"],
        "infant_day": counts["infants"] * days,
        "pet_day": counts["pets"] * days,
        "household": 1,
    }.get(basis, 1)


def is_usable(item: dict) -> bool:
    d = parse_date(item.get("best_before"))
    return d is None or d >= today()


def food_meals(items: list[dict]) -> dict:
    """How many meals the food makes. Bases and toppings only count in pairs.

    Meals on their own count one each. A portion of a base (pasta, rice) and a
    portion of a topping (sauce, curry) together make one meal, so the smaller of
    the two counts; the rest of the larger is spare until its other half is bought.
    Extras (biscuits, bars, milk) aren't counted. Items with no role yet count as meals."""
    t = {"meal": 0.0, "base": 0.0, "topping": 0.0, "extra": 0.0}
    for i in items:
        role = i.get("role") if i.get("role") in t else "meal"
        t[role] += i["quantity"] or 0
    paired = min(t["base"], t["topping"])
    return {
        "meals": round(t["meal"] + paired, 2),
        "own": round(t["meal"], 2),
        "paired": round(paired, 2),
        "base": round(t["base"], 2),
        "topping": round(t["topping"], 2),
        "extra": round(t["extra"], 2),
        "spare_base": round(t["base"] - paired, 2),
        "spare_topping": round(t["topping"] - paired, 2),
    }


def readiness() -> dict:
    s = db.settings()
    days = float(s.get("target_days") or 3)
    counts = household_counts()
    items = db.rows("SELECT * FROM items WHERE status='active'")
    cats = db.rows("SELECT * FROM categories ORDER BY sort, name")
    out, scored = [], []
    for c in cats:
        required = round(c["amount"] * multiplier(c["basis"], counts, days), 2)
        in_cat = [i for i in items if i["category"] == c["key"]]
        if c["key"] == "food":
            food = food_meals([i for i in in_cat if is_usable(i)])
            held = food["meals"]
            expired = food_meals([i for i in in_cat if not is_usable(i)])["meals"]
        else:
            held = round(sum(i["quantity"] or 0 for i in in_cat if is_usable(i)), 2)
            expired = round(sum(i["quantity"] or 0 for i in in_cat if not is_usable(i)), 2)
        applies = required > 0
        score = min(held / required, 1.0) if applies else None
        row = {**c, "required": required, "held": held, "expired_qty": expired,
               "food": food if c["key"] == "food" else None,
               "applies": applies, "score": score,
               "short": round(max(required - held, 0), 2) if applies else 0}
        out.append(row)
        if c["in_score"] and applies:
            scored.append(score)
    overall = round(100 * sum(scored) / len(scored)) if scored else 0

    def per_day(key):
        c = next((x for x in out if x["key"] == key), None)
        if not c or not c["amount"]:
            return None
        need = c["amount"] * counts["people_for_targets"]
        return round(c["held"] / need, 1) if need else None

    covered = [d for d in (per_day("water"), per_day("food")) if d is not None]
    return {
        "categories": out,
        "score": overall,
        "days_covered": min(covered) if covered else 0,
        "target_days": days,
        "counts": counts,
        "shortfall": [c for c in out if c["in_score"] and c["applies"] and c["short"] > 0],
    }


def expiring_items(window: int | None = None) -> dict:
    s = db.settings()
    window = int(s.get("warning_days") or 30) if window is None else window
    items = db.rows("SELECT * FROM items WHERE status='active' AND best_before IS NOT NULL AND best_before != '' ORDER BY best_before")
    soon, expired = [], []
    for i in items:
        d = days_until(i["best_before"])
        i["days_left"] = d
        if d is None:
            continue
        if d < 0:
            expired.append(i)
        elif d <= window:
            soon.append(i)
    return {"soon": soon, "expired": expired, "window": window}


def use_first(limit: int = 15) -> list[dict]:
    items = db.rows("SELECT * FROM items WHERE status='active' AND best_before IS NOT NULL AND best_before != '' ORDER BY best_before LIMIT ?", (limit,))
    for i in items:
        i["days_left"] = days_until(i["best_before"])
    return items


def medication_alerts() -> dict:
    s = db.settings()
    window = int(s.get("warning_days") or 30)
    repeat_window = int(s.get("repeat_warning_days") or 7)
    meds = db.rows("SELECT * FROM medications WHERE status='active'")
    expiring, expired, repeats = [], [], []
    for m in meds:
        d = days_until(m["expiry"])
        m["days_left"] = d
        if d is not None and d < 0:
            expired.append(m)
        elif d is not None and d <= window:
            expiring.append(m)
        r = days_until(m["repeat_due"])
        m["repeat_days"] = r
        if r is not None and r <= repeat_window:
            repeats.append(m)
    return {"expiring": expiring, "expired": expired, "repeats": repeats}


def pack_status() -> dict:
    s = db.settings()
    printed, changed = s.get("pack_last_printed") or "", s.get("data_changed_at") or ""
    return {
        "last_printed": printed,
        "out_of_date": (not printed) or (changed > printed),
    }


def reviews() -> dict:
    s = db.settings()
    months = int(s.get("review_months") or 6)
    kit = parse_date(s.get("kit_last_checked"))
    kit_due = add_months(kit, months) if kit else None
    plans = db.rows("SELECT id, scenario, last_reviewed FROM plans ORDER BY sort, id")
    plans_due = []
    for p in plans:
        lr = parse_date(p["last_reviewed"])
        if not lr or add_months(lr, months) <= today():
            plans_due.append(p)
    return {
        "months": months,
        "kit_last_checked": s.get("kit_last_checked") or "",
        "kit_due": (kit_due is None) or kit_due <= today(),
        "kit_due_date": kit_due.isoformat() if kit_due else "",
        "plans_due": plans_due,
    }


def waste_stats(days: int = 365) -> dict:
    since = (datetime.now() - timedelta(days=days)).isoformat()
    used = db.row("SELECT COUNT(*) n FROM events WHERE action='used' AND ts >= ?", (since,))["n"]
    thrown = db.row("SELECT COUNT(*) n FROM events WHERE action='discarded' AND ts >= ?", (since,))["n"]
    return {"used": used, "discarded": thrown}


def summary() -> dict:
    """Everything the HA integration needs, in one call."""
    r = readiness()
    e = expiring_items()
    m = medication_alerts()
    p = pack_status()
    v = reviews()
    bk = backup.status()
    return {
        "readiness": r["score"],
        "categories": {c["key"]: (round(c["score"] * 100) if c["score"] is not None else None)
                       for c in r["categories"] if c["in_score"]},
        "days_covered": r["days_covered"],
        "target_days": r["target_days"],
        "people": r["counts"]["people"],
        "pets": r["counts"]["pets"],
        "warning_days": e["window"],
        "items_expiring": len(e["soon"]),
        "items_expiring_list": [{"id": i["id"], "name": i["name"], "best_before": i["best_before"],
                                 "days_left": i["days_left"], "quantity": i["quantity"], "unit": i["unit"]}
                                for i in e["soon"]],
        "items_expired": len(e["expired"]),
        "items_expired_list": [{"id": i["id"], "name": i["name"], "best_before": i["best_before"]}
                               for i in e["expired"]],
        "meds_expiring": len(m["expiring"]) + len(m["expired"]),
        "meds_repeat_due": [{"id": x["id"], "name": x["name"], "repeat_due": x["repeat_due"]} for x in m["repeats"]],
        "shortfall": [{"key": c["key"], "name": c["name"], "short": c["short"], "unit": c["unit"]}
                      for c in r["shortfall"]],
        "pack_last_printed": p["last_printed"],
        "pack_out_of_date": p["out_of_date"],
        "kit_check_due": v["kit_due"],
        "plans_review_due": [x["scenario"] for x in v["plans_due"]],
        "food": next((c["food"] for c in r["categories"] if c["key"] == "food"), None),
        "backup_due": bk["due"],
        "backup_last": bk["last_at"],
        "backup_downloaded": bk["downloaded_at"],
    }


def food_note(f: dict) -> str:
    if f["spare_base"]:
        return f"; {f['spare_base']:g} portions of pasta, rice etc. need a sauce or topping"
    if f["spare_topping"]:
        return f"; {f['spare_topping']:g} portions of sauce etc. need pasta, rice or similar"
    return ""


def sections(r: dict | None = None) -> list[dict]:
    """Readiness per Be Ready checklist section, for the dashboard cards.

    A section's score is the average of its scored categories. Sections with
    nothing that applies to this household (no infant, no pet) are left out."""
    r = r or readiness()
    out = []
    for g in db.checklist_groups():
        cats = [c for c in r["categories"] if c.get("grp") == g["key"] and c["in_score"] and c["applies"]]
        if not cats:
            continue
        score = sum(c["score"] for c in cats) / len(cats)
        missing = [c for c in cats if c["score"] < 1]
        if not missing:
            note = "All there"
        elif len(cats) == 1:
            c = cats[0]
            note = f"{c['held']:g} of {c['required']:g} {c['unit']}"
            if c.get("food"):
                note += food_note(c["food"])
        else:
            names = [c["name"].split(",")[0].split(":")[0] for c in missing]
            names = [n if i == 0 or n[:2].isupper() else n[0].lower() + n[1:] for i, n in enumerate(names)]
            note = "Missing: " + ", ".join(names)
        out.append({**g, "score": score, "pct": round(score * 100), "note": note})
    return out
