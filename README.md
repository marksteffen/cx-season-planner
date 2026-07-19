# CX Season Planner

A one-page planner for the 2026–27 cyclocross season: every CX race listed on
[BikeReg](https://www.bikereg.com), with drive times from Brooklyn, NY,
registration windows, categories, and one-click "add to Google Calendar" links.

**How it stays fresh:** there is no server. A GitHub Actions workflow runs the
fetch script every morning, commits the updated data file, and GitHub Pages
serves the result. The committed [js/race-data.js](js/race-data.js) *is* the
database.

## How it works

```
BikeReg Event Search API ──► scripts/fetch_races.py ──► js/race-data.js ──► index.html
                                   │    ▲
                    OSRM routing   │    │  data/drivetime-cache.json
                    (drive times) ─┴────┘  (one route per event, ever)
```

- **`scripts/fetch_races.py`** — stdlib-only Python. Queries BikeReg's public
  API month-by-month across the season window, dedupes, drops non-race listings
  (camps, clinics, and anything spanning more than 4 days — season passes and
  series memberships masquerade as events), parses the `.NET /Date(…)/`
  timestamps, then asks [OSRM](https://project-osrm.org) for the driving time
  from Brooklyn to each new event. Results land in `js/race-data.js`.
- **`data/drivetime-cache.json`** — drive times keyed by event id, committed so
  the daily run only routes newly posted races. If OSRM is unreachable, the
  script falls back to a straight-line estimate (flagged in the UI as
  "estimate") and retries it on a later run.
- **`index.html` + `js/app.js` + `css/style.css`** — a static page, no build
  step. Registration badges (Opens {date} / Open / Closed) are computed in the
  browser from the raw dates on every load, so they stay correct even between
  refreshes. Starred races live in the browser's localStorage and never leave
  your device.

## Refresh model

- **Automatic:** `.github/workflows/refresh.yml` runs daily at ~6am ET
  (10:00/11:00 UTC depending on DST) and commits `js/race-data.js` +
  `data/drivetime-cache.json` only when they changed. If the script fails, the
  workflow fails loudly and the site keeps serving the last good data.
- **Manual:** Actions tab → *Refresh race data* → *Run workflow*, or locally:

  ```sh
  python3 scripts/fetch_races.py
  ```

  No dependencies to install; Python 3.9+ is enough.

- **Note:** GitHub disables cron workflows in repos with no activity for 60
  days. The workflow's own daily commits count as activity, so this shouldn't
  happen — if it ever does, one click in the Actions tab re-enables it.

## Running locally

```sh
python3 -m http.server 8642
# open http://localhost:8642
```

(Opening `index.html` straight from the filesystem also works — the data is a
script tag, not a fetch.)

## Tests

```sh
cd scripts && python3 test_fetch_races.py
```

Fixtures in `scripts/fixtures/` are trimmed real API responses.

## Known limits

- **Drive times are typical, not live** — OSRM gives traffic-free durations
  from a fixed Brooklyn origin. Read "2h 34m" as "about two and a half hours on
  a good day."
- **The API caps responses at 100 events per request.** The script queries one
  month at a time and warns if any window hits the cap (none come close today);
  windows can be split further if the calendar ever gets that dense.
- **Season window is fixed** in `scripts/fetch_races.py` (`SEASON_START` /
  `SEASON_END`) — bump it next season.
