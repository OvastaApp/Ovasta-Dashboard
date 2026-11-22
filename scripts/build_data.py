#!/usr/bin/env python3
"""Turn dashboard_dump.json (from dashboard_refresh.py) into public/data.json for the static dashboard.

  python build_data.py [--dump dashboard_dump.json] [--labels complaints_classified.json] [--out public/data.json]

* No PII and no free text leaves this script: data.json holds only counts, money totals, dates,
  district names and complaint categories. Ticket / rating text is read only to classify it.
* Complaint labels: the manual labels in complaints_classified.json win for every ticket / low rating
  they cover; anything newer is labelled by classifier.py (deterministic keyword rules; unclear -> other).
  A low rating that opened a ticket takes the ticket's label, like the manual labels.
* Exit code 2 if the dump is unusable (missing months or errors in a required step), so the daily job
  does not publish broken data.
"""
import argparse, collections, datetime, json, os, re, sys
from classifier import classify

HERE = os.path.dirname(os.path.abspath(__file__))
FIRST_MONTH = "2026-02"
CATS = ["delay", "courier", "quality", "missing_wrong", "pricing", "app", "other"]
REQUIRED_STEPS = ("md_", "last_day", "tickets", "low_ratings", "rating_dist")

def z(v): return round(v or 0)
def dk(r): return "0" if r.get("is_total") else str(r["district_id"])
def ts(s): return datetime.datetime.fromisoformat(str(s)[:19])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=os.path.join(HERE, "dashboard_dump.json"))
    ap.add_argument("--labels", default=os.path.join(HERE, "complaints_classified.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "public", "data.json"))
    a = ap.parse_args()
    o = json.load(open(a.dump, encoding="utf-8"))
    errs = o.get("errors") or {}
    bad = [k for k in errs if k.startswith(REQUIRED_STEPS)]
    if bad or not o.get("months"):
        print("dump not usable, errors in:", bad or "months missing"); sys.exit(2)

    sess = o["session"]
    pulled = ts(sess["cairo_now"]); run_day = ts(sess["cairo_today"] + "T00:00:00" if len(str(sess["cairo_today"])) == 10 else sess["cairo_today"])

    # ---- monthly metrics ----
    M, partial = {}, None
    for m in o["months"]:
        M[m["month"]] = {dk(r): [r["placed"], r["delivered"], r["cancelled"], r["open"], z(r["gmv"]), z(r["nmv"]),
                                 z(r["delivery_fees"]), r["active_customers"], r["delivered_normal"], r["delivered_anything"]]
                         for r in (m["by_district"] or [])}
        if m.get("partial") and m.get("through"):
            start = datetime.datetime.strptime(m["month"] + "-01", "%Y-%m-%d")
            days = max((ts(m["through"]) - start).total_seconds() / 86400, 0.01)
            partial = {"month": m["month"], "through": str(m["through"])[:16], "days": round(days, 2)}
    used = {d for mm, v in M.items() if mm >= FIRST_MONTH for d, r in v.items() if d != "0" and r[0] > 0}
    districts = [{"id": str(d["id"]), "en": d["en_name"].strip(), "ar": d["ar_name"].strip()}
                 for d in o["districts"] if str(d["id"]) in used]

    # ---- last working day ----
    if o.get("last_day"):
        L = o["last_day"]; until = None; is_partial = False
    else:   # dumps from before v3 only have today's partial day
        L = dict(o["today"], is_yesterday=False, days_back=0); until = str(o["today"]["pulled_at_cairo"])[11:16]; is_partial = True
    hours = {h["hour"]: h for h in (L.get("by_hour") or [])}
    last_day = {"date": L.get("date"), "is_yesterday": bool(L.get("is_yesterday")), "days_back": L.get("days_back"),
                "partial": is_partial, "until": until,
                "by_district": {dk(r): [r["placed"], r["delivered"], r["cancelled"], r["open"], z(r["nmv"]), z(r["gmv"]), z(r["open_value"])]
                                for r in (L.get("by_district") or [])},
                "by_hour": [[hours.get(h, {}).get("placed", 0), hours.get(h, {}).get("delivered", 0)] for h in range(24)]}

    # ---- complaint labels: manual first, classifier for the rest ----
    man = json.load(open(a.labels, encoding="utf-8")) if os.path.exists(a.labels) else {"tickets": [], "low_ratings": []}
    mt = {t["id"]: t for t in man["tickets"]}
    mr = {r["sales_order_id"]: r for r in man["low_ratings"] if r.get("ticket_id") is None}
    n_manual = n_auto = 0
    tickets = []
    for t in o.get("tickets") or []:
        if t["id"] in mt:
            lab = mt[t["id"]]; prim, excl = lab["primary"], lab["excluded_from_pct"]; n_manual += 1
        else:
            prim, tag, _ = classify(t.get("text")); excl = tag == "empty"; n_auto += 1
        tickets.append({"day": str(t["created_at"])[:10], "d": str(t["district_id"]), "solved": bool(t["is_solved"]),
                        "cat": prim, "excl": excl, "from_rating": bool(t.get("sales_order_id"))})
    t_by_order = {}
    for t, x in zip(o.get("tickets") or [], tickets):
        if t.get("sales_order_id"): t_by_order[t["sales_order_id"]] = x
    lows = []
    for r in o.get("low_ratings") or []:
        if r["sales_order_id"] in t_by_order:
            x = t_by_order[r["sales_order_id"]]; prim, excl = x["cat"], x["excl"]
        elif r["sales_order_id"] in mr:
            lab = mr[r["sales_order_id"]]; prim, excl = lab["primary"], lab["excluded_from_pct"]; n_manual += 1
        else:
            prim, tag, _ = classify(r.get("rating_comment")); excl = tag == "empty"; n_auto += 1
        lows.append({"m": str(r["created_at"])[:7], "d": str(r["district_id"]), "rating": r["rating"], "cat": prim, "excl": excl})

    CA, LA, RD = {}, {}, {}
    for x in tickets:
        mm = x["day"][:7]
        if mm < FIRST_MONTH: continue
        for k in (x["d"], "0"):
            c = CA.setdefault(mm, {}).setdefault(k, [0] * 11)
            c[0] += 1; c[2] += x["solved"]; c[10] += x["from_rating"]
            if not x["excl"]: c[1] += 1; c[3 + CATS.index(x["cat"])] += 1
    for x in lows:
        for k in (x["d"], "0"):
            c = LA.setdefault(x["m"], {}).setdefault(k, [0] * 12)
            c[0] += 1; c[x["rating"]] += 1
            if not x["excl"]: c[4] += 1; c[5 + CATS.index(x["cat"])] += 1
    for r in o.get("rating_distribution") or []:
        mm, d = str(r["month"])[:7], str(r["district_id"])
        for k in (d, "0"):
            RD.setdefault(mm, {}).setdefault(k, [0] * 5)[r["rating"] - 1] += r["orders"]

    # complaints on the last day before the run day that had any
    days = sorted({x["day"] for x in tickets if x["day"] < run_day.date().isoformat()})
    cday = None
    if days:
        dd = days[-1]
        items = [{"d": x["d"], "cat": x["cat"], "solved": x["solved"]} for x in tickets if x["day"] == dd]
        cday = {"date": dd, "is_yesterday": dd == (run_day.date() - datetime.timedelta(days=1)).isoformat(), "items": items}
    today_count = sum(1 for x in tickets if x["day"] == run_day.date().isoformat())
    unsolved = [x for x in tickets if x["day"][:7] >= FIRST_MONTH and not x["solved"]]

    data = {"generated": pulled.isoformat(timespec="minutes"), "timezone": "Africa/Cairo (UTC+2)",
            "first_month": FIRST_MONTH, "partial": partial, "districts": districts, "M": M, "last_day": last_day,
            "complaints_day": cday, "complaints_today_so_far": today_count,
            "unsolved": {"count": len(unsolved), "oldest": min((x["day"] for x in unsolved), default=None)},
            "CA": CA, "LA": LA, "RD": RD,
            "labels": {"manual": n_manual, "auto": n_auto}}
    check_no_pii(data)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, a.out)
    print(f"wrote {a.out}: {os.path.getsize(a.out)} bytes; last day {last_day['date']}; "
          f"labels manual={n_manual} auto={n_auto}; complaints day {cday and cday['date']}")

ALLOWED_TEXT = re.compile(r"^[\w\-:.+ ()/]*$")
def check_no_pii(data):
    """Fail loudly if anything that looks like free text, a phone number or an e-mail slipped in."""
    names = {s for d in data["districts"] for s in (d["en"], d["ar"])}
    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                if re.search(r"text|comment|consumer|phone|mobile|email|name", k, re.I): raise SystemExit(f"PII-like key {path}/{k}")
                walk(x, path + "/" + str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v): walk(x, path)
        elif isinstance(v, str):
            if v in names: return
            if re.search(r"\d{7,}|@", v) or len(v) > 40 or not ALLOWED_TEXT.match(v):
                raise SystemExit(f"unexpected string at {path}: {v[:30]!r}")
    walk({k: x for k, x in data.items() if k != "districts"}, "")
    for d in data["districts"]:
        if set(d) != {"id", "en", "ar"}: raise SystemExit("district fields")

if __name__ == "__main__":
    main()
