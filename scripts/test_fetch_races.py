#!/usr/bin/env python3
"""Tests for fetch_races.py. Run: python3 scripts/test_fetch_races.py

Fixture: scripts/fixtures/events_fixture.json — trimmed real events from the
live API (2026-07-18), plus two synthesized variants (null RegCloseDate,
missing lat/long)."""

import json
import re
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

import fetch_races

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "events_fixture.json"


def load_fixture():
    with open(FIXTURE_PATH) as f:
        return {e["EventId"]: e for e in json.load(f)["MatchingEvents"]}


FIXTURE = load_fixture()


class ParseDotnetDateTest(unittest.TestCase):
    def test_edt_offset_parses_to_local_calendar_date(self):
        parsed = fetch_races.parse_dotnet_date("/Date(1788321600000-0400)/")
        self.assertEqual(parsed.date().isoformat(), "2026-09-02")

    def test_est_offset_parses_to_local_calendar_date(self):
        # Keene Pumpkin Cross: Nov 8 2026, -0500 offset
        parsed = fetch_races.parse_dotnet_date(FIXTURE[73083]["EventDate"])
        self.assertEqual(parsed.date().isoformat(), "2026-11-08")

    def test_null_and_garbage_return_none(self):
        self.assertIsNone(fetch_races.parse_dotnet_date(None))
        self.assertIsNone(fetch_races.parse_dotnet_date("not a date"))


class NormalizeEventTest(unittest.TestCase):
    def test_one_day_race_normalizes(self):
        race = fetch_races.normalize_event(FIXTURE[75277])
        self.assertEqual(race["name"], "CCAP Rocky Hill Cyclocross Series #2")
        self.assertEqual(race["startDate"], "2026-09-02")
        self.assertEqual(race["endDate"], "2026-09-02")
        self.assertEqual(race["days"], 1)
        self.assertEqual(race["city"], "Rocky Hill")
        self.assertEqual(race["state"], "CT")
        self.assertEqual(race["regOpen"], "2026-06-01T00:15:00-04:00")
        self.assertEqual(race["regClose"], "2026-09-01T23:59:00-04:00")
        self.assertTrue(race["url"].startswith("https://"))
        self.assertEqual(race["categories"][0]["name"], "CCAP Led Junior Practice")
        self.assertEqual(race["categories"][1]["fee"], 20.0)

    def test_two_day_race_has_days_2(self):
        race = fetch_races.normalize_event(FIXTURE[77025])
        self.assertEqual(race["startDate"], "2026-10-03")
        self.assertEqual(race["endDate"], "2026-10-04")
        self.assertEqual(race["days"], 2)

    def test_two_day_race_across_est_offset(self):
        race = fetch_races.normalize_event(FIXTURE[75191])
        self.assertEqual(race["startDate"], "2026-11-07")
        self.assertEqual(race["endDate"], "2026-11-08")
        self.assertEqual(race["days"], 2)

    def test_null_reg_close_is_valid_record(self):
        race = fetch_races.normalize_event(FIXTURE[73951])
        self.assertIsNone(race["regClose"])
        self.assertEqual(race["regOpen"], "2026-08-01T00:01:00-04:00")
        self.assertEqual(race["startDate"], "2026-09-12")

    def test_missing_lat_lng_is_valid_record(self):
        race = fetch_races.normalize_event(FIXTURE[76849])
        self.assertIsNone(race["lat"])
        self.assertIsNone(race["lng"])
        self.assertEqual(race["startDate"], "2026-09-13")


class ExclusionTest(unittest.TestCase):
    def test_camp_with_cyclocross_type_is_excluded(self):
        self.assertIsNotNone(fetch_races.exclusion_reason(FIXTURE[76626]))

    def test_regional_type_tags_are_kept(self):
        # ['Cyclocross', 'NEBRA'] must not trip the keyword filter
        self.assertIsNone(fetch_races.exclusion_reason(FIXTURE[75277]))

    def test_season_long_listing_is_excluded_and_reported(self):
        # River Valley CX Series spans 70 days
        self.assertIn("70 days", fetch_races.exclusion_reason(FIXTURE[77173]))
        races, excluded = fetch_races.normalize_season(dict(FIXTURE))
        excluded_names = [name for name, _ in excluded]
        self.assertIn("River Valley CX Series", excluded_names)
        self.assertIn("Cycle-Smart Cyclocross Camp", excluded_names)

    def test_two_day_race_weekend_is_kept(self):
        self.assertIsNone(fetch_races.exclusion_reason(FIXTURE[77025]))


class FetchSeasonTest(unittest.TestCase):
    def test_duplicate_event_id_across_windows_appears_once(self):
        windows = list(fetch_races.season_windows())
        per_window = {windows[0][0]: [FIXTURE[75277]], windows[1][0]: [FIXTURE[75277]]}

        def fake_fetch(start, end):
            return per_window.get(start, [])

        with mock.patch.object(fetch_races, "fetch_window", side_effect=fake_fetch), \
             mock.patch.object(fetch_races.time, "sleep"):
            events, failures = fetch_races.fetch_season()
        self.assertEqual(list(events), [75277])
        self.assertEqual(failures, [])

    def test_http_failure_on_one_window_continues(self):
        windows = list(fetch_races.season_windows())
        failing_start = windows[1][0]

        def fake_fetch(start, end):
            if start == failing_start:
                raise urllib.error.URLError("boom")
            return [FIXTURE[75277]] if start == windows[0][0] else []

        with mock.patch.object(fetch_races, "fetch_window", side_effect=fake_fetch), \
             mock.patch.object(fetch_races.time, "sleep"):
            events, failures = fetch_races.fetch_season()
        self.assertEqual(list(events), [75277])
        self.assertEqual([start for start, _ in failures], [failing_start])


class EnrichDriveTimesTest(unittest.TestCase):
    def _race(self, event_id=75277):
        return fetch_races.normalize_event(FIXTURE[event_id])

    def test_cached_osrm_result_is_not_rerequested(self):
        race = self._race()
        cache = {str(race["id"]): {"minutes": 165, "miles": 120, "source": "osrm"}}
        with mock.patch.object(fetch_races, "fetch_drive_time") as fetch_mock:
            fetch_races.enrich_drive_times([race], cache)
        fetch_mock.assert_not_called()
        self.assertEqual(race["driveMinutes"], 165)
        self.assertEqual(race["driveSource"], "osrm")

    def test_missing_lat_lng_yields_null_drive_time(self):
        race = self._race(76849)  # synthesized no-geo event
        cache = {}
        with mock.patch.object(fetch_races, "fetch_drive_time") as fetch_mock:
            fetch_races.enrich_drive_times([race], cache)
        fetch_mock.assert_not_called()
        self.assertIsNone(race["driveMinutes"])
        self.assertIsNone(race["driveMiles"])
        self.assertIsNone(race["driveSource"])
        self.assertEqual(cache, {})

    def test_osrm_failure_falls_back_to_haversine_estimate(self):
        race = self._race()  # Rocky Hill CT, ~100 straight-line miles from Brooklyn
        cache = {}
        with mock.patch.object(fetch_races, "fetch_drive_time",
                               side_effect=urllib.error.URLError("down")), \
             mock.patch.object(fetch_races.time, "sleep"):
            fetch_races.enrich_drive_times([race], cache)
        self.assertEqual(race["driveSource"], "estimate")
        self.assertTrue(60 <= race["driveMiles"] <= 130, race["driveMiles"])
        exact_miles = fetch_races.haversine_miles(
            fetch_races.ORIGIN_LAT, fetch_races.ORIGIN_LNG, race["lat"], race["lng"])
        self.assertEqual(race["driveMiles"], round(exact_miles))
        self.assertEqual(race["driveMinutes"],
                         round(exact_miles / fetch_races.ESTIMATE_SPEED_MPH * 60))
        self.assertEqual(cache[str(race["id"])]["source"], "estimate")

    def test_cached_estimate_is_retried_and_upgraded(self):
        race = self._race()
        cache = {str(race["id"]): {"minutes": 120, "miles": 90, "source": "estimate"}}
        with mock.patch.object(fetch_races, "fetch_drive_time",
                               return_value=(150.4, 118.6)), \
             mock.patch.object(fetch_races.time, "sleep"):
            fetch_races.enrich_drive_times([race], cache)
        self.assertEqual(race["driveSource"], "osrm")
        self.assertEqual(race["driveMinutes"], 150)
        self.assertEqual(cache[str(race["id"])]["source"], "osrm")


class WriteRaceDataTest(unittest.TestCase):
    def test_output_is_valid_js_with_generated_at_and_date_sorted_events(self):
        import tempfile
        races, _ = fetch_races.normalize_season(dict(FIXTURE))
        for race in races:
            race.update(driveMinutes=None, driveMiles=None, driveSource=None)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "race-data.js"
            fetch_races.write_race_data(races, out)
            source = out.read_text()
        match = re.search(r"^const RACE_DATA = (\{.*\});$", source, re.S | re.M)
        self.assertIsNotNone(match, "expected a RACE_DATA assignment")
        data = json.loads(match.group(1))
        self.assertIn("generatedAt", data)
        self.assertEqual(data["origin"]["label"], "Brooklyn, NY")
        dates = [event["startDate"] for event in data["events"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(data["events"]), len(races))


class SeasonWindowsTest(unittest.TestCase):
    def test_windows_tile_the_season_by_month(self):
        windows = list(fetch_races.season_windows(date(2026, 8, 1), date(2027, 1, 31)))
        self.assertEqual(windows[0], (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(windows[-1], (date(2027, 1, 1), date(2027, 1, 31)))
        self.assertEqual(len(windows), 6)
        # contiguous, no gaps or overlaps
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            self.assertEqual((next_start - prev_end).days, 1)


if __name__ == "__main__":
    unittest.main()
