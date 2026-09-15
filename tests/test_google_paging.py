import importlib.util
import io
import json
import os
from datetime import datetime
from pathlib import Path
from unittest import mock
import tempfile
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_events_paging", ROOT / "fetch-events.py")
fetch_events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_events)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _event(n, summary=True):
    item = {
        "id": f"evt_{n}",
        "start": {"dateTime": "2026-08-25T10:00:00Z"},
        "end": {"dateTime": "2026-08-25T11:00:00Z"},
    }
    if summary:
        item["summary"] = f"Meeting {n}"
    return item


class GoogleApiPagingTests(unittest.TestCase):
    CAL = {"name": "Work", "googleCalendarId": "primary"}
    START = datetime(2026, 8, 1)
    END = datetime(2026, 8, 31, 23, 59, 59)

    def fetch(self, pages):
        requests = []

        def fake_urlopen(req, timeout=None):
            requests.append(req.full_url)
            return _FakeResponse(json.dumps(pages[len(requests) - 1]).encode("utf-8"))

        with mock.patch.object(fetch_events, "get_google_access_token", return_value="fake-token"), \
             mock.patch.object(fetch_events.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = fetch_events.fetch_google_api_calendar(self.CAL, self.START, self.END)
        return result, requests

    def test_follows_next_page_token(self):
        pages = [
            {"items": [_event(1), _event(2)], "nextPageToken": "page-2"},
            {"items": [_event(3)]},
        ]
        result, requests = self.fetch(pages)

        self.assertEqual(result["status"], "ok")
        self.assertEqual([e["title"] for e in result["events"]], ["Meeting 1", "Meeting 2", "Meeting 3"])
        self.assertEqual(len(requests), 2)
        self.assertNotIn("pageToken", urllib.parse.urlparse(requests[0]).query)
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(requests[1]).query)["pageToken"], ["page-2"])

    def test_page_count_is_bounded(self):
        endless = [{"items": [_event(n)], "nextPageToken": f"p{n}"} for n in range(fetch_events.GOOGLE_MAX_PAGES + 5)]
        result, requests = self.fetch(endless)

        self.assertEqual(len(requests), fetch_events.GOOGLE_MAX_PAGES)
        self.assertEqual(result["count"], fetch_events.GOOGLE_MAX_PAGES)

    def test_free_busy_calendar_events_are_labelled_busy(self):
        result, _ = self.fetch([{"accessRole": "freeBusyReader", "items": [_event(1, summary=False)]}])
        self.assertEqual(result["events"][0]["title"], "Busy")

    def test_untitled_event_on_readable_calendar_keeps_untitled_label(self):
        result, _ = self.fetch([{"accessRole": "owner", "items": [_event(1, summary=False)]}])
        self.assertEqual(result["events"][0]["title"], "(Untitled Event)")


class SaveConfigStdinTests(unittest.TestCase):
    def test_save_config_accepts_indented_json_with_stdin_left_open(self):
        calendars = [{"name": "Work", "googleCalendarId": "primary", "enabled": False}]
        # The panel writes the payload plus a newline and never closes stdin,
        # so nothing after the JSON may be read.
        lines = iter(json.dumps(calendars, indent=2).splitlines(keepends=True))

        def readline():
            try:
                return next(lines)
            except StopIteration:
                raise AssertionError("read past the end of the payload; would block on a real pipe")

        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "calendars.json")
            with mock.patch.object(fetch_events, "CONFIG_PATH", config_path), \
                 mock.patch("sys.argv", ["fetch-events.py", "--save-config"]), \
                 mock.patch("sys.stdin.readline", side_effect=readline), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                 self.assertRaises(SystemExit) as cm:
                fetch_events.main()

            self.assertEqual(cm.exception.code, 0, stdout.getvalue())
            self.assertEqual(fetch_events.safe_load_json(config_path), calendars)


if __name__ == "__main__":
    unittest.main()
