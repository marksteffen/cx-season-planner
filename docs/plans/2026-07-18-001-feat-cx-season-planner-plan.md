---
title: "feat: Cyclocross Season Planner site"
type: feat
status: completed
date: 2026-07-18
---

# feat: Cyclocross Season Planner site

## Overview

A personal webapp that lists cyclocross races nationwide from BikeReg, prioritized by drive time from Brooklyn NY, with one-click "add to Google Calendar" links. Data comes from BikeReg's official public Event Search API (verified live during planning, no auth required). The site is hosted on GitHub Pages, and a GitHub Actions scheduled workflow refreshes the data daily in the cloud: it runs the fetch script, commits the updated data file, and the site redeploys. No server, no database, and nothing running on Mark's machine.

**Target repo:** `cx-season-planner`, a standalone public repo living at `~/Desktop/Personal Projects/cx-season-planner` (git already initialized; this plan lives in it at `docs/plans/`). Published to GitHub as a public repo during Unit 5. All file paths below are relative to the repo root. This project is independent of the PM-OS workspace.

## Problem Frame

Mark is planning his cyclocross racing season (roughly Aug 2026 through Jan 2027). Today that means manually browsing BikeReg's calendar, guessing at drive times, and cross-referencing dates. He wants one page that answers: what races exist, how far away are they, is registration open, and what categories can I race. When he commits to a race, adding it to Google Calendar should be one click, with no auth setup.

## Requirements Trace

- R1. Pull cyclocross races nationwide from BikeReg.com
- R2. Show per race: name, date(s), 1-day vs 2-day, location (city/state), drive time from Brooklyn NY, link to BikeReg registration page
- R3. Show registration status (open / not yet open / closed) and registration close date when available
- R4. Show categories offered at each race (bonus requirement, fully supported by the API)
- R5. Prioritize/sort races by proximity to Brooklyn
- R6. Simplest possible Google Calendar add: prefilled event link, no OAuth, no email plumbing
- R7. Data refreshes automatically on a schedule with no action from Mark and nothing running on his machine
- R8. The site is reachable from any device via a URL (hosted webapp, not a local file)

## Scope Boundaries

- No backend server or database. The "webapp" is a static site on GitHub Pages; the committed `js/race-data.js` file is the datastore, updated by a scheduled GitHub Actions workflow.
- Public repo (confirmed by Mark 2026-07-18; required for free GitHub Pages + Actions on a personal account). Everything in it is public race data plus the site code; the starred list stays in the browser's localStorage and is never in the repo.
- No accounts. "Races I'm considering" is a localStorage star per race plus a "Starred only" filter (Unit 3); nothing syncs anywhere. Committing to a race = the calendar click.
- Refresh cadence is daily (race listings change over days/weeks; reg open/closed badges are computed client-side from raw dates on every page load, so they are always current regardless of data age). Manual refresh stays available: rerun the workflow from the Actions tab or run the script locally.
- No traffic-aware drive times. OSRM gives typical (free-flow-ish) durations; that is the "average drive time" for planning purposes.
- No scraping of BikeReg HTML pages. API only.

## Context & Research

### Relevant Code and Patterns

- `outputs/prototypes/creator-roadmap/` in Mark's PM-OS workspace (`~/Desktop/PM-OS`) — reference pattern from a prior project: `index.html` + `js/roadmap-data.js` (data shipped as a JS file, not fetched, so the page works from `file://` and on static hosting with zero CORS issues). Follow this data-as-JS pattern; no code is shared.

### External References (verified live on 2026-07-18)

- **BikeReg Event Search API**: `GET https://www.bikereg.com/api/search` — public, no auth, JSON. Verified working params: `eventType=cyclocross`, `startDate=YYYY-MM-DD`, `endDate=YYYY-MM-DD`. Response: `{ MatchingEvents: [...] }`, max 100 events per request, chronological order.
- Verified event fields: `EventId`, `EventName`, `EventCity`, `EventState`, `EventZip`, `EventDate`, `EventEndDate`, `Latitude`, `Longitude`, `EventPermalink` (registration page), `RegOpenDate`, `RegCloseDate`, `EventTypes` (array, e.g. `['Cyclocross','NEBRA']`), `PresentedBy`, `Categories` (array of `{CategoryName, CategoryDates, EntryFee, StartTime, FieldLimit, RegistrationCount}`).
- Dates are .NET JSON format: `/Date(1786593600000-0400)/` (epoch ms + UTC offset) — needs parsing.
- Sample response saved at scratchpad `bikereg-sample.json` during planning.
- **OSRM public demo server**: `https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false` — free driving durations, no key. Community server: throttle requests (~1/sec) and cache results.
- **Google Calendar event template URL**: `https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=YYYYMMDD/YYYYMMDD&location=...&details=...` — opens a prefilled event in the user's Google Calendar; all-day date range format handles 1- and 2-day races. Zero auth.

## Key Technical Decisions

- **Official API over scraping**: BikeReg publishes this API for exactly this use; it's faster, stable, and complete (categories, reg windows, lat/long included).
- **Fetch script + static site, no backend**: a Python 3 stdlib script (`urllib`, `json`, no pip installs) fetches and enriches data, writing `js/race-data.js`. The site is pure static HTML/JS. Zero-dependency Python means the CI workflow needs no package install step.
- **GitHub Pages + Actions cron instead of a server**: the scheduled workflow (daily, early morning ET) runs `fetch_races.py`, and commits `js/race-data.js` + `data/drivetime-cache.json` only when they changed; Pages serves the updated site. The committed drive-time cache means each daily run only routes newly posted races, keeping OSRM usage tiny. Alternatives rejected: a hosted backend (Vercel/Cloudflare functions + storage) adds accounts and moving parts for zero user-visible benefit at this scale; browser-side live fetch is impossible anyway (BikeReg sends no CORS headers).
- **Month-by-month paging**: the API caps at 100 results; querying one month at a time across the season window (Aug 1 2026 – Jan 31 2027) and deduping by `EventId` stays safely under the cap (September nationwide returned 26 events as of planning; will grow as organizers post, monthly slicing leaves ample headroom).
- **Drive times via OSRM at refresh time, cached**: computed once per event in the fetch script from a fixed Brooklyn origin (40.6782, -73.9442), cached in `data/drivetime-cache.json` keyed by `EventId` so reruns only route new events. Fallback ladder: OSRM success → real drive time; OSRM failure with lat/long present → haversine-distance estimate (`miles / 45 mph`), flagged as an estimate in the UI; lat/long absent → null drive time (renders as "—", sorts last).
- **Calendar = prefilled Google Calendar link** (R6): a per-race "Add to Google Calendar" link using the template URL, prefilled with race name, all-day date range, location, and the BikeReg URL in the description. One click, opens GCal, Mark hits Save. Email-an-invite was considered and rejected: it requires SMTP or an API credential, which violates "don't waste time on auth." An `.ics` download link is a trivial add-on for non-Google calendars if ever needed.
- **Filter out non-race listings**: `eventType=cyclocross` also returns items typed `Cycling Camp`/`Clinic`, plus season passes, series memberships, and junior programs listed as single "events" spanning weeks or months (16 of 100 sampled events span >2 days; one spans 348 days). Exclude events whose `EventTypes` include camp/clinic types AND any event spanning more than 4 calendar days (not a race weekend). Log excluded events in the script output so miscategorized real races are noticeable.
- **Registration status is two dates, three displays**: `RegOpenDate` in the future → badge "Opens {date}"; between open and close → "Open" with close date shown; past `RegCloseDate` → "Closed". No arbitrary "opening soon" threshold to define.

## Open Questions

### Resolved During Planning

- Does BikeReg have an API or do we scrape? → Official public API, verified live.
- Can we tell 1-day vs 2-day races? → Yes: `EventEndDate` vs `EventDate` (calendar days spanned).
- Can we get reg open/close? → Yes: `RegOpenDate` / `RegCloseDate` (close date may be null; show "—" and treat as open-ended). Display logic: future open date → "Opens {date}", otherwise Open/Closed by close date.
- Simplest calendar integration? → Prefilled Google Calendar template link; no auth, no email.
- How does it refresh without Mark's machine? → GitHub Actions scheduled workflow commits fresh data daily; GitHub Pages serves it. The committed data file is the datastore; no server or database needed.

### Deferred to Implementation

- Exact throttle/retry behavior against OSRM if it rate-limits mid-run — tune when running against the real event count.
- Whether September (peak season, fully posted) ever nears the 100-event cap — if so, split paging to half-month windows; the paging code should make the window size a constant.

## Output Structure

    cx-season-planner/          (repo root, at ~/Desktop/Personal Projects/)
    ├── docs/plans/             # this plan
    ├── index.html              # the site
    ├── css/style.css
    ├── js/app.js               # rendering, sort/filter, calendar links
    ├── js/race-data.js         # generated by fetch script (committed; this is the datastore)
    ├── data/drivetime-cache.json
    ├── scripts/fetch_races.py  # BikeReg fetch + OSRM enrichment + race-data.js writer
    ├── scripts/test_fetch_races.py
    ├── .github/workflows/refresh.yml  # daily scheduled data refresh
    └── README.md               # architecture, refresh model, how to run locally

## Implementation Units

- [x] **Unit 1: BikeReg fetch and normalize script**

**Goal:** `scripts/fetch_races.py` pulls the full season of cyclocross events and normalizes them into clean JSON records.

**Requirements:** R1, R2 (partial), R3, R4, R7

**Dependencies:** None

**Files:**
- Create: `scripts/fetch_races.py`
- Test: `scripts/test_fetch_races.py`

**Approach:**
- Query `api/search` per calendar month over the season window (constants at top of file: window, event type, origin coords, max race span)
- Dedupe by `EventId`; exclude `EventTypes` containing `Cycling Camp` or `Clinic`, and exclude events spanning more than 4 calendar days (season passes / series memberships / programs, not races); print excluded event names so misfiled real races are catchable
- Parse `/Date(ms-offset)/` into ISO dates; derive `days` from `EventDate`→`EventEndDate` calendar-day span
- Emit raw `RegOpenDate`/`RegCloseDate`; the UI derives the display (`Opens {date}` / `Open` / `Closed`) against today's date, so no status is baked in at fetch time
- Carry through categories (name, start time, entry fee), location fields, lat/long, permalink
- Set a browser-like User-Agent (BikeReg's CDN 403s default agents)

**Test scenarios:**
- Happy path: a trimmed fixture of 5-10 representative events (1-day CX, 2-day CX, camp+CX combo, null RegCloseDate, missing lat/long, both `-0400` and `-0500` offsets) normalizes to expected records with ISO dates. Extract the fixture from a live API response; do not commit the full 1.2MB sample payload
- Happy path: event with `EventEndDate` one calendar day after `EventDate` → `days: 2`
- Edge case: same-day `EventEndDate` → `days: 1`
- Edge case: null `RegCloseDate` → close date null, record still valid
- Error path: event spanning 30+ days (season pass) is excluded and reported in script output; a 2-day race weekend is kept
- Edge case: `/Date(...-0500)/` and `-0400` offsets both parse to the correct local calendar date
- Edge case: duplicate `EventId` across two month windows → appears once
- Error path: event typed `['Cycling Camp','Cyclocross']` is excluded; `['Cyclocross','NEBRA']` is kept
- Error path: HTTP failure on one month window → script reports it and continues with other months rather than dying

**Verification:**
- Running the script prints a per-month event count and writes a normalized JSON structure covering the real season; spot-check a known race (e.g. a CCAP Rocky Hill series event) has correct dates, categories, and reg window

- [x] **Unit 2: Drive-time enrichment**

**Goal:** Each event gets `driveMinutes` and `driveMiles` from Brooklyn, cached across reruns.

**Requirements:** R2, R5

**Dependencies:** Unit 1

**Files:**
- Modify: `scripts/fetch_races.py`
- Create: `data/drivetime-cache.json`
- Test: `scripts/test_fetch_races.py`

**Approach:**
- After normalization, for events missing from the cache, call OSRM driving route from the Brooklyn origin; throttle ~1 req/sec
- Cache `{EventId: {minutes, miles, source}}`; `source` is `osrm` or `estimate`
- Fallback ladder: OSRM error with lat/long present → haversine `miles / 45 mph` estimate (`source: "estimate"`); lat/long absent → null drive time, no routing attempted
- Final step writes `js/race-data.js` as `const RACE_DATA = {...};` including a `generatedAt` timestamp

**Test scenarios:**
- Happy path: cached event is not re-requested (mock/fake the router call)
- Edge case: missing lat/long → null drive time, record still emitted
- Error path: OSRM non-200 → haversine estimate used, `source: "estimate"`
- Happy path: output file is valid JS defining `RACE_DATA` with `generatedAt` and events sorted by date

**Verification:**
- Second consecutive run makes zero OSRM calls and produces identical output; drive time for a known race (e.g. a Connecticut CCAP race ≈ 2h from Brooklyn) passes a sanity check

- [x] **Unit 3: Season planner UI**

**Goal:** `index.html` renders the season: every race with name, dates, day count, location, drive time, reg status badge, reg close date, categories, and a link to BikeReg.

**Requirements:** R2, R3, R4, R5

**Dependencies:** Unit 2 (needs `race-data.js` shape)

**Files:**
- Create: `index.html`, `css/style.css`, `js/app.js`

**Approach:**
- Load `js/race-data.js` via script tag (works from `file://`, matches `creator-roadmap` pattern)
- Default view: chronological list grouped by month, each row showing drive time prominently. Proximity emphasis uses the same buckets as the filter: under 2h rows highlighted, 2-4h neutral, 4h+ muted — this is the "prioritize closer" behavior
- Controls: sort by date or by drive time; max-drive-time filter (2h / 4h / 8h / any); toggle to hide closed-registration races; "Starred only" toggle
- Sorting by drive time drops the month grouping and shows one flat proximity-ordered list (nulls last)
- Reg status derived client-side from raw dates against today: future open date → "Opens {date}", between open and close → "Open" (+ close date), past close → "Closed"
- Categories collapsed by default, expandable per race (many races have 20+ categories)
- Star/save races to localStorage as a lightweight "I'm considering this" marker; starring and the calendar link stay independent actions
- Show `generatedAt` ("data refreshed X") so it's obvious when the last scheduled refresh ran
- Empty state: when the active filter combination matches zero races, show a message suggesting widening the drive-time range or including closed registrations (never a silent blank list)

**Execution note:** Use the frontend-design skill when building this page; it should look like a purpose-built planner, not a default HTML table.

**Test scenarios:** (manual, via browser preview — no JS test infra in this repo's prototypes)
- Happy path: races render with all R2/R3/R4 fields; sort and filter controls change ordering/visibility correctly
- Edge case: race with null drive time renders "—" and sorts last under drive-time sort
- Happy path: drive-time sort shows a flat proximity-ordered list (no month headers); switching back to date sort restores month grouping
- Happy path: starring persists across reload; "Starred only" toggle shows just starred races
- Edge case: race with null RegCloseDate shows open-ended registration
- Edge case: 2-day race clearly badged "2 days"; category expand/collapse works on a race with 60+ categories
- Edge case: filter combination with zero matches shows the empty-state message instead of a blank list

**Verification:**
- Open via browser preview; verify against the live BikeReg pages for 2–3 races (dates, reg status, category names match)

- [x] **Unit 4: Google Calendar links + README**

**Goal:** One-click "Add to Google Calendar" per race, and a README documenting the refresh workflow.

**Requirements:** R6, R7

**Dependencies:** Unit 3

**Files:**
- Modify: `js/app.js`, `index.html`
- Create: `README.md`
- Create: `.claude/launch.json` (static-server entry so the site can be previewed during development, e.g. `python3 -m http.server`)

**Approach:**
- Build the GCal template URL per race: title = race name, all-day `dates=YYYYMMDD/YYYYMMDD+1` (end-exclusive; 2-day races span both days), location = "City, ST", details = BikeReg registration link + categories teaser
- Open in a new tab; Mark reviews the prefilled event and clicks Save in GCal
- README: what this is, the refresh model (daily via Actions, manual via workflow_dispatch or local script run), how to run locally, known limits (OSRM estimates, 100-per-request cap handling)

**Test scenarios:**
- Happy path: 1-day race link → GCal shows a single all-day event on the right date
- Edge case: 2-day race link → GCal shows an all-day event spanning both days (end-exclusive date handled)
- Edge case: race name with `&`/`#` characters URL-encodes correctly
- Happy path: details field contains a working BikeReg registration URL

**Verification:**
- Click through for one near-term race; the prefilled GCal event matches the race's name, dates, and location

- [x] **Unit 5: Deploy as a webapp with scheduled refresh**

**Goal:** The site lives at a public URL and its data refreshes daily with no involvement from Mark or his machine.

**Requirements:** R7, R8

**Dependencies:** Units 1-4 (working site and script)

**Files:**
- Create: `.github/workflows/refresh.yml` (in the new repo)
- Modify: `README.md`

**Approach:**
- Create the `cx-season-planner` GitHub repo (public) from the project directory and enable GitHub Pages serving from the default branch root. Confirm with Mark before creating the public repo; this is the one outward-facing step in the plan
- `refresh.yml`: `schedule` cron daily around 6am ET plus `workflow_dispatch` for manual runs; job runs `python3 scripts/fetch_races.py`, then commits and pushes `js/race-data.js` and `data/drivetime-cache.json` only if changed (skip-empty commit guard)
- Workflow needs only the default `GITHUB_TOKEN` with contents write permission; no secrets of any kind
- On script failure the workflow fails loudly (GitHub emails Mark by default); the site keeps serving the last good data because the data file is only replaced on success

**Test scenarios:**
- Happy path: manual `workflow_dispatch` run fetches, commits changed data, and the live site shows the new `generatedAt` timestamp within minutes
- Edge case: run with no data changes ends green without creating an empty commit
- Error path: script exiting non-zero fails the workflow run without committing anything; live site still serves the previous data

**Verification:**
- Site loads at the GitHub Pages URL on desktop and phone; the Actions tab shows a green scheduled run and the `generatedAt` shown on the site matches it

## System-Wide Impact

- **External dependencies:** BikeReg API (unversioned, could change shape — normalization isolates this in one script) and OSRM demo server (best-effort community service — cache + haversine fallback means the site never breaks when it's down).
- **Unchanged invariants:** This is a standalone repo; nothing in Mark's PM-OS workspace or any other project is touched.
- **Integration coverage:** The real proof is one full `fetch_races.py` run against the live API followed by browser verification against live BikeReg pages (Units 1–3 verification steps).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| BikeReg API shape changes or starts blocking non-browser agents | Browser User-Agent header; all parsing isolated in `fetch_races.py`; trimmed representative fixture kept with the tests |
| OSRM demo server rate-limits or goes down | Per-event cache, 1 req/sec throttle, haversine fallback flagged as estimate |
| A month window exceeds the 100-result cap at peak season | Window size is a constant; drop to half-month windows if any window returns exactly 100 |
| Early-season data is sparse (organizers haven't posted yet) | Daily scheduled refresh picks up new races automatically as organizers post through the summer |
| GitHub disables cron workflows in repos with no activity for 60 days | The workflow's own daily data commits count as activity; if it ever gets disabled, one click in the Actions tab re-enables it (noted in README) |
| OSRM demo server unreachable from CI runners on some runs | Same fallback ladder as local runs; cache means a bad day only affects newly posted races, retried next day |
| Reg status drifts as the data file ages | Status computed client-side from raw dates at page load, not baked in at fetch time |

## Sources & References

- BikeReg Event Search API: https://www.bikereg.com/api/search (verified live 2026-07-18)
- OSRM demo routing: https://router.project-osrm.org
- Google Calendar template URL: https://calendar.google.com/calendar/render?action=TEMPLATE
- Existing prototype pattern: `outputs/prototypes/creator-roadmap/`
