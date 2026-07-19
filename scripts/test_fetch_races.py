#!/usr/bin/env python3
"""Tests for fetch_races.py. Run: python3 scripts/test_fetch_races.py

Fixture: scripts/fixtures/events_fixture.json — trimmed real events from the
live API (2026-07-18), plus two synthesized variants (null RegCloseDate,
missing lat/long)."""

import json
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
