#!/usr/bin/env python3
"""
Daily mutual-fund report for Manulife GIF Select holdings.

- Reads holdings from holdings.csv
- Fetches live NAV + 1-day change from Manulife's public fund API
- Computes market value, today's change, and gain/loss vs cost (ACB)
- Appends one row per day to data/value_log.csv (quick history at a glance)
- Appends a per-day snapshot to data/snapshots.jsonl (dashboard history chart)
- Writes a simple report (report.txt, report.html) AND a full dashboard (dashboard.html)

No third-party dependencies (stdlib only).
"""
import csv, json, math, os, re, sys, urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
HOLDINGS = os.path.join(ROOT, "holdings.csv")
DATA_DIR = os.path.join(ROOT, "data")
SNAP = os.path.join(DATA_DIR, "snapshots.jsonl")
VALUE_LOG = os.path.join(DATA_DIR, "value_log.csv")
REPORT_TXT = os.path.join(ROOT, "report.txt")
REPORT_HTML = os.path.join(ROOT, "report.html")
DASH = os.path.join(ROOT, "dashboard.html")
API = "https://funds.manulife.ca/profiles/api/funds/list/en-US/?take=6000"

PALETTE = ["#4f8ef7", "#f7a44f", "#57c785", "#e8607a", "#a97cf0", "#3ec1d3",
           "#f2d24b", "#8d99ae", "#ef8354", "#6a994e", "#bc6c25", "#709775"]


def load_holdings():
    rows = []
    with open(HOLDINGS, newline="", encoding="utf-8") as f:
        lines = [l for l in f if not l.lstrip().startswith("#")]
    for r in csv.DictReader(lines):
        if not (r.get("code") or "").strip():
            continue
        r["units"] = float(r["units"])
        r["acb"] = float(r.get("acb") or 0)
        rows.append(r)
    return rows


def fetch_funds():
    print("Fetching Manulife fund prices ...")
    req = urllib.request.Request(API, headers={"Accept": "application/json",
                                               "User-Agent": "finance-report/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    by_code = {}
    for it in data["Items"]:
        for c in fund_codes(it):
            by_code.setdefault(c, it)
    return by_code


def fund_codes(it):
    """Collect every fund-serv code on an item (fields like fundServCodes are
    bracketed strings, e.g. '[MGF1916]')."""
    codes = set()
    for k, v in it.items():
        if k.startswith("fundServ") or k == "firstFundServCode":
            if isinstance(v, str) and v:
                for c in re.split(r"[,\[\]\s]+", v):
                    if c:
                        codes.add(c)
    return codes


def build(holdings, by_code):
    out, missing = [], []
    for h in holdings:
        it = by_code.get(h["code"])
        if not it:
            missing.append(h["code"]); continue
        nav = float(it["retNav"])
        d1amt = float(it.get("retD1Amt") or 0)
        value = h["units"] * nav
        cost = h["acb"]
        out.append({
            "account": h["account"], "fund": h["fund_name"], "code": h["code"],
            "nav": nav, "units": h["units"], "value": value,
            "day_pl": h["units"] * d1amt, "day_pct": float(it.get("retD1") or 0),
            "cost": cost, "gain": value - cost,
            "gain_pct": (value - cost) / cost * 100 if cost else 0.0,
            "asof": it.get("retEffectiveDate"),
        })
    return out, missing


def group(rows, key):
    g = {}
    for r in rows:
        g[r[key]] = g.get(r[key], 0) + r["value"]
    return sorted(g.items(), key=lambda kv: -kv[1])


def group_with_cost(rows, key):
    """Group by key, returning (name, value, cost) sorted by value desc."""
    g = {}
    for r in rows:
        a = g.setdefault(r[key], [0.0, 0.0])
        a[0] += r["value"]
        a[1] += r["cost"]
    return sorted(((k, v, c) for k, (v, c) in g.items()), key=lambda t: -t[1])


# ---------- SVG charts (no external libs) ----------
def donut(segments, size=260, thickness=52):
    total = sum(v for _, v, _ in segments) or 1
    cx = cy = size / 2
    ro = size / 2 - 3
    ri = ro - thickness
    ang, parts = -90.0, []
    for label, val, color in segments:
        frac = val / total
        if frac <= 0:
            continue
        a0, a1 = math.radians(ang), math.radians(ang + frac * 360)
        large = 1 if frac * 360 > 180 else 0
        x0, y0 = cx + ro * math.cos(a0), cy + ro * math.sin(a0)
        x1, y1 = cx + ro * math.cos(a1), cy + ro * math.sin(a1)
        x2, y2 = cx + ri * math.cos(a1), cy + ri * math.sin(a1)
        x3, y3 = cx + ri * math.cos(a0), cy + ri * math.sin(a0)
        d = (f"M{x0:.2f},{y0:.2f} A{ro:.2f},{ro:.2f} 0 {large} 1 {x1:.2f},{y1:.2f} "
             f"L{x2:.2f},{y2:.2f} A{ri:.2f},{ri:.2f} 0 {large} 0 {x3:.2f},{y3:.2f} Z")
        parts.append(f'<path d="{d}" fill="{color}"><title>{label}: {frac*100:.1f}%</title></path>')
        ang += frac * 360
    return f'<svg viewBox="0 0 {size} {size}" class="donut">{"".join(parts)}</svg>'


def bars(items, width=520, rowh=30):
    total = sum(v for _, v in items) or 1
    h = len(items) * rowh + 8
    out = [f'<svg viewBox="0 0 {width} {h}" class="bars" preserveAspectRatio="xMinYMin meet">']
    for i, (label, val) in enumerate(items):
        y = i * rowh + 4
        w = max(2, (val / total) * (width - 230))
        out.append(f'<text x="0" y="{y+15}" class="barlab">{label[:34]}</text>')
        out.append(f'<rect x="185" y="{y+3}" width="{w:.1f}" height="16" rx="3" fill="#4f8ef7"/>')
        out.append(f'<text x="{185+w+8:.1f}" y="{y+16}" class="barval">${val:,.0f} ({val/total*100:.1f}%)</text>')
    out.append('</svg>')
    return "".join(out)


def line(history, width=1040, height=240, pad=44):
    pts = [(d, v) for d, v in history if v]
    if len(pts) < 2:
        return ('<div class="empty">Not enough history yet — the trend line appears after '
                'the second daily run.</div>')
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi, lo = hi * 1.001, lo * 0.999
    n = len(pts)

    def X(i): return pad + i * (width - 2 * pad) / (n - 1)

    def Y(v): return height - pad - (v - lo) * (height - 2 * pad) / (hi - lo)

    path = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = path + f" L{X(n-1):.1f},{height-pad} L{X(0):.1f},{height-pad} Z"
    grid = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        grid += (f'<line x1="{pad}" y1="{y:.1f}" x2="{width-pad}" y2="{y:.1f}" class="grid"/>'
                 f'<text x="{pad-6}" y="{y+4:.1f}" class="ytick" text-anchor="end">${v/1000:,.0f}k</text>')
    dots = "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.5" fill="#4f8ef7"/>'
                   for i, (_, v) in enumerate(pts))
    first, last = pts[0][0], pts[-1][0]
    labels = (f'<text x="{pad}" y="{height-14}" class="xtick">{first}</text>'
              f'<text x="{width-pad}" y="{height-14}" class="xtick" text-anchor="end">{last}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" class="line" preserveAspectRatio="none">'
            f'{grid}<path d="{area}" fill="rgba(79,142,247,0.12)" stroke="none"/>'
            f'<path d="{path}" fill="none" stroke="#4f8ef7" stroke-width="2.5"/>{dots}{labels}</svg>')


def save_snapshot(asof, rows, total, cost):
    os.makedirs(DATA_DIR, exist_ok=True)
    hist = {}
    if os.path.exists(SNAP):
        for ln in open(SNAP, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                d = json.loads(ln)
                hist[d["date"]] = d
    key = asof.replace("/", "-") if asof else datetime.now().strftime("%Y-%m-%d")
    hist[key] = {"date": key, "total_value": round(total, 2), "total_cost": round(cost, 2),
                 "holdings": [{"code": r["code"], "account": r["account"],
                               "value": round(r["value"], 2)} for r in rows]}
    with open(SNAP, "w", encoding="utf-8") as f:
        for k in sorted(hist):
            f.write(json.dumps(hist[k]) + "\n")
    return sorted((k, v["total_value"]) for k, v in hist.items())


def add_value_log(asof, total, cost, day_pl):
    """One row per day in data/value_log.csv (deduped by date)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    key = asof.replace("/", "-") if asof else datetime.now().strftime("%Y-%m-%d")
    row = [key, f"{total:.2f}", f"{day_pl:.2f}", f"{total - cost:.2f}"]
    hist = {}
    if os.path.exists(VALUE_LOG):
        with open(VALUE_LOG, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if not r or r[0] == "date":
                    continue
                hist[r[0]] = r
    hist[key] = row
    with open(VALUE_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "market_value", "today_change", "gain_loss"])
        for k in sorted(hist):
            w.writerow(hist[k])


def render_dashboard(rows, total, cost, day_pl, asof, history, missing):
    day_pct = day_pl / (total - day_pl) * 100 if (total - day_pl) else 0
    gain = total - cost
    gain_pct = gain / cost * 100 if cost else 0

    funds = group(rows, "fund")
    accounts = group(rows, "account")
    segs = [(n, v, PALETTE[i % len(PALETTE)]) for i, (n, v) in enumerate(funds)]

    legend = "".join(
        f'<div class="lg"><span class="sw" style="background:{c}"></span>'
        f'<span class="lgn">{n}</span><span class="lgv">${v:,.0f} · {v/total*100:.1f}%</span></div>'
        for (n, v, c) in segs)

    def cls(x): return "pos" if x > 0 else ("neg" if x < 0 else "flat")
    def sgn(x): return f'+${x:,.2f}' if x >= 0 else f'-${abs(x):,.2f}'

    trs = "".join(
        f'<tr><td>{r["account"]}</td><td>{r["fund"]}</td><td class="mono">{r["code"]}</td>'
        f'<td class="num">{r["units"]:,.4f}</td><td class="num">{r["nav"]:,.4f}</td>'
        f'<td class="num">${r["value"]:,.2f}</td>'
        f'<td class="num">{r["value"]/total*100:.2f}%</td>'
        f'<td class="num {cls(r["day_pl"])}">{sgn(r["day_pl"])}<br><small>({r["day_pct"]:+.2f}%)</small></td>'
        f'<td class="num">${r["cost"]:,.2f}</td>'
        f'<td class="num {cls(r["gain"])}">{sgn(r["gain"])}<br><small>({r["gain_pct"]:+.1f}%)</small></td></tr>'
        for r in sorted(rows, key=lambda r: -r["value"]))

    warn = ""
    if missing:
        warn = f'<div class="warn">⚠ Codes not found in Manulife data: {", ".join(missing)}</div>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mutual Fund Dashboard</title>
<style>
 :root {{ --bg:#0f1420; --card:#171d2c; --line:#242c40; --txt:#e8ecf4; --mut:#8b97ad;
          --pos:#3ddc84; --neg:#ff6b81; --acc:#4f8ef7; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--txt);
        font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
 .wrap {{ max-width:1120px; margin:0 auto; padding:28px 20px 60px; }}
 h1 {{ font-size:22px; margin:0 0 2px; }}
 .sub {{ color:var(--mut); margin-bottom:22px; }}
 .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }}
 .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }}
 .card .k {{ color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
 .card .v {{ font-size:24px; font-weight:650; margin-top:6px; }}
 .pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .flat {{ color:var(--mut); }}
 .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:22px; }}
 .panel {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; }}
 .panel h2 {{ font-size:14px; margin:0 0 14px; color:var(--mut); text-transform:uppercase; letter-spacing:.05em; }}
 .donutwrap {{ display:flex; gap:20px; align-items:center; }}
 .donut {{ width:200px; height:200px; flex:0 0 200px; }}
 .lg {{ display:flex; align-items:center; gap:8px; margin:5px 0; font-size:13px; }}
 .sw {{ width:11px; height:11px; border-radius:3px; flex:0 0 11px; }}
 .lgn {{ flex:1; }} .lgv {{ color:var(--mut); font-variant-numeric:tabular-nums; }}
 .bars {{ width:100%; height:auto; }}
 .barlab {{ fill:var(--txt); font-size:12px; }} .barval {{ fill:var(--mut); font-size:11px; }}
 .line {{ width:100%; height:220px; }}
 .grid {{ stroke:var(--line); stroke-width:1; }}
 .ytick,.xtick {{ fill:var(--mut); font-size:11px; }}
 .empty {{ color:var(--mut); padding:40px 0; text-align:center; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th,td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; }}
 th {{ color:var(--mut); font-weight:500; font-size:11px; text-transform:uppercase; }}
 td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
 .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
 small {{ color:var(--mut); }}
 .warn {{ background:#3a2a12; border:1px solid #6b4d1a; color:#ffcf7a;
          padding:10px 14px; border-radius:10px; margin-bottom:16px; }}
 .foot {{ color:var(--mut); font-size:12px; margin-top:20px; }}
</style></head><body><div class="wrap">
 <h1>Mutual Fund Dashboard</h1>
 <div class="sub">Manulife GIF Select · as of {asof} · base currency CAD</div>
 {warn}
 <div class="cards">
  <div class="card"><div class="k">Portfolio value</div><div class="v">${total:,.2f}</div></div>
  <div class="card"><div class="k">Today's change</div>
     <div class="v {cls(day_pl)}">{sgn(day_pl)} <small>({day_pct:+.2f}%)</small></div></div>
  <div class="card"><div class="k">Gain / loss</div>
     <div class="v {cls(gain)}">{sgn(gain)} <small>({gain_pct:+.1f}%)</small></div></div>
  <div class="card"><div class="k">Cost (ACB)</div><div class="v">${cost:,.2f}</div></div>
 </div>
 <div class="grid2">
  <div class="panel"><h2>Allocation by fund</h2>
    <div class="donutwrap">{donut(segs)}<div>{legend}</div></div></div>
  <div class="panel"><h2>Value by account</h2>{bars(accounts)}</div>
 </div>
 <div class="panel" style="margin-bottom:22px"><h2>Portfolio value history</h2>
   {line(history)}</div>
 <div class="panel"><h2>Holdings</h2>
  <table><thead><tr>
    <th>Account</th><th>Fund</th><th>Code</th><th class="num">Units</th><th class="num">NAV</th>
    <th class="num">Value</th><th class="num">Weight</th><th class="num">Today</th>
    <th class="num">Cost</th><th class="num">Gain/Loss</th></tr></thead>
    <tbody>{trs}</tbody></table></div>
 <div class="foot">Generated {datetime.now():%Y-%m-%d %H:%M} · NAV source: funds.manulife.ca ·
   daily change is the fund's 1-day unit-value change as of {asof}.</div>
</div></body></html>"""


def simple_report(rows, total, cost, day_pl, asof, missing):
    """Write the daily report as report.txt and report.html."""
    gain = total - cost
    gain_pct = gain / cost * 100 if cost else 0.0
    day_pct = day_pl / (total - day_pl) * 100 if (total - day_pl) else 0.0

    def signed(x): return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"
    def pct(x): return f"{x:+.1f}%"

    accounts = group(rows, "account")
    funds = group_with_cost(rows, "fund")

    # ---------- report.txt ----------
    lines = [
        f"Mutual Fund Report — as of {asof} (CAD)",
        "=" * 46,
        f"Market value:   ${total:,.2f}",
        f"Gain / loss:    {signed(gain)}  ({pct(gain_pct)})",
        f"Today's change: {signed(day_pl)}  ({day_pct:+.2f}%)",
        f"Cost (ACB):     ${cost:,.2f}",
        "",
        "By account:",
    ]
    for name, val in accounts:
        lines.append(f"  {name:<18} ${val:>13,.2f}")
    lines += ["", "By fund:"]
    for name, val, cst in funds:
        gf = val - cst
        lines.append(f"  {name[:38]:<38} ${val:>13,.2f}  {signed(gf):>14}  "
                     f"({(gf / cst * 100 if cst else 0):+.1f}%)")
    if missing:
        lines += ["", f"NOTE: codes not found in Manulife data: {', '.join(missing)}"]
    text = "\n".join(lines) + "\n"
    open(REPORT_TXT, "w", encoding="utf-8").write(text)

    # ---------- report.html ----------
    def cls(x): return "pos" if x > 0 else ("neg" if x < 0 else "flat")
    acct_rows = "".join(
        f'<tr><td>{name}</td><td class="num">${val:,.2f}</td></tr>' for name, val in accounts)
    fund_rows = "".join(
        f'<tr><td>{name}</td><td class="num">${val:,.2f}</td>'
        f'<td class="num {cls(val - cst)}">{signed(val - cst)} '
        f'<span class="pct">({(val - cst) / cst * 100 if cst else 0:+.1f}%)</span></td></tr>'
        for name, val, cst in funds)
    warn = (f'<div class="warn">⚠ codes not found: {", ".join(missing)}</div>'
            if missing else "")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mutual Fund Report</title><style>
 body {{ margin:0; background:#0f1420; color:#e8ecf4;
        font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
 .wrap {{ max-width:560px; margin:0 auto; padding:44px 24px; }}
 .date {{ color:#8b97ad; margin-bottom:26px; }}
 .big {{ font-size:40px; font-weight:700; letter-spacing:-.02em; }}
 .label {{ color:#8b97ad; font-size:12px; text-transform:uppercase; letter-spacing:.06em; margin-top:24px; }}
 .pos {{ color:#3ddc84; }} .neg {{ color:#ff6b81; }} .flat {{ color:#8b97ad; }}
 table {{ width:100%; border-collapse:collapse; margin-top:6px; }}
 td {{ padding:7px 0; border-bottom:1px solid #242c40; }}
 td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
 .pct {{ color:#8b97ad; }}
 .warn {{ background:#3a2a12; border:1px solid #6b4d1a; color:#ffcf7a;
          padding:8px 12px; border-radius:8px; margin-top:16px; font-size:13px; }}
</style></head><body><div class="wrap">
 <div class="date">As of {asof} · CAD</div>
 <div class="label">Market value</div>
 <div class="big">${total:,.2f}</div>
 <div class="label">Gain / loss</div>
 <div class="big {cls(gain)}">{signed(gain)} <span style="font-size:20px">({pct(gain_pct)})</span></div>
 <div class="label">Today's change</div>
 <div style="font-size:24px;font-weight:600" class="{cls(day_pl)}">{signed(day_pl)}
   <span style="font-size:16px">({day_pct:+.2f}%)</span></div>
 <div class="label">By account</div>
 <table>{acct_rows}</table>
 <div class="label">By fund</div>
 <table>{fund_rows}</table>
 {warn}
</div></body></html>"""
    open(REPORT_HTML, "w", encoding="utf-8").write(html)
    return text


def main():
    holdings = load_holdings()
    by_code = fetch_funds()
    rows, missing = build(holdings, by_code)
    total = sum(r["value"] for r in rows)
    cost = sum(r["cost"] for r in rows)
    day_pl = sum(r["day_pl"] for r in rows)
    asof = rows[0]["asof"] if rows else None
    hist = save_snapshot(asof, rows, total, cost)
    add_value_log(asof, total, cost, day_pl)
    simple_report(rows, total, cost, day_pl, asof, missing)
    open(DASH, "w", encoding="utf-8").write(
        render_dashboard(rows, total, cost, day_pl, asof, hist, missing))
    print(f"as of {asof}: value ${total:,.2f} | today {day_pl:+,.2f} "
          f"| gain ${total - cost:,.2f} | {len(rows)} holdings")
    if missing:
        print("MISSING CODES:", missing)
    print("wrote report.txt, report.html, dashboard.html and data/value_log.csv")


if __name__ == "__main__":
    main()
