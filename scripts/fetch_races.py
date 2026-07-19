#!/usr/bin/env python3
"""Fetch cyclocross races from BikeReg and write the site's data file.

Pulls the season's events from BikeReg's public Event Search API
(month-by-month, deduped), filters out non-race listings (camps, clinics,
season passes), normalizes dates, and writes js/race-data.js for the site.

Zero dependencies beyond the Python 3 standard library.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# --- Season / query configuration -------------------------------------------

SEASON_START = date(2026, 8, 1)
SEASON_END = date(2027, 1, 31)
EVENT_TYPE = "cyclocross"

# BikeReg caps responses at 100 events. Month windows stay well under that
# today; if any window ever returns exactly MAX_RESULTS the script warns so
# the window can be split (see season_windows).
MAX_RESULTS = 100

API_URL = "https://www.bikereg.com/api/search"
# BikeReg's CDN 403s non-browser user agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
REQUEST_PAUSE_SECONDS = 1.0

# Listings whose EventTypes include these keywords are not races.
EXCLUDED_TYPE_KEYWORDS = ("camp", "clinic")
# A race weekend spans a few days at most; longer listings are season passes,
# series memberships, or programs.
MAX_RACE_SPAN_DAYS = 4

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Date parsing ------------------------------------------------------------

DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)([+-])(\d{2})(\d{2})\)/")


def parse_dotnet_date(value):
    """Parse BikeReg's .NET JSON date '/Date(1786593600000-0400)/' to an
    offset-aware datetime in the event's local timezone. Returns None for
    null/unparseable values."""
    if not value:
        return None
    match = DOTNET_DATE_RE.match(value)
    if not match:
        return None
    ms, sign, hours, minutes = match.groups()
    offset = timedelta(hours=int(hours), minutes=int(minutes))
    if sign == "-":
        offset = -offset
    return datetime.fromtimestamp(int(ms) / 1000, timezone(offset))


# --- Fetching ----------------------------------------------------------------


def season_windows(start=SEASON_START, end=SEASON_END):
    """Yield (window_start, window_end) date pairs, one per calendar month,
    clipped to the season. Kept as a generator so the window size can shrink
    (e.g. half-months) if a month ever nears the API's result cap."""
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        yield cursor, min(next_month - timedelta(days=1), end)
        cursor = next_month


def fetch_window(window_start, window_end):
    """Fetch one date window from the API. Returns the raw event list."""
    params = urllib.parse.urlencode(
        {
            "eventType": EVENT_TYPE,
            "startDate": window_start.isoformat(),
            "endDate": window_end.isoformat(),
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("MatchingEvents") or []


def fetch_season():
    """Fetch every window in the season, deduping by EventId.

    A failed window is reported and skipped so one bad request doesn't kill
    the whole refresh. Returns (events_by_id, failed_windows)."""
    events = {}
    failures = []
    for window_start, window_end in season_windows():
        try:
            raw_events = fetch_window(window_start, window_end)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"  {window_start:%Y-%m}: FAILED ({exc})", file=sys.stderr)
            failures.append((window_start, window_end))
            continue
        new = [e for e in raw_events if e["EventId"] not in events]
        for event in new:
            events[event["EventId"]] = event
        print(f"  {window_start:%Y-%m}: {len(raw_events)} events ({len(new)} new)")
        if len(raw_events) >= MAX_RESULTS:
            print(
                f"  WARNING: {window_start:%Y-%m} returned {len(raw_events)} events, "
                "at the API cap — split this window (see season_windows)",
                file=sys.stderr,
            )
        time.sleep(REQUEST_PAUSE_SECONDS)
    return events, failures


# --- Normalization -----------------------------------------------------------


def exclusion_reason(raw_event):
    """Return why this listing isn't a race, or None to keep it."""
    for event_type in raw_event.get("EventTypes") or []:
        for keyword in EXCLUDED_TYPE_KEYWORDS:
            if keyword in event_type.lower():
                return f"event type '{event_type}'"
    start = parse_dotnet_date(raw_event.get("EventDate"))
    end = parse_dotnet_date(raw_event.get("EventEndDate")) or start
    if start and end:
        span = (end.date() - start.date()).days + 1
        if span > MAX_RACE_SPAN_DAYS:
            return f"spans {span} days"
    return None


def normalize_event(raw_event):
    """Normalize one raw API event into the record the site consumes."""
    start = parse_dotnet_date(raw_event["EventDate"])
    end = parse_dotnet_date(raw_event.get("EventEndDate")) or start
    reg_open = parse_dotnet_date(raw_event.get("RegOpenDate"))
    reg_close = parse_dotnet_date(raw_event.get("RegCloseDate"))
    # The API hands out http:// permalinks; the site itself is https.
    url = raw_event.get("EventPermalink") or raw_event.get("EventUrl")
    if url and url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return {
        "id": raw_event["EventId"],
        "name": raw_event["EventName"],
        "city": raw_event.get("EventCity"),
        "state": raw_event.get("EventState"),
        "lat": raw_event.get("Latitude"),
        "lng": raw_event.get("Longitude"),
        "startDate": start.date().isoformat(),
        "endDate": end.date().isoformat(),
        "days": (end.date() - start.date()).days + 1,
        "regOpen": reg_open.isoformat() if reg_open else None,
        "regClose": reg_close.isoformat() if reg_close else None,
        "url": url,
        "presentedBy": raw_event.get("PresentedBy"),
        "eventTypes": raw_event.get("EventTypes") or [],
        "categories": [
            {
                "name": category.get("CategoryName"),
                "startTime": category.get("StartTime"),
                "fee": category.get("EntryFee"),
            }
            for category in raw_event.get("Categories") or []
        ],
    }


def normalize_season(events_by_id):
    """Split raw events into normalized races and an excluded-listings log."""
    races = []
    excluded = []
    for raw_event in events_by_id.values():
        reason = exclusion_reason(raw_event)
        if reason:
            excluded.append((raw_event["EventName"], reason))
        else:
            races.append(normalize_event(raw_event))
    races.sort(key=lambda race: (race["startDate"], race["name"]))
    return races, excluded


# --- Output ------------------------------------------------------------------


def write_race_data(races, path):
    """Write the site's data file: a JS file assigning RACE_DATA."""
    data = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seasonStart": SEASON_START.isoformat(),
        "seasonEnd": SEASON_END.isoformat(),
        "events": races,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "// Generated by scripts/fetch_races.py — do not edit by hand.\n"
        f"const RACE_DATA = {json.dumps(data, indent=1)};\n"
    )


def main():
    print(f"Fetching {EVENT_TYPE} events {SEASON_START} → {SEASON_END}")
    events_by_id, failures = fetch_season()
    if not events_by_id:
        print("No events fetched — refusing to overwrite data file.", file=sys.stderr)
        return 1
    races, excluded = normalize_season(events_by_id)
    print(f"\n{len(races)} races kept, {len(excluded)} listings excluded:")
    for name, reason in excluded:
        print(f"  excluded: {name} ({reason})")
    output_path = REPO_ROOT / "js" / "race-data.js"
    write_race_data(races, output_path)
    print(f"\nWrote {output_path.relative_to(REPO_ROOT)}")
    if failures:
        print(f"{len(failures)} window(s) failed — data may be incomplete.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
