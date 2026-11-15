/* Ovasta startup metrics: static dashboard. Reads ../data.json (built by build_data.py). No dependencies. */
(function () {
  "use strict";
  var CATS = ["Delay / late delivery", "Courier behavior", "Product quality", "Missing / wrong items", "Pricing / billing", "App / ordering / account", "Other / unclear"];
  var CATKEY = ["delay", "courier", "quality", "missing_wrong", "pricing", "app", "other"];
  var EXAMPLES = [
    ["Delay / late delivery", "Order took 1.5 to 2+ hours · asked where the order was after an hour and nobody called · late every time, even for a small order"],
    ["Courier behavior", "Courier rude or loud with the customer · refused to bring the order up to the second floor · promised 5 minutes, then stopped answering"],
    ["Product quality", "Fruit or vegetables spoiled or not fresh · food arrived cold, burnt or soggy · expired yogurt or milk"],
    ["Missing / wrong items", "Paid for items that never came (bread, eggs, honey) · different brand, size or flavour sent without asking · food from a different restaurant than ordered"],
    ["Pricing / billing", "Delivery fee raised after the order was accepted · courier asked for more than the in-app invoice · change owed not added to the wallet · asking to pay by Vodafone Cash, InstaPay or card"],
    ["App / ordering / account", "Can't register, activate the account or change the phone number · told the area is not covered or service paused · asking support to cancel or edit an order · app freezes or won't place the order"],
    ["Other / unclear", "Please call me with no issue stated · very bad service with no detail · praise for a courier · shops asking to list their products"]
  ];
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"];

  var D, MONTHS, state = { month: null, dist: "0", trend: "orders", scope: "month" };

  // ---------- formatting ----------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function n0(v) { return Math.round(v || 0).toLocaleString("en-US"); }
  function egp(v) { return "EGP " + n0(v); }
  function egpK(v) { return v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1000 ? Math.round(v / 1000) + "k" : String(Math.round(v)); }
  function pct(a, b) { return b > 0 ? (100 * a / b).toFixed(1) + "%" : "–"; }
  function sp(v) { return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%"; }
  function growth(a, b) { return b > 0 ? sp(100 * (a - b) / b) : "–"; }
  function ym(m) { var p = m.split("-"); return { y: +p[0], m: +p[1] }; }
  function daysIn(m) { var t = ym(m); return new Date(Date.UTC(t.y, t.m, 0)).getUTCDate(); }
  function prevKey(m) { var t = ym(m); var d = new Date(Date.UTC(t.y, t.m - 2, 1)); return d.getUTCFullYear() + "-" + String(d.getUTCMonth() + 1).padStart(2, "0"); }
  function isPartial(m) { return !!(D.partial && D.partial.month === m); }
  function throughDay() { return D.partial ? +D.partial.through.slice(8, 10) : null; }
  function mlabel(m) { var t = ym(m); var s = MON[t.m - 1] + " " + t.y; return isPartial(m) ? s + " (to " + throughDay() + " " + MON[t.m - 1] + ")" : s; }
  function mshort(m) { var t = ym(m); return MON[t.m - 1] + " " + String(t.y).slice(2) + (isPartial(m) ? "*" : ""); }
  function dlabel(iso, withWd) { var p = iso.split("-"); var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); return (withWd ? WD[d.getUTCDay()] + " " : "") + (+p[2]) + " " + MON[+p[1] - 1] + " " + p[0]; }
  function dname(d) { if (d === "0") return "All districts"; var x = D.districts.filter(function (z) { return z.id === d; })[0]; return x ? x.en : "District " + d; }
  function dnameHtml(d) { if (d === "0") return "All districts"; var x = D.districts.filter(function (z) { return z.id === d; })[0]; return x ? esc(x.en) + ' · <bdi dir="rtl" lang="ar" class="ar">' + esc(x.ar) + "</bdi>" : "District " + esc(d); }
  function row(m, d) { return D.M[m] && D.M[m][d]; }
  function scopeLabel() { return state.scope === "all" ? mshort(MONTHS[0]).replace("*", "") + " – " + mshort(MONTHS[MONTHS.length - 1]).replace("*", "") : mlabel(state.month); }

  // ---------- small components ----------
  function table(cols, rows, opts) {
    opts = opts || {};
    var h = '<div class="tw"><table><thead><tr>' + cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (r, i) {
      var cls = opts.totalLast && i === rows.length - 1 ? ' class="total"' : "";
      h += "<tr" + cls + ">" + r.map(function (c, j) { return "<td" + (opts.wrapCol === j ? ' class="wrap"' : "") + ">" + (c && c.html != null ? c.html : esc(c)) + "</td>"; }).join("") + "</tr>";
    });
    return h + "</tbody></table></div>";
  }
  function H(html) { return { html: html }; }
  function kpis(list) {
    return '<div class="kpis">' + list.map(function (k) {
      return '<div class="kpi"><div class="v">' + esc(k.value) + '</div><div class="l">' + esc(k.label) + "</div>" +
        (k.detail ? '<div class="d ' + (k.tone || "") + '">' + esc(k.detail) + "</div>" : "") + "</div>";
    }).join("") + "</div>";
  }
  function bars(list) {
    var max = Math.max.apply(null, list.map(function (b) { return b.value; }).concat([1]));
    return '<div class="bars">' + list.map(function (b) {
      return '<div class="bar"><div class="t"><span>' + (b.labelHtml || esc(b.label)) + '</span><span>' + esc(b.display) +
        (b.meta ? '<span class="m">' + esc(b.meta) + "</span>" : "") + '</span></div><div class="track"><div class="fill" style="width:' +
        (100 * b.value / max).toFixed(1) + '%"></div></div></div>';
    }).join("") + "</div>";
  }
  function seg(name, options, value) {
    return '<div class="seg" data-seg="' + name + '">' + options.map(function (o) {
      return '<button type="button" data-v="' + o[0] + '" class="' + (o[0] === value ? "on" : "") + '" aria-pressed="' + (o[0] === value) + '">' + esc(o[1]) + "</button>";
    }).join("") + "</div>";
  }
  function legend(series) {
    return '<div class="legend">' + series.map(function (s, i) { return '<span><i style="background:' + COLORS[i % 5] + '"></i>' + esc(s.name) + "</span>"; }).join("") + "</div>";
  }
  function niceMax(v) { if (v <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log10(v))); var f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
  function frame(W, Hh, L, B, max, fmt) {
    var g = "";
    for (var i = 0; i <= 4; i++) {
      var y = Hh - B - (Hh - B - 10) * i / 4;
      g += '<line x1="' + L + '" x2="' + W + '" y1="' + y + '" y2="' + y + '" stroke="#ecebe9"/><text x="' + (L - 6) + '" y="' + (y + 4) + '" text-anchor="end">' + esc(fmt(max * i / 4)) + "</text>";
    }
    return g;
  }
  function columns(labels, series, stacked, fmt) {
    var W = 720, Hh = 250, L = 46, B = 26, n = labels.length;
    var tot = labels.map(function (_, i) { return stacked ? series.reduce(function (s, x) { return s + (x.values[i] || 0); }, 0) : Math.max.apply(null, series.map(function (x) { return x.values[i] || 0; })); });
    var max = niceMax(Math.max.apply(null, tot.concat([0])));
    var bw = (W - L) / n, inner = Math.max(4, bw * 0.62), plotH = Hh - B - 10;
    var g = frame(W, Hh, L, B, max, fmt);
    labels.forEach(function (lab, i) {
      var x0 = L + i * bw + (bw - inner) / 2, base = Hh - B;
      series.forEach(function (s, k) {
        var v = s.values[i] || 0, h = plotH * v / max;
        var w = stacked ? inner : inner / series.length, x = stacked ? x0 : x0 + k * w;
        var y = stacked ? base - h : Hh - B - h;
        if (h > 0) g += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + Math.max(1, w - (stacked ? 0 : 1)).toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + COLORS[k % 5] + '" rx="2"><title>' + esc(lab + " · " + s.name + ": " + fmt(v)) + "</title></rect>";
        if (stacked) base -= h;
      });
      if (lab) g += '<text x="' + (L + i * bw + bw / 2).toFixed(1) + '" y="' + (Hh - 8) + '" text-anchor="middle">' + esc(lab) + "</text>";
      if (n <= 12 && tot[i] > 0) g += '<text x="' + (L + i * bw + bw / 2).toFixed(1) + '" y="' + (Hh - B - plotH * tot[i] / max - 4).toFixed(1) + '" text-anchor="middle" style="fill:var(--ink)">' + esc(fmt(tot[i])) + "</text>";
    });
    return '<div class="chart" role="img" aria-label="Column chart">' + (series.length > 1 ? legend(series) : "") + '<svg viewBox="0 0 ' + W + " " + Hh + '">' + g + "</svg></div>";
  }
  function lines(labels, series, fmt) {
    var W = 720, Hh = 250, L = 52, B = 26, n = labels.length;
    var max = niceMax(Math.max.apply(null, series.map(function (s) { return Math.max.apply(null, s.values.concat([0])); })) * 1.05);
    var plotH = Hh - B - 10, step = n > 1 ? (W - L - 20) / (n - 1) : 0;
    var g = frame(W, Hh, L, B, max, fmt);
    series.forEach(function (s, k) {
      var pts = s.values.map(function (v, i) { return [L + 10 + i * step, Hh - B - plotH * (v || 0) / max]; });
      g += '<polyline fill="none" stroke="' + COLORS[k % 5] + '" stroke-width="2.5" points="' + pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ") + '"/>';
      pts.forEach(function (p, i) { g += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="3.5" fill="' + COLORS[k % 5] + '"><title>' + esc(labels[i] + " · " + s.name + ": " + fmt(s.values[i])) + "</title></circle>"; });
    });
    labels.forEach(function (lab, i) { g += '<text x="' + (L + 10 + i * step).toFixed(1) + '" y="' + (Hh - 8) + '" text-anchor="middle">' + esc(lab) + "</text>"; });
    return '<div class="chart" role="img" aria-label="Line chart">' + legend(series) + '<svg viewBox="0 0 ' + W + " " + Hh + '">' + g + "</svg></div>";
  }
  function head(title, cap, actions) {
    return '<div class="head"><div><h2>' + title + "</h2>" + (cap ? '<p class="cap">' + cap + "</p>" : "") + "</div>" + (actions || "") + "</div>";
  }
  function callout(t) { return '<div class="callout">' + esc(t) + "</div>"; }

  // ---------- sections ----------
  function renderLastDay() {
    var L = D.last_day, el = document.getElementById("lastday");
    if (!L || !L.date) { el.innerHTML = head("Last working day") + callout("No orders found in the recent days."); return; }
    var t = L.by_district["0"] || [0, 0, 0, 0, 0, 0, 0];
    var title, cap;
    if (L.partial) { title = "Today so far: " + esc(dlabel(L.date, true)); cap = "All districts, up to " + esc(L.until) + " Cairo time. Not affected by the filters."; }
    else {
      title = "Last working day: " + esc(dlabel(L.date, true));
      cap = (L.is_yesterday ? "Yesterday, full day" : "Yesterday had no orders, so this is the most recent day with orders (" + L.days_back + " days ago)") + ", all districts, Cairo time. Not affected by the filters.";
    }
    var h = head(title, cap);
    h += kpis([{ value: n0(t[0]), label: "Orders placed" }, { value: n0(t[1]), label: "Delivered" }, { value: n0(t[2]), label: "Cancelled" },
      { value: n0(t[3]), label: "Still open" }, { value: egp(t[4]), label: "NMV (delivered orders)" }, { value: egp(t[5]), label: "GMV (all placed orders)" }]);
    var hrs = L.by_hour, lastH = 23; if (L.partial) { lastH = 0; hrs.forEach(function (x, i) { if (x[0]) lastH = i; }); }
    hrs = hrs.slice(0, lastH + 1);
    h += "<h3>Orders by hour placed</h3>" + columns(hrs.map(function (_, i) { return i % 3 === 0 ? String(i).padStart(2, "0") + ":00" : ""; }),
      [{ name: "Delivered", values: hrs.map(function (x) { return x[1]; }) }, { name: "Not delivered", values: hrs.map(function (x) { return x[0] - x[1]; }) }], true, n0);
    var ids = D.districts.map(function (d) { return d.id; }).filter(function (d) { return L.by_district[d]; });
    h += table(["District", "Placed", "Delivered", "Cancelled", "Open", "NMV", "GMV"], ids.concat(["0"]).map(function (d) {
      var r = L.by_district[d] || [0, 0, 0, 0, 0, 0, 0]; return [H(dnameHtml(d)), n0(r[0]), n0(r[1]), n0(r[2]), n0(r[3]), egp(r[4]), egp(r[5])];
    }), { totalLast: true });
    var none = D.districts.filter(function (d) { return !L.by_district[d.id]; }).map(function (d) { return d.en; });
    h += '<p class="note">' + (none.length ? "No orders in " + esc(none.join(", ")) + " that day. " : "") + "NMV can be slightly above GMV when a price adjustment is added to an order.</p>";
    var C = D.complaints_day;
    h += "<h3>Complaints</h3>";
    if (!C) h += '<p class="note">No complaints recorded yet.</p>';
    else {
      var by = {}; C.items.forEach(function (x) { (by[x.d] = by[x.d] || []).push(CATS[CATKEY.indexOf(x.cat)] || "Other"); });
      var open = C.items.filter(function (x) { return !x.solved; }).length;
      var parts = Object.keys(by).map(function (d) { return "<b>" + esc(dname(d)) + "</b>: " + esc(by[d].join(", ")); });
      var when = C.date === L.date ? "That day" : (C.is_yesterday ? "Yesterday" : "Most recent day with complaints") + ", " + esc(dlabel(C.date, true));
      h += "<p>" + when + ": " + C.items.length + " complaint" + (C.items.length === 1 ? "" : "s") + " (" + parts.join("; ") + "). " +
        (open ? open + " still open." : "All solved.") + "</p>";
      if (C.date !== L.date && !L.partial) h += '<p class="note">No complaints were filed on ' + esc(dlabel(L.date)) + ".</p>";
    }
    if (D.complaints_today_so_far) h += '<p class="note">' + D.complaints_today_so_far + " more filed today so far.</p>";
    el.innerHTML = h;
  }

  function renderKpis() {
    var m = state.month, d = state.dist, cur = row(m, d), el = document.getElementById("kpis");
    var h = head("Key metrics: " + esc(mlabel(m)) + ", " + dnameHtml(d));
    if (!cur) { el.innerHTML = h + callout("This district had no orders in " + mlabel(m) + ". Pick another month or district."); return; }
    var pm = prevKey(m), prev = row(pm, d), part = isPartial(m), pshort = MON[ym(pm).m - 1];
    function arrow(g, goodUp, tail, unit) {
      var flat = Math.abs(g) < 0.05;
      return { detail: (flat ? "■ " : g > 0 ? "▲ " : "▼ ") + Math.abs(g).toFixed(1) + unit + tail, tone: flat ? "" : ((g > 0) === goodUp ? "good" : "bad") };
    }
    function kd(i, goodUp) {
      if (!prev || !(prev[i] > 0)) return { detail: "No prior month" };
      if (part) { var a = cur[i] / D.partial.days, b = prev[i] / daysIn(pm); return arrow(100 * (a - b) / b, goodUp !== false, " daily pace vs " + pshort, "%"); }
      return arrow(100 * (cur[i] - prev[i]) / prev[i], goodUp !== false, " vs " + pshort, "%");
    }
    function ext(o, x) { o.detail = x.detail; o.tone = x.tone; return o; }
    var cr = function (r) { return r && r[0] ? 100 * r[2] / r[0] : 0; }, aov = function (r) { return r && r[1] ? r[5] / r[1] : 0; };
    var tail = " vs " + pshort;
    h += '<p class="cap">' + (part ? esc(mlabel(m).split(" (")[0]) + " is in progress (to " + throughDay() + " " + MON[ym(m).m - 1] + "). Changes compare the daily pace with " + esc(mlabel(pm)) + ". " + n0(cur[3]) + " orders are still open."
      : "Changes compare with " + esc(mlabel(pm)) + ". Green is better, amber is worse.") + "</p>";
    h += kpis([
      ext({ value: n0(cur[0]), label: "Orders placed" }, kd(0)),
      part ? { value: n0(cur[1]), label: "Orders delivered", detail: n0(cur[3]) + " still open" } : ext({ value: n0(cur[1]), label: "Orders delivered" }, kd(1)),
      ext({ value: cr(cur).toFixed(1) + "%", label: "Cancellation rate (" + n0(cur[2]) + " cancelled)" }, prev && prev[0] ? arrow(cr(cur) - cr(prev), false, tail, " pts") : { detail: "No prior month" }),
      ext({ value: egp(cur[4]), label: "GMV" }, kd(4)),
      part ? { value: egp(cur[5]), label: "NMV", detail: "Open orders not yet counted" } : ext({ value: egp(cur[5]), label: "NMV" }, kd(5)),
      ext({ value: cur[1] ? egp(aov(cur)) : "–", label: "Average order value" }, prev && prev[1] && cur[1] ? arrow(100 * (aov(cur) - aov(prev)) / aov(prev), true, tail, "%") : { detail: "No prior month" }),
      part ? { value: egp(cur[6]), label: "Delivery fees", detail: "Delivered orders only" } : ext({ value: egp(cur[6]), label: "Delivery fees" }, kd(6)),
      part ? { value: n0(cur[7]), label: "Active customers", detail: "So far this month" } : ext({ value: n0(cur[7]), label: "Active customers" }, kd(7))
    ]);
    el.innerHTML = h;
  }

  function series() { return MONTHS.map(function (m) { return { m: m, r: row(m, state.dist) || [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] }; }); }
  function renderTrend() {
    var s = series(), labels = s.map(function (x) { return mshort(x.m); }), t = state.trend, el = document.getElementById("trend");
    var cap = esc(mshort(MONTHS[0])) + " to " + esc(mshort(MONTHS[MONTHS.length - 1]).replace("*", "")) + (D.partial ? ". " + esc(mshort(D.partial.month)) + " is in progress." : ".");
    var h = head("Monthly trend: " + dnameHtml(state.dist), cap, seg("trend", [["orders", "Orders"], ["value", "GMV & NMV"], ["customers", "Active customers"], ["mix", "Order type"]], t));
    if (t === "orders") h += columns(labels, [{ name: "Delivered", values: s.map(function (x) { return x.r[1]; }) }, { name: "Cancelled", values: s.map(function (x) { return x.r[2]; }) }, { name: "Open", values: s.map(function (x) { return x.r[3]; }) }], true, n0);
    if (t === "value") h += lines(labels, [{ name: "GMV", values: s.map(function (x) { return x.r[4]; }) }, { name: "NMV", values: s.map(function (x) { return x.r[5]; }) }], egpK);
    if (t === "customers") h += columns(labels, [{ name: "Active customers", values: s.map(function (x) { return x.r[7]; }) }], false, n0);
    if (t === "mix") h += columns(labels, [{ name: "Normal (catalog)", values: s.map(function (x) { return x.r[8]; }) }, { name: "Any Thing (errand)", values: s.map(function (x) { return x.r[9]; }) }], true, n0);
    el.innerHTML = h;
  }

  function renderDistricts() {
    var m = state.month, el = document.getElementById("districts"), tot = row(m, "0"), pm = prevKey(m), part = isPartial(m);
    var ids = D.districts.map(function (d) { return d.id; }).filter(function (d) { return row(m, d); });
    var h = head("District comparison: " + esc(mlabel(m)), "Uses the month filter only.");
    if (!ids.length) { el.innerHTML = h + callout("No orders in " + mlabel(m) + "."); return; }
    function mk(i, disp, what) {
      return ids.map(function (d) { var r = row(m, d); return { labelHtml: dnameHtml(d), value: r[i], display: disp(r[i]), meta: tot && tot[i] ? pct(r[i], tot[i]) + " of " + what : "" }; }).sort(function (a, b) { return b.value - a.value; });
    }
    h += '<div class="grid2"><div><h3>NMV</h3>' + bars(mk(5, egp, "NMV")) + "</div><div><h3>Orders placed</h3>" + bars(mk(0, function (v) { return n0(v) + " orders"; }, "orders")) + "</div></div>";
    h += table(["District", "Placed", "Delivered", "Cancel %", "GMV", "NMV", "AOV", "Delivery fees", "Active cust.", "Errand %", "NMV MoM"], ids.concat(["0"]).map(function (d) {
      var r = row(m, d) || [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], p = row(pm, d);
      return [H(dnameHtml(d)), n0(r[0]), n0(r[1]), pct(r[2], r[0]), egp(r[4]), egp(r[5]), r[1] ? egp(r[5] / r[1]) : "–", egp(r[6]), n0(r[7]), pct(r[9], r[1]), part ? "In progress" : p ? growth(r[5], p[5]) : "–"];
    }), { totalLast: true });
    h += '<p class="note">Errand % is the share of delivered orders placed as "Any Thing" errands. A customer who ordered in two districts counts in both rows, so district rows can add up to more than the total.</p>';
    el.innerHTML = h;
  }

  function scopeMonths() { return state.scope === "all" ? MONTHS : [state.month]; }
  function sumArr(src, len) {
    var a = []; for (var i = 0; i < len; i++) a.push(0);
    scopeMonths().forEach(function (m) { ((src[m] || {})[state.dist] || []).forEach(function (v, i) { a[i] += v; }); });
    return a;
  }
  function renderComplaints() {
    var el = document.getElementById("complaints"), d = state.dist, ca = sumArr(D.CA, 11);
    var delivered = scopeMonths().reduce(function (s, m) { return s + ((row(m, d) || [])[1] || 0); }, 0);
    var h = head("Complaints: " + esc(scopeLabel()) + ", " + dnameHtml(d), "", seg("scope", [["month", "Selected month"], ["all", "All months"]], state.scope));
    if (ca[0] > 0) {
      h += '<div class="grid2"><div><h3>By type</h3>' + bars(CATS.map(function (c, i) { return { label: c, value: ca[3 + i], display: pct(ca[3 + i], ca[1]), meta: n0(ca[3 + i]) + " tickets" }; }).sort(function (a, b) { return b.value - a.value; })) + "</div><div>" +
        table(["Measure", "Value"], [["Tickets", n0(ca[0])], ["Counted in type shares", n0(ca[1])], ["Solved", n0(ca[2]) + " · " + pct(ca[2], ca[0])], ["Unsolved", n0(ca[0] - ca[2])],
          ["Per 100 delivered orders", delivered > 0 ? (100 * ca[0] / delivered).toFixed(2) : "–"], ["From low ratings with a comment", n0(ca[10])]]) + "</div></div>";
    } else h += callout("No complaints were filed for this selection.");
    var cs = MONTHS.map(function (m) { return (D.CA[m] || {})[d] || [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]; });
    h += "<h3>Complaints by month: " + dnameHtml(d) + "</h3>";
    h += columns(MONTHS.map(mshort), [{ name: "Delay", values: cs.map(function (a) { return a[3]; }) }, { name: "Missing / wrong items", values: cs.map(function (a) { return a[6]; }) },
      { name: "Pricing / billing", values: cs.map(function (a) { return a[7]; }) }, { name: "All other types", values: cs.map(function (a) { return a[4] + a[5] + a[8] + a[9]; }) }], true, n0);
    h += table(["Month", "Tickets", "Per 100 deliv.", "Solved", "Delay", "Courier", "Quality", "Missing", "Pricing", "App", "Other"], MONTHS.map(function (m, i) {
      var a = cs[i], r = row(m, d), del = r ? r[1] : 0;
      return [mshort(m), n0(a[0]), del > 0 ? (100 * a[0] / del).toFixed(2) : "–", pct(a[2], a[0]), pct(a[3], a[1]), pct(a[4], a[1]), pct(a[5], a[1]), pct(a[6], a[1]), pct(a[7], a[1]), pct(a[8], a[1]), pct(a[9], a[1])];
    }));
    var u = D.unsolved;
    h += '<p class="note">Type shares leave out blank, test and duplicate tickets. Since late July 2026 every low rating with a comment also opens a ticket, which explains much of the jump in August.' +
      (u && u.count ? " " + u.count + " ticket" + (u.count === 1 ? " is" : "s are") + " still open (oldest from " + esc(dlabel(u.oldest)) + ")." : "") + "</p>";
    h += "<h3>Typical complaints by type</h3>" + table(["Type", "Typical complaints, reworded"], EXAMPLES, { wrapCol: 1 });
    h += '<p class="note">Older tickets were reviewed by hand; new ones are sorted by keyword rules, and anything unclear counts as Other. App / ordering also covers account, address and service-area requests and asks to cancel or edit an order. Pricing also covers questions about paying by wallet, Vodafone Cash, InstaPay or card.</p>';
    el.innerHTML = h;
  }

  function renderRatings() {
    var el = document.getElementById("ratings"), d = state.dist, la = sumArr(D.LA, 12), rd = sumArr(D.RD, 5);
    var rated = rd.reduce(function (s, v) { return s + v; }, 0), low = rd[0] + rd[1] + rd[2];
    var delivered = scopeMonths().reduce(function (s, m) { return s + ((row(m, d) || [])[1] || 0); }, 0);
    var h = head("Low ratings (3★ or below): " + esc(scopeLabel()) + ", " + dnameHtml(d), "Follows the complaints scope above.");
    if (rated > 0) {
      h += '<div class="grid2"><div><h3>All ratings</h3>' + bars([5, 4, 3, 2, 1].map(function (s) { return { label: s + "★", value: rd[s - 1], display: n0(rd[s - 1]), meta: pct(rd[s - 1], rated) }; })) +
        "</div><div><h3>Low-rating comments by type</h3>" + bars(CATS.map(function (c, i) { return { label: c, value: la[5 + i], display: pct(la[5 + i], la[4]), meta: n0(la[5 + i]) + " comments" }; }).sort(function (a, b) { return b.value - a.value; })) + "</div></div>";
      h += "<p>" + n0(low) + " of " + n0(rated) + " rated orders (" + pct(low, rated) + ") were rated 3★ or below. " + pct(rated, delivered) + " of delivered orders got a rating.</p>";
    } else h += callout("No rated orders for this selection.");
    h += table(["Month", "Rated orders", "Avg rating", "Rated ≤3", "Share ≤3", "1★", "2★", "3★"], MONTHS.map(function (m) {
      var x = (D.RD[m] || {})[d] || [0, 0, 0, 0, 0], n = x.reduce(function (s, v) { return s + v; }, 0), lo = x[0] + x[1] + x[2];
      return [mshort(m), n0(n), n > 0 ? (x.reduce(function (s, v, i) { return s + v * (i + 1); }, 0) / n).toFixed(2) : "–", n0(lo), pct(lo, n), n0(x[0]), n0(x[1]), n0(x[2])];
    }));
    h += '<p class="note">Ratings are optional and counted by the month the order was placed. Since late July low ratings with a comment also appear as tickets in the Complaints section, so do not add the two together.</p>';
    el.innerHTML = h;
  }

  function renderTable() {
    var el = document.getElementById("table"), d = state.dist, s = series(), wasOpen = el.querySelector("details") && el.querySelector("details").open;
    var rows = s.map(function (x, i) {
      var r = x.r, p = i > 0 ? s[i - 1].r : row(prevKey(x.m), d), part = isPartial(x.m);
      return [mlabel(x.m), n0(r[0]), n0(r[1]), n0(r[2]), pct(r[2], r[0]), egp(r[4]), egp(r[5]), r[1] ? egp(r[5] / r[1]) : "–", n0(r[7]),
        part ? "In progress" : p ? growth(r[0], p[0]) : "–", part ? "In progress" : p ? growth(r[5], p[5]) : "–"];
    });
    el.innerHTML = "<details" + (wasOpen ? " open" : "") + "><summary>Monthly table: " + dnameHtml(d) + "</summary>" +
      table(["Month", "Placed", "Delivered", "Cancelled", "Cancel %", "GMV", "NMV", "AOV", "Active cust.", "Orders MoM", "NMV MoM"], rows) + "</details>";
  }

  function renderAll() { renderKpis(); renderTrend(); renderDistricts(); renderComplaints(); renderRatings(); renderTable(); }

  function init(data) {
    D = data;
    MONTHS = Object.keys(D.M).filter(function (m) { return m >= D.first_month; }).sort();
    var full = MONTHS.filter(function (m) { return !isPartial(m); });
    state.month = full.length ? full[full.length - 1] : MONTHS[MONTHS.length - 1];
    var g = D.generated;
    var gd = new Date(g + ":00+02:00"), mins = Math.max(0, Math.round((Date.now() - gd.getTime()) / 60000));
    var ago = mins < 60 ? mins + " min ago" : mins < 1440 ? Math.round(mins / 60) + " h ago" : Math.round(mins / 1440) + " days ago";
    var wd = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][new Date(g.slice(0, 10) + "T12:00:00Z").getUTCDay()];
    var up = document.getElementById("updated");
    up.textContent = "Last updated: " + wd + " " + dlabel(g.slice(0, 10)) + ", " + g.slice(11, 16) + " Cairo time (" + ago + ")";
    if (mins > 36 * 60) { up.className = "updated stale"; up.textContent += " · daily update may have been missed"; }
    document.getElementById("asof").textContent = dlabel(MONTHS[0] + "-01").replace(/^1 /, "") + " onward. Amounts in EGP. Updates daily at 07:00 Cairo time.";
    var fm = document.getElementById("f-month"), fd = document.getElementById("f-dist");
    fm.innerHTML = MONTHS.slice().reverse().map(function (m) { return '<option value="' + m + '"' + (m === state.month ? " selected" : "") + ">" + esc(mlabel(m)) + "</option>"; }).join("");
    fd.innerHTML = '<option value="0">All districts</option>' + D.districts.map(function (d) { return '<option value="' + esc(d.id) + '">' + esc(d.en) + " · \u2068" + esc(d.ar) + "\u2069</option>"; }).join("");
    fm.addEventListener("change", function () { state.month = fm.value; renderAll(); });
    fd.addEventListener("change", function () { state.dist = fd.value; renderAll(); });
    document.getElementById("app").addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".seg button"); if (!b) return;
      var name = b.parentNode.getAttribute("data-seg"); state[name] = b.getAttribute("data-v");
      if (name === "trend") renderTrend(); else { renderComplaints(); renderRatings(); }
    });
    renderLastDay(); renderAll();
  }

  fetch("data.json", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(init).catch(function (e) {
    document.getElementById("asof").textContent = "Could not load data.json (" + e.message + "). Open the site through a web server, e.g. python -m http.server.";
  });
})();
