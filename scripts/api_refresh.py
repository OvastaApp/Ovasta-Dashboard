#!/usr/bin/env python3
"""Ovasta dashboard refresh via the read-only Metrics API (API_SPEC.md, v1).

Drop-in alternative to dashboard_refresh.py: never touches the database. It calls the HTTPS API and
writes dashboard_dump.json in the same shape that build_data.py already reads.

  OVASTA_API_BASE  (or OVASTA_API_URL)  base URL incl. version, e.g. https://metrics.example.com/v1
  OVASTA_API_KEY   API key (sent only as "Authorization: Bearer ..."; never printed or logged)
  python api_refresh.py [--out dashboard_dump.json]

Safety / hygiene
  * HTTPS only by default. Plain http is refused unless OVASTA_API_ALLOW_HTTP=1 (or localhost with OVASTA_API_ALLOW_HTTP_LOCAL=1 for tests). /v1 is appended if missing.
  * GET only, ~8 requests per run, short pause between them; retries 429/5xx with backoff (Retry-After)
  * Allow-list of fields per endpoint: anything else the API returns (e.g. a stray consumer_id) is dropped
  * free text is masked again here (7+ digit runs incl. Arabic digits, also split by spaces/dashes; e-mails)
  * numeric strings (PHP/PDO style) are converted to numbers
  * if any required step fails: exit code 1 and the previous dashboard_dump.json is left untouched
    (the failed pull goes to dashboard_dump.failed.json for inspection)
Only the Python standard library is used.
"""
import argparse, datetime, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
FIRST_MONTH = "2026-02"          # dashboard starts here
BASELINE_MONTH = "2026-01"       # month-over-month baseline only
TICKETS_SINCE = "2026-01-01"
LOW_RATINGS_SINCE = FIRST_MONTH + "-01"
PAGE = 500
PAUSE = 0.2
TIMEOUT = 30
RETRIES = 4
UA = "ovasta-dashboard-api-refresh/1"

D_ = "[0-9\u0660-\u0669\u06F0-\u06F9]"
PHONE_SPLIT = re.compile(D_ + r"(?:[\s\-\.]?" + D_ + "){6,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
def mask(text):
    if not text: return text
    return EMAIL.sub("[email]", PHONE_SPLIT.sub("[رقم]", text))

# ---- allow-lists (field -> type); unknown fields are dropped ----
INT, NUM, STR, BOOL, TS, ANY = "int", "num", "str", "bool", "ts", "any"
F_DISTRICT = {"id": INT, "en_name": STR, "ar_name": STR, "is_active": BOOL, "permanently_closed": BOOL}
F_STATUS = {"id": INT, "en_name": STR, "ar_name": STR}
F_PERIOD = {"district_id": INT, "is_total": INT, "placed": INT, "delivered": INT, "cancelled": INT, "open": INT,
            "gmv": NUM, "nmv": NUM, "open_value": NUM, "delivery_fees": NUM, "ordering_customers": INT,
            "active_customers": INT, "delivered_normal": INT, "delivered_anything": INT}
F_HOUR = {"hour": INT, "placed": INT, "delivered": INT, "nmv": NUM, "gmv": NUM}
F_TICKET = {"id": INT, "created_at": TS, "district_id": INT, "is_solved": BOOL, "sales_order_id": INT, "text": STR}
F_LOW = {"sales_order_id": INT, "rating": INT, "rating_comment": STR, "rated_at": TS, "created_at": TS, "district_id": INT}
F_RDIST = {"month": STR, "district_id": INT, "rating": INT, "orders": INT}
REQ_PERIOD = ("placed", "delivered", "cancelled", "open", "gmv", "nmv", "delivery_fees", "active_customers",
              "delivered_normal", "delivered_anything")

class ApiError(Exception):
    pass

def conv(v, t, field):
    if v is None: return None
    if t == INT:
        if isinstance(v, bool): return int(v)
        if isinstance(v, int): return v
        if isinstance(v, float) and v.is_integer(): return int(v)
        if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()): return int(v)
        raise ApiError(f"{field}: expected integer, got {v!r:.30}")
    if t == NUM:
        if isinstance(v, (int, float)) and not isinstance(v, bool): return v
        if isinstance(v, str):
            try: return float(v)
            except ValueError: pass
        raise ApiError(f"{field}: expected number, got {v!r:.30}")
    if t == BOOL:
        if isinstance(v, bool): return v
        if v in (0, 1, "0", "1", "t", "f", "true", "false"): return v in (1, "1", "t", "true")
        raise ApiError(f"{field}: expected boolean, got {v!r:.30}")
    if t == TS:
        s = str(v).replace(" ", "T")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?", s):
            raise ApiError(f"{field}: expected Cairo local timestamp YYYY-MM-DDTHH:MM:SS, got {v!r:.30}")
        return s
    if t == STR: return str(v)
    return v

def clean(row, fields, where, required=()):
    if not isinstance(row, dict): raise ApiError(f"{where}: expected object")
    for k in required:
        if k not in row: raise ApiError(f"{where}: missing field {k}")
    return {k: conv(row.get(k), t, f"{where}.{k}") for k, t in fields.items() if k in row}

class Client:
    def __init__(self, base, key):
        u = urllib.parse.urlparse(base)
        local = u.hostname in ("localhost", "127.0.0.1", "::1")
        allow_http = os.environ.get("OVASTA_API_ALLOW_HTTP") == "1"
        allow_local = os.environ.get("OVASTA_API_ALLOW_HTTP_LOCAL") == "1"
        if u.scheme != "https" and not (u.scheme == "http" and (allow_http or (local and allow_local))):
            raise SystemExit("OVASTA_API_URL must be https:// (the key must never travel over plain http). "
                             "For a temporary http endpoint, set OVASTA_API_ALLOW_HTTP=1.")
        if u.scheme == "http" and not local:
            log("WARNING: plain http; the API key travels unencrypted. Put HTTPS in front and rotate the key.")
        base = base.rstrip("/")
        if not urllib.parse.urlparse(base).path.rstrip("/").endswith("/v1"):
            base = base + "/v1"
            log("NOTE: appended /v1 to OVASTA_API_URL")
        self.base = base; self.key = key; self.n = 0

    def get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": "Bearer " + self.key, "Accept": "application/json", "User-Agent": UA})
        delay = 2.0
        for attempt in range(RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    body = r.read(); self.n += 1
                    time.sleep(PAUSE)
                    try: return json.loads(body.decode("utf-8"))
                    except ValueError: raise ApiError(f"GET {path}: response is not JSON")
            except urllib.error.HTTPError as e:
                self.n += 1
                try: err = json.loads(e.read().decode("utf-8")).get("error", {})
                except Exception: err = {}
                msg = f"GET {path}: HTTP {e.code} {err.get('code', '')} {err.get('message', '')}".strip()
                if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                    ra = e.headers.get("Retry-After")
                    wait = min(float(ra), 120) if ra and ra.replace(".", "", 1).isdigit() else delay
                    log(f"{msg}; retrying in {wait:.0f}s"); time.sleep(wait); delay *= 2; continue
                raise ApiError(msg)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.n += 1
                if attempt < RETRIES:
                    log(f"GET {path}: {getattr(e, 'reason', e)}; retrying in {delay:.0f}s"); time.sleep(delay); delay *= 2; continue
                raise ApiError(f"GET {path}: {getattr(e, 'reason', e)}")

    def pages(self, path, id_field, **params):
        out, after, seen = [], 0, 0
        while True:
            r = self.get(path, after_id=after, limit=PAGE, **params)
            items = r.get("items")
            if not isinstance(items, list): raise ApiError(f"{path}: items missing")
            out.extend(items)
            nxt = r.get("next_after_id")
            if nxt is None: return out
            nxt = int(nxt)
            if nxt <= after or not items: raise ApiError(f"{path}: pagination did not advance")
            after = nxt; seen += 1
            if seen > 1000: raise ApiError(f"{path}: too many pages")

T0 = time.time()
def log(msg): print(f"[{time.time() - T0:5.1f}s] {msg}", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "dashboard_dump.json"))
    a = ap.parse_args()
    base = os.environ.get("OVASTA_API_BASE") or os.environ.get("OVASTA_API_URL") or ""
    key = os.environ.get("OVASTA_API_KEY") or ""
    if not base or not key:
        raise SystemExit("Set OVASTA_API_BASE (or OVASTA_API_URL) and OVASTA_API_KEY first.")
    c = Client(base, key)

    out = {"generated_local": datetime.datetime.now().isoformat(), "source": "api", "errors": {}}
    def step(name, fn):
        try: return fn()
        except (ApiError, KeyError, TypeError, ValueError) as e:
            out["errors"][name] = str(e); log(f"ERROR in {name}: {e}"); return None

    # ---- meta ----
    def meta():
        m = c.get("/meta")
        for k in ("cairo_now", "cairo_today", "districts", "statuses"):
            if k not in m: raise ApiError(f"/meta: missing {k}")
        out["session"] = {"cairo_now": conv(m["cairo_now"], TS, "cairo_now"), "cairo_today": str(m["cairo_today"])[:10],
                          "db_now": m.get("generated_at_utc"), "ro": "on" if m.get("read_only") else "unknown",
                          "api_version": m.get("api_version")}
        out["districts"] = [clean(d, F_DISTRICT, "districts", ("id", "en_name", "ar_name")) for d in m["districts"]]
        out["statuses"] = [clean(s, F_STATUS, "statuses", ("id",)) for s in m["statuses"]]
        defs = m.get("definitions") or {}
        out["definitions"] = {k: str(v) for k, v in defs.items()} if isinstance(defs, dict) else {}
        out["definitions"]["source"] = "Ovasta Metrics API v1 (" + urllib.parse.urlparse(base).hostname + ")"
        return True
    if not step("meta", meta):
        return finish(a.out, out, c, fatal=True)
    log(f"meta ok; API clock Cairo {out['session']['cairo_now']}")

    # ---- monthly ----
    def monthly():
        r = c.get("/metrics/monthly", **{"from": BASELINE_MONTH})
        months = []
        for m in r["months"]:
            mon = str(m["month"])[:7]
            if not re.fullmatch(r"\d{4}-\d{2}", mon): raise ApiError(f"monthly: bad month {mon!r}")
            rows = [clean(x, F_PERIOD, f"monthly[{mon}]", REQ_PERIOD + ("is_total",)) for x in (m.get("by_district") or [])]
            part = bool(m.get("partial"))
            months.append({"month": mon, "baseline_only": mon < FIRST_MONTH, "partial": part,
                           "through": conv(m.get("through"), TS, "through") if part else None, "by_district": rows})
        if not any(x["month"] >= FIRST_MONTH for x in months): raise ApiError("monthly: no months returned")
        return sorted(months, key=lambda x: x["month"])
    out["months"] = step("md_monthly", monthly) or []
    log(f"monthly ok ({len(out['months'])} months)")

    # ---- last working day ----
    def lwd():
        r = c.get("/metrics/last-working-day", before=out["session"]["cairo_today"])
        d = r.get("date")
        return {"date": str(d)[:10] if d else None, "is_yesterday": bool(r.get("is_yesterday")),
                "days_back": conv(r.get("days_back"), INT, "days_back"),
                "pulled_at_cairo": out["session"]["cairo_now"], "pulled_at_db": out["session"]["db_now"],
                "by_district": [clean(x, F_PERIOD, "last_day", REQ_PERIOD[:6] + ("is_total", "open_value")) for x in (r.get("by_district") or [])],
                "by_hour": [clean(x, F_HOUR, "last_day.by_hour", ("hour", "placed", "delivered")) for x in (r.get("by_hour") or [])]}
    ld = step("last_day", lwd)
    if ld is not None: out["last_day"] = ld
    log(f"last working day ok ({ld and ld['date']})")

    # ---- complaints ----
    def tickets():
        rows = [clean(x, F_TICKET, "complaints", ("id", "created_at", "district_id", "is_solved")) for x in c.pages("/complaints", "id", since=TICKETS_SINCE)]
        for t in rows: t["text"] = mask(t.get("text"))
        return rows
    t = step("tickets", tickets)
    out["tickets"] = t if t is not None else []
    log(f"complaints ok ({len(out['tickets'])})")

    # ---- ratings ----
    def low():
        rows = [clean(x, F_LOW, "ratings/low", ("sales_order_id", "rating", "created_at", "district_id"))
                for x in c.pages("/ratings/low", "sales_order_id", since=LOW_RATINGS_SINCE)]
        for r in rows: r["rating_comment"] = mask(r.get("rating_comment"))
        return rows
    lr = step("low_ratings", low)
    out["low_ratings"] = lr if lr is not None else []
    def rdist():
        r = c.get("/ratings/distribution", **{"from": FIRST_MONTH})
        return [clean(x, F_RDIST, "ratings/distribution", tuple(F_RDIST)) for x in r["rows"]]
    out["rating_distribution"] = step("rating_dist", rdist)
    log(f"ratings ok ({len(out['low_ratings'])} low)")
    return finish(a.out, out, c)

def finish(path, out, c, fatal=False):
    out["queries_run"] = c.n; out["elapsed_s"] = round(time.time() - T0, 1)
    bad = bool(out["errors"]) or fatal
    target = path.replace(".json", ".failed.json") if bad else path
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(out, f, indent=1, ensure_ascii=False)
    os.replace(tmp, target)
    if bad:
        log(f"FAILED ({list(out['errors'])}); wrote {target}; {path} left unchanged"); sys.exit(1)
    log(f"done: {c.n} API requests -> {target}")

if __name__ == "__main__":
    main()
