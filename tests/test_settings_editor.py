import unittest

from niri_live_wallpaper.media import VideoInfo
from niri_live_wallpaper.niri import Output
from niri_live_wallpaper.tui import style
from niri_live_wallpaper.tui.settings_editor import CANCEL, INHERIT, SettingsEditor

LAPTOP = Output("eDP-1", 1920, 1200)
ULTRAWIDE = Output("HDMI-A-1", 3440, 1440)
PHOTO = VideoInfo(width=3440, height=1440, fps=0, duration=0, has_audio=False, is_image=True)
CLIP = VideoInfo(width=3840, height=2160, fps=30, duration=5, has_audio=False)


class ScriptedDialogs:
    """Answers choose() with the next scripted index; records the options it was shown.
    wait_for_key() plays back `keys`."""

    def __init__(self, *answers, keys=()):
        self.answers = list(answers)
        self.keys = list(keys)
        self.shown = []

    def wait_for_key(self):
        return self.keys.pop(0)

    def choose(self, title, options, default=0, on_highlight=None):
        """The scripted answer is an index (Enter), None (Esc), or (highlights, answer): the
        highlight moves through those indices, then the answer."""
        self.shown.append((title, options, default))
        answer = self.answers.pop(0)
        if isinstance(answer, tuple):
            highlights, answer = answer
            for index in highlights:
                on_highlight(index)
        return answer


def editor(*answers, keys=()):
    dialogs = ScriptedDialogs(*answers, keys=keys)
    ed = SettingsEditor(None, dialogs, redraw=lambda: None)
    ed._draw = lambda *args: None  # no terminal here
    return ed, dialogs


class PickFitTest(unittest.TestCase):
    def test_black_bars_asks_nothing_more(self):
        ed, dialogs = editor(1)
        self.assertEqual(ed.pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center")), ("fit", "center"))
        self.assertEqual(len(dialogs.shown), 1)

    def test_fill_asks_which_part_to_keep_when_it_crops(self):
        ed, dialogs = editor(0, 1)  # fill, then "Left edge"
        self.assertEqual(ed.pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center")), ("fill", "left"))
        self.assertEqual(len(dialogs.shown), 2)

    def test_fill_on_a_screen_of_the_same_shape_does_not_ask(self):
        ed, dialogs = editor(0)
        same_shape = Output("X", 3440, 1440)
        self.assertEqual(ed.pick_fit("p.png", PHOTO, [same_shape], ("fill", "center")), ("fill", "center"))
        self.assertEqual(len(dialogs.shown), 1)

    def test_escape_cancels_at_either_step(self):
        self.assertIs(editor(None)[0].pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center")), CANCEL)
        self.assertIs(editor(0, None)[0].pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center")), CANCEL)

    def test_inherit_is_the_first_option_of_a_screen_row(self):
        ed, dialogs = editor(0)
        result = ed.pick_fit("p.png", PHOTO, [LAPTOP], INHERIT, inherit_label="Blurred bars")
        self.assertIs(result, INHERIT)
        title, options, default = dialogs.shown[0]
        self.assertEqual((options[0], default), ("Same as all screens (Blurred bars)", 0))


class ChangeCellTest(unittest.TestCase):
    def change(self, entry, output, column, info, *answers):
        ed, _ = editor(*answers)
        ed._change_cell("f", entry, output, column, info, [LAPTOP, ULTRAWIDE])
        return entry

    def test_all_screens_fit_is_stored_without_defaults(self):
        entry = self.change({}, None, "fit", PHOTO, 2)  # blurred bars
        self.assertEqual(entry, {"fit": "blur"})

    def test_all_screens_back_to_default_leaves_nothing(self):
        entry = self.change({"fit": "blur"}, None, "fit", PHOTO, 0, 0)  # fill, center
        self.assertEqual(entry, {})

    def test_per_screen_fit_is_an_override_next_to_the_all_screens_fit(self):
        entry = self.change({"fit": "blur"}, LAPTOP, "fit", PHOTO, 1 + 0, 0)  # inherit is 0 → fill is 1
        self.assertEqual(entry, {"fit": "blur", "screens": {"eDP-1": {"fit": "fill"}}})

    def test_per_screen_inherit_removes_the_override_and_empty_dicts(self):
        entry = {"fit": "blur", "screens": {"eDP-1": {"fit": "fill", "align": "left"}}}
        self.assertEqual(self.change(entry, LAPTOP, "fit", PHOTO, 0), {"fit": "blur"})

    def test_per_screen_override_keeps_other_columns(self):
        entry = {"screens": {"eDP-1": {"fps": 24}}}
        self.change(entry, LAPTOP, "fit", CLIP, 2)  # inherit, fill, black bars → index 2
        self.assertEqual(entry["screens"]["eDP-1"], {"fps": 24, "fit": "fit"})


ENTER, ESC = style.ENTER[0], style.ESC


class LivePreviewTest(unittest.TestCase):
    def run_editor(self, keys, *answers, entry=None):
        ed, _ = editor(*answers, keys=keys)
        previews = []
        result = ed.edit("p.png", PHOTO, entry or {}, [LAPTOP], on_change=lambda e: previews.append(e))
        return result, previews

    def test_every_change_is_previewed_and_esc_keeps_it(self):
        # Enter on All screens' Fit, choose "Black bars"; then Esc.
        result, previews = self.run_editor([ENTER, ESC], 1)
        self.assertEqual(result, {"fit": "fit"})
        self.assertEqual(previews, [{"fit": "fit"}])

    def test_several_changes_give_several_previews(self):
        result, previews = self.run_editor([ENTER, ENTER, ESC], 1, 2)
        self.assertEqual(previews, [{"fit": "fit"}, {"fit": "blur"}])
        self.assertEqual(result, {"fit": "blur"})

    def test_c_cancels_after_previews(self):
        result, previews = self.run_editor([ENTER, ord("c")], 1)
        self.assertIs(result, CANCEL)
        self.assertEqual(previews, [{"fit": "fit"}])  # the caller restores what it showed

    def test_q_cancels_too(self):
        self.assertIs(self.run_editor([ord("q")])[0], CANCEL)

    def test_a_dismissed_dialog_is_not_a_change(self):
        result, previews = self.run_editor([ENTER, ESC], None)
        self.assertEqual((result, previews), ({}, []))

    def test_choosing_what_is_already_set_is_not_a_change(self):
        result, previews = self.run_editor([ENTER, ESC], 1, entry={"fit": "fit"})
        self.assertEqual(previews, [])

    def test_defaults_are_tidied_in_previews(self):
        info = CLIP
        ed, _ = editor(0, keys=[ord("l"), ENTER, ESC])  # right to Resolution, choose 100%
        previews = []
        result = ed.edit("v.mp4", info, {"scale": 50}, [LAPTOP], on_change=previews.append)
        self.assertEqual((result, previews), ({}, [{}]))


class BrowsingPreviewTest(unittest.TestCase):
    """Moving the highlight shows each option; leaving puts things back."""

    def run_editor(self, answers, keys, entry=None, output_row=0):
        ed, _ = editor(*answers, keys=keys)
        previews = []
        result = ed.edit("p.png", PHOTO, entry or {}, [LAPTOP], on_change=lambda e: previews.append(e))
        return result, previews

    def test_each_highlighted_fit_is_previewed(self):
        # on All screens: highlight Black bars, Blurred bars, then pick Black bars again.
        result, previews = self.run_editor([([1, 2, 1], 1)], [ENTER, ESC])
        self.assertEqual(previews, [{"fit": "fit"}, {"fit": "blur"}, {"fit": "fit"}])
        self.assertEqual(result, {"fit": "fit"})

    def test_escape_in_the_menu_shows_the_old_fit_again(self):
        result, previews = self.run_editor([([1, 2], None)], [ENTER, ESC], entry={"fit": "stretch"})
        self.assertEqual(previews, [{"fit": "fit"}, {"fit": "blur"}, {"fit": "stretch"}])
        self.assertEqual(result, {"fit": "stretch"})

    def test_escape_without_moving_previews_nothing(self):
        result, previews = self.run_editor([None], [ENTER, ESC])
        self.assertEqual((result, previews), ({}, []))

    def test_crop_focus_is_previewed_while_browsing(self):
        # Fill, then browse Left, Right, Top and choose Right.
        result, previews = self.run_editor([0, ([1, 2, 3, 2], 2)], [ENTER, ESC])
        self.assertEqual(previews, [{"align": "left"}, {"align": "right"}, {"align": "top"}, {"align": "right"}])
        self.assertEqual(result, {"align": "right"})

    def test_escape_in_the_focus_menu_undoes_the_whole_choice(self):
        # Browsing: Black bars, then Fill; Enter opens the focus menu; browse Left; Esc.
        result, previews = self.run_editor([([1, 0], 0), ([1], None)], [ENTER, ESC], entry={"fit": "blur"})
        self.assertEqual(previews[-1], {"fit": "blur"})
        self.assertEqual(result, {"fit": "blur"})

    def test_per_screen_browsing_previews_overrides(self):
        ed, _ = editor(([1, 2], 2), keys=[ord("j"), ENTER, ESC])  # down to eDP-1's Fit
        previews = []
        result = ed.edit("p.png", PHOTO, {"fit": "blur"}, [LAPTOP], on_change=previews.append)
        # list: inherit, fill, black bars, blurred bars, …
        self.assertEqual(previews, [{"fit": "blur", "screens": {"eDP-1": {"fit": "fill"}}},
                                    {"fit": "blur", "screens": {"eDP-1": {"fit": "fit"}}}])
        self.assertEqual(result, previews[-1])

    def test_per_screen_inherit_is_previewed_as_no_override(self):
        ed, _ = editor(([0], 0), keys=[ord("j"), ENTER, ESC])
        previews = []
        start = {"fit": "blur", "screens": {"eDP-1": {"fit": "fit"}}}
        result = ed.edit("p.png", PHOTO, start, [LAPTOP], on_change=previews.append)
        self.assertEqual(previews, [{"fit": "blur"}])
        self.assertEqual(result, {"fit": "blur"})


class OpeningPreviewTest(unittest.TestCase):
    def test_the_menu_shows_the_current_choice_when_it_opens(self):
        ed, _ = editor(None)
        shown = []
        ed.pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center"), on_preview=shown.append)
        self.assertEqual(shown, [("fill", "center"), ("fill", "center")])  # on open, and on cancel

    def test_browsing_then_choosing_ends_on_what_was_chosen(self):
        ed, _ = editor(([2, 1], 1))
        shown = []
        result = ed.pick_fit("p.png", PHOTO, [LAPTOP], ("fill", "center"), on_preview=shown.append)
        self.assertEqual(shown, [("fill", "center"), ("blur", "center"), ("fit", "center")])
        self.assertEqual(result, ("fit", "center"))


class CellTextTest(unittest.TestCase):
    def test_inherited_and_own_values(self):
        entry = {"fit": "blur", "screens": {"eDP-1": {"fit": "fill", "align": "left"}}}
        self.assertEqual(SettingsEditor._cell("fit", entry, None), ("Blurred bars", False))
        self.assertEqual(SettingsEditor._cell("fit", entry, LAPTOP), ("Fill · left", False))
        self.assertEqual(SettingsEditor._cell("fit", entry, ULTRAWIDE), ("Blurred bars", True))

    def test_other_columns_are_still_inherited_when_only_fit_is_overridden(self):
        entry = {"fps": 30, "screens": {"eDP-1": {"fit": "fit"}}}
        self.assertEqual(SettingsEditor._cell("fps", entry, LAPTOP), ("30 fps", True))
        self.assertEqual(SettingsEditor._cell("scale", entry, LAPTOP), ("native (1920×1200)", True))


if __name__ == "__main__":
    unittest.main()
