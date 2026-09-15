import importlib.util
import io
import json
from pathlib import Path
from unittest import mock
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_events_colors", ROOT / "fetch-events.py")
fetch_events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_events)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FetchGoogleCalendarColorsTests(unittest.TestCase):
    def fetch(self, pages, token="fake-token"):
        requests = []

        def fake_urlopen(req, timeout=None):
            requests.append(req.full_url)
            page = pages[len(requests) - 1]
            if isinstance(page, Exception):
                raise page
            return _FakeResponse(json.dumps(page).encode("utf-8"))

        with mock.patch.object(fetch_events, "get_google_access_token", return_value=token), \
             mock.patch.object(fetch_events.urllib.request, "urlopen", side_effect=fake_urlopen):
            return fetch_events.fetch_google_calendar_colors(), requests

    def test_collects_colors_across_pages_and_aliases_primary(self):
        pages = [
            {"items": [{"id": "me@example.com", "backgroundColor": "#ff7537", "primary": True},
                       {"id": "team@group.calendar.google.com", "backgroundColor": "#16a765"}],
             "nextPageToken": "p2"},
            {"items": [{"id": "occ@example.org", "backgroundColor": "#cd74e6"}, {"id": "no-color@example.org"}]},
        ]
        colors, requests = self.fetch(pages)

        self.assertEqual(colors, {
            "me@example.com": "#ff7537",
            "primary": "#ff7537",
            "team@group.calendar.google.com": "#16a765",
            "occ@example.org": "#cd74e6",
        })
        self.assertIn("/users/me/calendarList?", requests[0])
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(requests[1]).query)["pageToken"], ["p2"])

    def test_no_login_means_no_request(self):
        colors, requests = self.fetch([], token=None)
        self.assertEqual((colors, requests), ({}, []))

    def test_network_failure_falls_back_to_config_colors(self):
        colors, _ = self.fetch([OSError("offline")])
        self.assertEqual(colors, {})


class ApplyGoogleColorsTests(unittest.TestCase):
    COLORS = {"work@example.com": "#16a765", "primary": "#ff7537"}

    def test_google_calendars_take_google_color(self):
        cals = [
            {"name": "Work", "googleCalendarId": "work@example.com", "color": "#000000"},
            {"name": "Me", "googleCalendarId": "primary", "color": "#000000"},
            {"name": "Feed", "url": "https://example.com/cal.ics", "color": "#123456"},
        ]
        out = fetch_events.apply_google_colors(cals, self.COLORS)
        self.assertEqual([c["color"] for c in out], ["#16a765", "#ff7537", "#123456"])
        self.assertEqual(cals[0]["color"], "#000000", "config entries must not be mutated")

    def test_sync_color_false_keeps_config_color(self):
        cals = [{"name": "Work", "googleCalendarId": "work@example.com", "color": "#000000", "syncColor": False}]
        self.assertEqual(fetch_events.apply_google_colors(cals, self.COLORS)[0]["color"], "#000000")

    def test_calendar_missing_from_google_keeps_config_color(self):
        cals = [{"name": "Gone", "googleCalendarId": "gone@example.com", "color": "#abcdef"}]
        self.assertEqual(fetch_events.apply_google_colors(cals, self.COLORS)[0]["color"], "#abcdef")

    def test_merged_group_uses_synced_color_of_namesake(self):
        cals = [
            {"name": "Sidekechs", "googleCalendarId": "primary", "color": "#000000", "group": "Enovara"},
            {"name": "Enovara", "googleCalendarId": "work@example.com", "color": "#000000", "group": "Enovara"},
        ]
        groups = fetch_events.calendar_groups(fetch_events.apply_google_colors(cals, self.COLORS))
        self.assertEqual(groups["Sidekechs"], ("Enovara", "#16a765"))


if __name__ == "__main__":
    unittest.main()
