# Finance — Daily Mutual Fund Report

Tracks Manulife (GIF Select) mutual fund holdings and generates a simple daily report.

## What it does

`fetch_report.py`:
1. Reads holdings from `holdings.csv`.
2. Fetches each fund's live NAV and 1-day change from Manulife's public fund API
   (`funds.manulife.ca/profiles/api/funds`).
3. Computes market value, today's change, and gain/loss vs cost (ACB).
4. Appends one row per day to `data/value_log.csv` (deduped by date).
5. Appends a per-day snapshot to `data/snapshots.jsonl` (dashboard history chart).
6. Writes a simple report (`report.txt`, `report.html`) **and** a full `dashboard.html`.

## Run it

```bash
python3 fetch_report.py
open report.html          # quick view (or: cat report.txt)
open dashboard.html       # full dashboard: allocation, charts, per-fund table
```

Only the Python standard library is required.

## Files

| File | Purpose |
|---|---|
| `holdings.csv` | Your holdings: account, fund, code, currency, units, ACB |
| `fetch_report.py` | Fetcher + report generator |
| `run_report.sh` | Wrapper invoked by the launchd schedule |
| `report.txt` | Generated daily report (plain text) |
| `report.html` | Generated daily report (one-page view) |
| `dashboard.html` | Generated full dashboard (allocation, charts, per-fund table) |
| `data/value_log.csv` | One row per day: date, market value, today's change, gain/loss |
| `data/snapshots.jsonl` | One record per day — drives the dashboard history chart |
| `data/run.log` | Scheduled-run history |
| `tools/ocr.swift` | On-device OCR (images/PDFs) used to import statements |

## Report contents

- **Market value**, **gain/loss** (vs ACB) and **today's change**
- Breakdown **by account**
- Breakdown **by fund** (value + gain/loss per fund)

## holdings.csv columns

- `account` — account label (freely rename)
- `fund_name` — display name
- `code` — Manulife fund-serv code, e.g. `MGF1916` (drives the price lookup)
- `currency` — `CAD`
- `units` — units held
- `acb` — adjusted cost base in CAD (for gain/loss)

## Daily automation

Installed as a macOS **launchd** agent: `~/Library/LaunchAgents/com.fannyng.finance.dailyreport.plist`.
It runs **weekdays (Mon–Fri) at 22:00 local (Eastern)** — after Manulife publishes NAVs —
by calling `run_report.sh`, which runs `fetch_report.py` and logs to `data/run.log`.
If the Mac is asleep at 22:00, launchd runs the job once it wakes.

Manage it:

```bash
# status
launchctl print gui/$(id -u)/com.fannyng.finance.dailyreport

# run now
launchctl kickstart -k gui/$(id -u)/com.fannyng.finance.dailyreport

# stop / remove
launchctl bootout gui/$(id -u)/com.fannyng.finance.dailyreport
```

## Notes / assumptions

- Base currency is **CAD**; all holdings are CAD. Multi-currency would need FX handling.
- Statement screenshots were as of **2026-10-08**; NAVs were verified against the API.
- `MGF8295` (Fidelity Bundle, 0 units) was removed — it has no value and is absent from the API.
