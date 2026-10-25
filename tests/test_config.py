import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from niri_live_wallpaper import config, paths


class ConfigFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / "config.json"
        patcher = mock.patch.object(paths, "CONFIG_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def write(self, data):
        self.file.write_text(json.dumps(data))

    def test_missing_file_gives_current_version(self):
        self.assertEqual(config.load(), {"version": config.CURRENT_VERSION})

    def test_corrupt_file_falls_back_to_defaults(self):
        self.file.write_text("{not json")
        with self.assertLogs("niri_live_wallpaper.config", "ERROR"):
            self.assertEqual(config.load(), {"version": config.CURRENT_VERSION})

    def test_v1_custom_hours_become_minutes(self):
        self.write({"cycle": {"mode": "custom", "hours": 5}, "wallpaper": "a.mp4"})
        cfg = config.load()
        self.assertEqual(cfg["cycle"], {"mode": "custom", "minutes": 300})
        self.assertEqual(cfg["wallpaper"], "a.mp4")
        self.assertEqual(cfg["version"], 2)

    def test_v1_existing_minutes_win_over_hours(self):
        self.write({"cycle": {"mode": "custom", "hours": 5, "minutes": 90}})
        self.assertEqual(config.load()["cycle"], {"mode": "custom", "minutes": 90})

    def test_newer_version_is_left_alone(self):
        self.write({"version": 99, "future": True})
        with self.assertLogs("niri_live_wallpaper.config", "WARNING"):
            self.assertEqual(config.load(), {"version": 99, "future": True})

    def test_update_merges_and_none_removes(self):
        self.write({"wallpaper": "a.mp4", "ask_fps": False})
        cfg = config.update(wallpaper=None, last_change=1.5)
        self.assertEqual(cfg, {"ask_fps": False, "last_change": 1.5, "version": 2})
        self.assertEqual(json.loads(self.file.read_text()), cfg)  # persisted, migrated

    def test_forget_video(self):
        self.write({"videos": {"a.mp4": {"fps": 30}, "b.mp4": {}}})
        config.forget_video("a.mp4")
        self.assertEqual(config.load()["videos"], {"b.mp4": {}})

    def test_defaults(self):
        self.assertTrue(config.ask_fps({}))
        self.assertFalse(config.ask_screens({}))


class ScreenSettingsTest(unittest.TestCase):
    cfg = {"videos": {"v.mp4": {
        "fps": 30, "scale": 75,
        "screens": {"eDP-1": {"fps": 24}, "HDMI-A-1": {"scale": 100, "fps": None}},
    }}}

    def test_override_both(self):
        self.assertEqual(config.screen_settings(self.cfg, "v.mp4", "HDMI-A-1"), (None, 100))

    def test_override_one_inherits_other(self):
        self.assertEqual(config.screen_settings(self.cfg, "v.mp4", "eDP-1"), (24, 75))

    def test_unknown_screen_uses_all_screens(self):
        self.assertEqual(config.screen_settings(self.cfg, "v.mp4", "DP-9"), (30, 75))

    def test_unknown_video_uses_defaults(self):
        self.assertEqual(config.screen_settings({}, "x.mp4", "eDP-1"), (None, 100))


if __name__ == "__main__":
    unittest.main()
