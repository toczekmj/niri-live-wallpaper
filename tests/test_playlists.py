import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

from niri_live_wallpaper import config, library, paths, playlists, variants
from niri_live_wallpaper.niri import Output

LAPTOP = Output("eDP-1", 1920, 1200)


class WithConfigFile(unittest.TestCase):
    """A real config file in a temporary directory, and an empty library next to it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        for attribute, value in (("CONFIG_FILE", root / "config.json"), ("VIDEO_DIR", root / "videos"),
                                 ("FRAME_DIR", root / "frames"), ("OPTIMIZED_DIR", root / "optimized")):
            patcher = mock.patch.object(paths, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        paths.VIDEO_DIR.mkdir()

    def write(self, data):
        paths.CONFIG_FILE.write_text(json.dumps(data))

    def touch(self, *names):
        for name in names:
            (paths.VIDEO_DIR / name).write_bytes(b"x")


class NamesTest(unittest.TestCase):
    CFG: ClassVar[dict[str, Any]] = {"playlists": {"Chill": {"items": {}}, "calm": {"items": {}}}}

    def test_names_are_trimmed_and_spaces_collapsed(self):
        self.assertEqual(playlists.clean_name(self.CFG, "  My   mix "), "My mix")

    def test_empty_and_too_long_names_are_refused(self):
        with self.assertRaises(ValueError):
            playlists.clean_name(self.CFG, "   ")
        with self.assertRaises(ValueError):
            playlists.clean_name(self.CFG, "x" * (playlists.NAME_MAX + 1))

    def test_names_are_unique_ignoring_case(self):
        with self.assertRaises(ValueError):
            playlists.clean_name(self.CFG, "CHILL")

    def test_a_playlist_may_keep_or_re_case_its_own_name_when_renamed(self):
        self.assertEqual(playlists.clean_name(self.CFG, "CHILL", renaming="Chill"), "CHILL")

    def test_names_are_sorted_ignoring_case(self):
        self.assertEqual(playlists.names(self.CFG), ["calm", "Chill"])


class OperationsTest(unittest.TestCase):
    def cfg(self):
        return {
            "playlist": "A",
            "videos": {"x.png": {"fit": "blur"}, "y.mp4": {"fps": 30}},
            "playlists": {"A": {"items": {"x.png": {"fit": "fit"}}}, "B": {"items": {}}},
        }

    def test_create_makes_an_empty_playlist(self):
        changes = playlists.create(self.cfg(), "C")
        self.assertEqual(changes["playlists"]["C"], {"items": {}})
        self.assertEqual(set(changes["playlists"]), {"A", "B", "C"})

    def test_rename_keeps_files_settings_and_activity(self):
        changes = playlists.rename(self.cfg(), "A", "Z")
        self.assertEqual(changes["playlists"]["Z"], {"items": {"x.png": {"fit": "fit"}}})
        self.assertNotIn("A", changes["playlists"])
        self.assertEqual(changes["playlist"], "Z")

    def test_renaming_another_playlist_leaves_the_active_one(self):
        self.assertNotIn("playlist", playlists.rename(self.cfg(), "B", "Z"))

    def test_deleting_the_active_playlist_goes_back_to_all_files(self):
        changes = playlists.delete(self.cfg(), "A")
        self.assertEqual(set(changes["playlists"]), {"B"})
        self.assertIsNone(changes["playlist"])

    def test_deleting_another_playlist_keeps_the_active_one(self):
        self.assertNotIn("playlist", playlists.delete(self.cfg(), "B"))

    def test_adding_copies_the_library_settings(self):
        items = playlists.add(self.cfg(), "B", ["x.png", "y.mp4"])["playlists"]["B"]["items"]
        self.assertEqual(items, {"x.png": {"fit": "blur"}, "y.mp4": {"fps": 30}})

    def test_the_copy_is_independent_of_the_library_settings(self):
        cfg = self.cfg()
        changes = playlists.add(cfg, "B", ["y.mp4"])
        changes["playlists"]["B"]["items"]["y.mp4"]["fps"] = 12
        self.assertEqual(cfg["videos"]["y.mp4"], {"fps": 30})

    def test_adding_a_file_never_asked_about_keeps_it_that_way(self):
        items = playlists.add(self.cfg(), "B", ["new.png"])["playlists"]["B"]["items"]
        self.assertEqual(items, {"new.png": None})

    def test_adding_a_file_already_in_the_playlist_keeps_its_playlist_settings(self):
        items = playlists.add(self.cfg(), "A", ["x.png"])["playlists"]["A"]["items"]
        self.assertEqual(items, {"x.png": {"fit": "fit"}})

    def test_removing_drops_the_file_and_its_playlist_settings_only(self):
        cfg = self.cfg()
        changes = playlists.remove(cfg, "A", ["x.png", "not-there.png"])
        self.assertEqual(changes["playlists"]["A"]["items"], {})
        self.assertEqual(cfg["videos"]["x.png"], {"fit": "blur"})  # the library is untouched

    def test_operations_do_not_modify_the_config_they_are_given(self):
        cfg = self.cfg()
        before = json.dumps(cfg)
        playlists.add(cfg, "B", ["x.png"])
        playlists.remove(cfg, "A", ["x.png"])
        playlists.rename(cfg, "A", "Z")
        playlists.delete(cfg, "A")
        self.assertEqual(json.dumps(cfg), before)

    def test_first_to_play_is_the_first_existing_file(self):
        cfg = {"playlist": "A", "playlists": {"A": {"items": {"b.png": None, "a.png": None, "gone.png": None}}}}
        self.assertEqual(playlists.first_to_play(cfg, ["a.png", "b.png"]), "a.png")
        self.assertEqual(playlists.first_to_play(cfg, ["b.png"]), "b.png")
        self.assertIsNone(playlists.first_to_play(cfg, []))
        self.assertIsNone(playlists.first_to_play({"playlists": cfg["playlists"]}, ["a.png"]))


class CycleTest(unittest.TestCase):
    """Every playlist has its own cycle; "all files" has the global one."""

    def cfg(self, active=None):
        cfg = {"cycle": {"mode": "daily", "minutes": 90},
               "playlists": {"A": {"items": {}, "cycle": {"mode": "hourly", "minutes": 45}},
                             "B": {"items": {}}}}
        if active:
            cfg["playlist"] = active
        return cfg

    def test_the_cycle_follows_the_active_playlist(self):
        self.assertEqual(config.cycle_settings(self.cfg()), {"mode": "daily", "minutes": 90})
        self.assertEqual(config.cycle_settings(self.cfg("A")), {"mode": "hourly", "minutes": 45})

    def test_a_playlist_without_a_cycle_does_not_cycle(self):
        from niri_live_wallpaper import cycling
        self.assertIsNone(cycling.interval_minutes(self.cfg("B")))
        self.assertEqual(cycling.interval_minutes(self.cfg("A")), 60)
        self.assertEqual(cycling.interval_minutes(self.cfg()), 24 * 60)

    def test_labels_and_the_remembered_custom_interval_are_per_playlist(self):
        from niri_live_wallpaper import cycling
        self.assertEqual(cycling.label(self.cfg("A")), "every hour")
        self.assertEqual(cycling.saved_custom_minutes(self.cfg("A")), 45)
        self.assertEqual(cycling.saved_custom_minutes(self.cfg("B")), cycling.DEFAULT_CUSTOM_MINUTES)

    def test_the_countdown_uses_the_playlists_interval(self):
        from niri_live_wallpaper import cycling
        cfg = {**self.cfg("A"), "last_change": 1000}
        self.assertEqual(cycling.seconds_until_next(cfg, 1000), 3600)
        self.assertEqual(cycling.seconds_until_next({**cfg, "playlist": None}, 1000), 24 * 3600)

    def test_changing_the_cycle_changes_only_the_active_context(self):
        cfg = self.cfg("B")
        changes = config.cycle_changes(cfg, {"mode": "weekly", "minutes": 60})
        self.assertEqual(changes["playlists"]["B"]["cycle"], {"mode": "weekly", "minutes": 60})
        self.assertEqual(changes["playlists"]["A"]["cycle"], {"mode": "hourly", "minutes": 45})
        self.assertNotIn("cycle", changes)
        self.assertNotIn("cycle", cfg["playlists"]["B"])  # the config given is not modified
        self.assertEqual(config.cycle_changes(self.cfg(), {"mode": "off", "minutes": 60}),
                         {"cycle": {"mode": "off", "minutes": 60}})

    def test_renaming_keeps_the_cycle_and_deleting_drops_it(self):
        renamed = playlists.rename(self.cfg("A"), "A", "Z")
        self.assertEqual(renamed["playlists"]["Z"]["cycle"], {"mode": "hourly", "minutes": 45})
        self.assertNotIn("A", playlists.delete(self.cfg("A"), "A")["playlists"])

    def test_a_new_playlist_starts_without_a_cycle(self):
        self.assertNotIn("cycle", playlists.create(self.cfg(), "C")["playlists"]["C"])

    def test_a_missing_active_playlist_falls_back_to_the_global_cycle(self):
        self.assertEqual(config.cycle_settings({**self.cfg(), "playlist": "gone"}),
                         {"mode": "daily", "minutes": 90})


class ShareWithLibraryTest(unittest.TestCase):
    def test_files_set_up_in_a_playlist_give_the_library_the_same_settings(self):
        cfg = {"videos": {"old.png": {"fit": "stretch"}},
               "playlists": {"P": {"items": {"new.png": {"fit": "blur"}, "old.png": {"fit": "fit"}, "asked.png": None}}}}
        videos = playlists.share_with_library(cfg, "P", ["new.png", "old.png", "asked.png"])["videos"]
        self.assertEqual(videos, {"old.png": {"fit": "stretch"}, "new.png": {"fit": "blur"}})

    def test_the_library_copy_is_independent(self):
        cfg = {"playlists": {"P": {"items": {"new.png": {"fit": "blur"}}}}}
        videos = playlists.share_with_library(cfg, "P", ["new.png"])["videos"]
        videos["new.png"]["fit"] = "fit"
        self.assertEqual(cfg["playlists"]["P"]["items"]["new.png"], {"fit": "blur"})


class SettingsInContextTest(WithConfigFile):
    """photo1.png fills in one playlist and has black bars in another."""

    def setUp(self):
        super().setUp()
        self.write({"videos": {"p.png": {"fit": "blur"}},
                    "playlists": {"one": {"items": {"p.png": {}}}, "two": {"items": {"p.png": {"fit": "fit"}}}}})

    def entry(self, playlist):
        cfg = config.load()
        if playlist:
            cfg["playlist"] = playlist
        return config.video_entry(cfg, "p.png")

    def test_each_context_has_its_own_settings(self):
        self.assertEqual(self.entry(None), {"fit": "blur"})
        self.assertEqual(self.entry("one"), {})
        self.assertEqual(self.entry("two"), {"fit": "fit"})

    def test_a_file_outside_the_active_playlist_uses_the_library_settings(self):
        cfg = {**config.load(), "playlist": "one"}
        self.assertEqual(config.video_entry(cfg, "other.png"), config.load()["videos"].get("other.png"))

    def test_saving_in_a_playlist_leaves_the_others_alone(self):
        config.update(playlist="two")
        config.save_video_entry("p.png", {"fit": "stretch"})
        config.update(playlist=None)
        cfg = config.load()
        self.assertEqual(cfg["videos"]["p.png"], {"fit": "blur"})
        self.assertEqual(cfg["playlists"]["one"]["items"]["p.png"], {})
        self.assertEqual(cfg["playlists"]["two"]["items"]["p.png"], {"fit": "stretch"})

    def test_saving_with_no_playlist_changes_only_the_library(self):
        config.save_video_entry("p.png", {"fit": "center"})
        cfg = config.load()
        self.assertEqual(cfg["videos"]["p.png"], {"fit": "center"})
        self.assertEqual(cfg["playlists"]["two"]["items"]["p.png"], {"fit": "fit"})

    def test_forgetting_in_a_playlist_means_never_asked_there(self):
        config.update(playlist="two")
        config.forget_video("p.png")
        cfg = config.load()
        self.assertIsNone(config.video_entry(cfg, "p.png"))
        self.assertEqual(cfg["videos"]["p.png"], {"fit": "blur"})
        self.assertIn("p.png", cfg["playlists"]["two"]["items"])  # still in the playlist

    def test_effective_fit_follows_the_active_playlist(self):
        cfg = config.load()
        self.assertEqual(config.screen_fit(cfg, "p.png", "eDP-1"), ("blur", "center"))
        self.assertEqual(config.screen_fit({**cfg, "playlist": "two"}, "p.png", "eDP-1"), ("fit", "center"))
        self.assertEqual(config.screen_fit({**cfg, "playlist": "one"}, "p.png", "eDP-1"), ("fill", "center"))

    def test_entries_of_lists_every_context(self):
        self.assertEqual(config.entries_of(config.load(), "p.png"), [{"fit": "blur"}, {}, {"fit": "fit"}])

    def test_purge_removes_the_file_everywhere(self):
        config.purge_video("p.png")
        cfg = config.load()
        self.assertNotIn("p.png", cfg["videos"])
        self.assertEqual([cfg["playlists"][p]["items"] for p in ("one", "two")], [{}, {}])

    def test_a_deleted_active_playlist_is_ignored(self):
        self.assertIsNone(config.active_playlist({"playlist": "gone", "playlists": {}}))


class ActiveListTest(WithConfigFile):
    def setUp(self):
        super().setUp()
        self.touch("b.png", "a.mp4", "c.png")
        self.write({"playlists": {"mix": {"items": {"c.png": None, "a.mp4": None, "gone.png": None}}}})

    def test_no_playlist_lists_the_whole_library(self):
        self.assertEqual(library.list_active(config.load()), ["a.mp4", "b.png", "c.png"])

    def test_a_playlist_lists_its_files_that_exist(self):
        self.assertEqual(library.list_active({**config.load(), "playlist": "mix"}), ["a.mp4", "c.png"])

    def test_deleting_a_file_takes_it_out_of_playlists_too(self):
        config.update(**playlists.add(config.load(), "mix", ["b.png"]))
        library.delete_video("b.png")
        self.assertNotIn("b.png", config.load()["playlists"]["mix"]["items"])
        self.assertFalse((paths.VIDEO_DIR / "b.png").exists())


class CacheTest(WithConfigFile):
    def test_pruning_keeps_the_copies_every_playlist_needs(self):
        from niri_live_wallpaper.media import VideoInfo
        info = VideoInfo(width=3840, height=2160, fps=30, duration=5, has_audio=False)
        cfg = {"videos": {"v.mp4": {"fit": "fit"}}, "playlists": {"p": {"items": {"v.mp4": {"fit": "stretch"}}}}}
        self.touch("v.mp4")
        folder = paths.OPTIMIZED_DIR / "v.mp4"
        folder.mkdir(parents=True)
        for filename in ("1920x1080@src-fit.mp4", "1920x1200@src-stretch.mp4", "1920x1200@src-blur.mp4"):
            (folder / filename).write_bytes(b"x")
        with mock.patch("niri_live_wallpaper.media.probe", return_value=info):
            variants.prune("v.mp4", variants.jobs_everywhere(cfg, "v.mp4", [LAPTOP]))
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ["1920x1080@src-fit.mp4", "1920x1200@src-stretch.mp4"])

    def test_jobs_follow_the_active_playlist(self):
        cfg = {"playlist": "p", "videos": {"v.mp4": {"fit": "fit"}},
               "playlists": {"p": {"items": {"v.mp4": {"fit": "stretch"}}}}}
        self.assertEqual(variants.jobs_for(cfg, "v.mp4", [LAPTOP])[0].fit_mode, "stretch")
        self.assertEqual(variants.jobs_for({**cfg, "playlist": None}, "v.mp4", [LAPTOP])[0].fit_mode, "fit")


if __name__ == "__main__":
    unittest.main()
