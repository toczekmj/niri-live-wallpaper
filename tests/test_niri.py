import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from niri_live_wallpaper import niri, paths


class ParseOutputsTest(unittest.TestCase):
    def test_modes_rotation_and_disabled(self):
        data = {
            "eDP-1": {"current_mode": 0, "modes": [{"width": 1920, "height": 1200}],
                      "logical": {"transform": "Normal"}},
            "DP-1": {"current_mode": 1, "modes": [{"width": 1, "height": 1},
                                                  {"width": 2560, "height": 1440}],
                     "logical": {"transform": "_90"}},
            "HDMI-A-2": {"current_mode": None, "modes": []},  # disabled
        }
        self.assertEqual(niri.parse_outputs(data), [
            niri.Output("DP-1", 1440, 2560),
            niri.Output("eDP-1", 1920, 1200),
        ])


class LayerRuleTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / "sub").mkdir()

    def write(self, name, text):
        (self.root / name).write_text(text)

    def test_rule_in_config_kdl_multiline_any_order(self):
        self.write("config.kdl", 'layer-rule {\n  place-within-backdrop true\n'
                                 '  match namespace="^mpvpaper$"\n}\n')
        self.assertTrue(niri.layer_rule_present(self.root / "config.kdl"))

    def test_one_line_rule_as_shown_in_the_app(self):
        self.write("config.kdl", niri.LAYER_RULE)
        self.assertTrue(niri.layer_rule_present(self.root / "config.kdl"))

    def test_rule_in_nested_include_relative_to_including_file(self):
        self.write("config.kdl", 'include "sub/a.kdl"\n')
        self.write("sub/a.kdl", 'include "b.kdl"\n')
        self.write("sub/b.kdl", niri.LAYER_RULE)
        self.assertTrue(niri.layer_rule_present(self.root / "config.kdl"))

    def test_rule_in_file_that_is_not_included_does_not_count(self):
        self.write("config.kdl", '// include "orphan.kdl"\n')
        self.write("orphan.kdl", niri.LAYER_RULE)
        self.assertFalse(niri.layer_rule_present(self.root / "config.kdl"))

    def test_commented_out_rule_does_not_count(self):
        self.write("config.kdl", "// " + niri.LAYER_RULE)
        self.assertFalse(niri.layer_rule_present(self.root / "config.kdl"))

    def test_include_loop_terminates(self):
        self.write("config.kdl", 'include "sub/a.kdl"\n')
        self.write("sub/a.kdl", 'include "../config.kdl"\n')
        self.assertFalse(niri.layer_rule_present(self.root / "config.kdl"))

    def test_missing_config(self):
        self.assertFalse(niri.layer_rule_present(self.root / "nope" / "config.kdl"))


class BackgroundTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.config = Path(self.dir.name) / "config.kdl"

    def transparent(self, text):
        self.config.write_text(text)
        return niri.background_transparent(self.config)

    def test_default_is_opaque(self):
        self.assertFalse(self.transparent("layout { gaps 8; }"))

    def test_transparent(self):
        self.assertTrue(self.transparent(niri.TRANSPARENT_BACKGROUND))
        self.assertTrue(self.transparent('layout {\n    background-color "#00000000"\n}'))

    def test_one_opaque_value_anywhere_counts(self):
        # e.g. a per-output override that hides the video on that screen
        self.assertFalse(self.transparent(
            niri.TRANSPARENT_BACKGROUND + '\noutput "eDP-1" { layout { background-color "#262626"; } }'))

    def test_commented_out_value_is_ignored(self):
        self.assertFalse(self.transparent('// layout { background-color "transparent"; }'))

    def test_other_color_settings_are_not_confused(self):
        self.assertFalse(self.transparent('overview { backdrop-color "transparent"; }'))

    def test_see_through_colors(self):
        for color in ["transparent", "#12345600", "#1234567f", "#1238", "rgba(0, 0, 0, 0)",
                      "rgba(0 0 0 / 50%)"]:
            with self.subTest(color=color):
                self.assertTrue(niri.is_see_through(color))
        for color in ["#262626", "#262626ff", "#123f", "red", "rgba(0, 0, 0, 1)", "rgb(0,0,0)"]:
            with self.subTest(color=color):
                self.assertFalse(niri.is_see_through(color))


class ConfigFileTest(unittest.TestCase):
    def test_niri_config_variable_wins(self):
        with mock.patch.dict(os.environ, {"NIRI_CONFIG": "/somewhere/niri.kdl"}):
            self.assertEqual(niri.config_file(), Path("/somewhere/niri.kdl"))

    def test_empty_variable_is_ignored(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"NIRI_CONFIG": ""}), \
                mock.patch.object(paths, "NIRI_CONFIG_DIR", Path(d)):
            (Path(d) / "config.kdl").write_text("")
            self.assertEqual(niri.config_file(), Path(d) / "config.kdl")


class LayersTest(unittest.TestCase):
    def test_only_foreign_background_surfaces(self):
        layers = [
            {"namespace": "mpvpaper", "output": "eDP-1", "layer": "Background"},
            {"namespace": "wallpaper", "output": "eDP-1", "layer": "Background"},
            {"namespace": "wallpaper", "output": "DP-1", "layer": "Background"},
            {"namespace": "dms:bar", "output": "eDP-1", "layer": "Top"},
        ]
        self.assertEqual(niri.parse_other_background_surfaces(layers), ["wallpaper"])


if __name__ == "__main__":
    unittest.main()
