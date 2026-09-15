import importlib.util
from datetime import datetime
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_events_groups", ROOT / "fetch-events.py")
fetch_events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_events)


def _event(calendar, title, hour, color="#000000"):
    return {
        "id": f"{calendar}-{title}-{hour}",
        "title": title,
        "calendar": calendar,
        "color": color,
        "date_key": "2026-09-15",
        "start_dt": datetime(2026, 9, 15, hour),
        "end_dt": datetime(2026, 9, 15, hour + 1),
        "all_day": False,
    }


def _status(name, count, color="#000000", status="ok", writable=False):
    return {"name": name, "color": color, "type": "google", "writable": writable, "status": status, "count": count}


CALENDARS = [
    {"name": "Sidekechs", "googleCalendarId": "primary", "color": "#ff7537", "group": "Enovara"},
    {"name": "OCC", "googleCalendarId": "occ", "color": "#cd74e6"},
    {"name": "Enovara", "googleCalendarId": "enovara", "color": "#16a765", "group": "Enovara"},
]


class CalendarGroupTests(unittest.TestCase):
    def test_group_takes_color_of_member_named_after_it(self):
        groups = fetch_events.calendar_groups(CALENDARS)
        self.assertEqual(groups, {"Sidekechs": ("Enovara", "#16a765"), "Enovara": ("Enovara", "#16a765")})

    def test_group_without_named_member_uses_first_member_color(self):
        cals = [{"name": "A", "color": "#111111", "group": "Work"}, {"name": "B", "color": "#222222", "group": "Work"}]
        self.assertEqual(fetch_events.calendar_groups(cals)["B"], ("Work", "#111111"))

    def test_no_groups_leaves_everything_untouched(self):
        events = [_event("OCC", "Core Meeting", 19)]
        statuses = [_status("OCC", 1)]
        self.assertEqual(fetch_events.merge_grouped_calendars([CALENDARS[1]], events, statuses), (events, statuses))

    def test_members_are_relabelled_and_keep_their_source(self):
        events = [_event("Sidekechs", "Standup", 9), _event("Enovara", "Discovery Call", 11), _event("OCC", "Core Meeting", 19)]
        merged, _ = fetch_events.merge_grouped_calendars(CALENDARS, events, [])

        self.assertEqual([(e["calendar"], e["color"], e.get("sourceCalendar")) for e in merged], [
            ("Enovara", "#16a765", "Sidekechs"),
            ("Enovara", "#16a765", "Enovara"),
            ("OCC", "#000000", None),
        ])
        self.assertEqual(events[0]["calendar"], "Sidekechs", "input events must not be mutated")

    def test_same_meeting_on_two_members_shows_once(self):
        events = [_event("Sidekechs", "Planning", 14), _event("Enovara", "Planning", 14), _event("Enovara", "Planning", 15)]
        merged, _ = fetch_events.merge_grouped_calendars(CALENDARS, events, [])
        self.assertEqual([(e["title"], e["start_dt"].hour) for e in merged], [("Planning", 14), ("Planning", 15)])

    def test_statuses_fold_into_one_chip_with_merged_count(self):
        events = [_event("Sidekechs", "Planning", 14), _event("Enovara", "Planning", 14), _event("Enovara", "Review", 16)]
        statuses = [_status("Sidekechs", 1, writable=True), _status("OCC", 5), _status("Enovara", 2, status="error: HTTP 500")]
        _, merged = fetch_events.merge_grouped_calendars(CALENDARS, events, statuses)

        self.assertEqual([s["name"] for s in merged], ["Enovara", "OCC"])
        enovara = merged[0]
        self.assertEqual(enovara["color"], "#16a765")
        self.assertEqual(enovara["members"], ["Sidekechs", "Enovara"])
        self.assertEqual(enovara["count"], 2)
        self.assertTrue(enovara["writable"])
        self.assertEqual(enovara["status"], "error: HTTP 500")


class CalendarIconTests(unittest.TestCase):
    def test_status_gets_its_calendar_glyph(self):
        cals = [{"name": "CommonSpirit", "icon": "", "iconFont": "CommonSpirit Mark"}, {"name": "OCC"}]
        statuses = [_status("CommonSpirit", 1), _status("OCC", 2)]
        out = fetch_events.attach_calendar_icons(cals, statuses)

        self.assertEqual((out[0]["icon"], out[0]["iconFont"]), ("", "CommonSpirit Mark"))
        self.assertNotIn("icon", out[1])
        self.assertNotIn("icon", statuses[0], "input statuses must not be mutated")

    def test_merged_group_uses_glyph_of_member_named_after_it(self):
        cals = [
            {"name": "Sidekechs", "group": "Enovara", "icon": "", "iconFont": "Enovara Submark"},
            {"name": "Enovara", "group": "Enovara", "icon": "", "iconFont": "Enovara Mark"},
        ]
        out = fetch_events.attach_calendar_icons(cals, [_status("Enovara", 3)])
        self.assertEqual((out[0]["icon"], out[0]["iconFont"]), ("", "Enovara Mark"))

    def test_merged_group_falls_back_to_any_member_glyph(self):
        cals = [
            {"name": "Sidekechs", "group": "Enovara", "icon": "", "iconFont": "Enovara Submark"},
            {"name": "Enovara", "group": "Enovara"},
        ]
        out = fetch_events.attach_calendar_icons(cals, [_status("Enovara", 3)])
        self.assertEqual(out[0]["iconFont"], "Enovara Submark")


if __name__ == "__main__":
    unittest.main()
