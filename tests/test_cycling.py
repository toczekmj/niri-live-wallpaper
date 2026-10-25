import unittest

from niri_live_wallpaper import cycling


class IntervalTextTest(unittest.TestCase):
    def test_parse_valid(self):
        cases = {"1:30": 90, "0:45": 45, "2": 120, ":45": 45, "0:01": 1, "1:5": 65,
                 "24:00": 1440, "720:00": cycling.MAX_MINUTES}
        for text, minutes in cases.items():
            with self.subTest(text=text):
                self.assertEqual(cycling.parse_interval(text), minutes)

    def test_parse_invalid(self):
        for text in ["", "0:00", "1:60", "1:", "abc", "720:01", "1:2:3", "1:999"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                cycling.parse_interval(text)

    def test_format(self):
        self.assertEqual(cycling.format_interval(90), "1h 30m")
        self.assertEqual(cycling.format_interval(45), "45m")
        self.assertEqual(cycling.format_interval(120), "2h")


class ScheduleTest(unittest.TestCase):
    def test_interval_by_mode(self):
        self.assertIsNone(cycling.interval_minutes({}))
        self.assertIsNone(cycling.interval_minutes({"cycle": {"mode": "off", "minutes": 5}}))
        self.assertEqual(cycling.interval_minutes({"cycle": {"mode": "daily", "minutes": 5}}), 1440)
        self.assertEqual(cycling.interval_minutes({"cycle": {"mode": "custom", "minutes": 5}}), 5)

    def test_labels(self):
        self.assertEqual(cycling.label({}), "off")
        self.assertEqual(cycling.label({"cycle": {"mode": "weekly"}}), "every week")
        self.assertEqual(cycling.label({"cycle": {"mode": "custom", "minutes": 90}}), "every 1h 30m")

    def test_is_due(self):
        cfg = {"cycle": {"mode": "hourly"}, "last_change": 1000}
        self.assertFalse(cycling.is_due(cfg, 1000 + 3599, video_count=3))
        self.assertTrue(cycling.is_due(cfg, 1000 + 3600, video_count=3))
        self.assertFalse(cycling.is_due(cfg, 1000 + 3600, video_count=1))  # nothing to switch to
        self.assertFalse(cycling.is_due({}, 10**10, video_count=3))  # off

    def test_seconds_until_next(self):
        cfg = {"cycle": {"mode": "custom", "minutes": 2}, "last_change": 100}
        self.assertEqual(cycling.seconds_until_next(cfg, 130), 90)
        self.assertIsNone(cycling.seconds_until_next({}, 130))

    def test_next_video_wraps(self):
        videos = ["a", "b", "c"]
        self.assertEqual(cycling.next_video(videos, "a"), "b")
        self.assertEqual(cycling.next_video(videos, "c"), "a")
        self.assertEqual(cycling.next_video(videos, "deleted"), "a")
        self.assertEqual(cycling.next_video(videos, None), "a")

    def test_preset_keeps_last_custom_interval(self):
        cfg = {"cycle": {"mode": "custom", "minutes": 90}}
        self.assertEqual(cycling.new_cycle_settings(cfg, "daily", None), {"mode": "daily", "minutes": 90})
        self.assertEqual(cycling.new_cycle_settings(cfg, "custom", 15), {"mode": "custom", "minutes": 15})
        self.assertEqual(cycling.new_cycle_settings({}, "hourly", None)["minutes"],
                         cycling.DEFAULT_CUSTOM_MINUTES)


if __name__ == "__main__":
    unittest.main()
