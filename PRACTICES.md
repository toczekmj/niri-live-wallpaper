# Python practices for a maintainable mid-size app

Research notes behind the 0.1.0 refactor of Niri Live Wallpaper (2026-10-25).

The focus is **human maintainability and long-term support**: can someone who has never seen the code, or the
author two years from now, find the right place, understand why it's shaped that way, change it safely, and keep
it running as niri, DMS, mpvpaper and Python move on? Style rules and "clean code" purity come second. Each
section gives the practice, why it matters for maintenance, the sources, and what it means here.

---

## 1. Organize modules by responsibility, so things are easy to find

**Practice.** Once a project outgrows one file, put the code in a package named after the project. Give each
module **one clear purpose** with a short lowercase name that says what it is about. Keep `__init__.py` empty,
or nearly so. Put tests in `tests/`, mirroring the modules. When two modules need each other, move the shared
part into a third module instead of importing in a circle.

**Why it helps maintenance.** The most common maintenance question is "where is the code that does X?". A
1,400-line file answers that with Ctrl+F; a module named `systemd.py` answers it with the file list. Clear
boundaries also limit what a change can break.

**Caution against over-splitting.** Dozens of 20-line modules, layers of abstract classes or plugin systems hurt
readability as much as one giant file. Split along real responsibilities (talking to niri, to systemd, to
ffmpeg, the settings file, the UI), not along every function.

Sources: [Python Wiki: project layout](https://wiki.python.org/moin/ProjectFileAndDirectoryLayout),
[The Hitchhiker's Guide: structuring your project](https://python-guide-zh-cn.readthedocs.io/zh/latest/writing/structure.html),
[Dagster: best practices in structuring Python projects](https://dagster.io/blog/python-project-best-practices),
[DEV: organizing code in modules and packages](https://dev.to/nkpydev/organizing-code-in-python-modules-and-packages-1o16).

**Here.** `nlw.py` became the package `niri_live_wallpaper/`, with one module per outside system or concern
(`niri`, `dms`, `systemd`, `desktop`, `media`), the app's own logic (`config`, `cycling`, `variants`,
`library`), the background `service`, and a `tui/` sub-package. The dependency direction is one-way: the UI and
the service use the logic modules, and the logic modules never import the UI.

## 2. Keep logic separate from side effects ("functional core, imperative shell")

**Practice.** Put decisions (calculations, rules, parsing) in plain functions that take data and return data.
Push side effects (running programs, reading files, the clock, the screen) to the edges, and pass the results
in as arguments. Watch out for one side effect deep in a call stack: everything that calls it inherits it.

**Why it helps maintenance.** Pure functions can be read in isolation, are easy to test without mocks, and are
safe to change. Most bugs live in decisions, not in `subprocess.run` calls.

Sources: [kyle.au: Functional Core, Imperative Shell](https://kyle.au/notes/technology/development/functional-core-imperative-shell-pattern),
[No Longer Set: FCIS](https://nolongerset.com/fcis/),
[HackerNoon: negating side effects in Python](https://www.hackernoon.com/negating-side-effects-in-python-a-guide-with-pictures).

**Here.**
- `variants.plan()` used to call `ffprobe` itself. Now it takes the probed `VideoInfo` and decides whether a
  copy is needed and which ffmpeg filter to use.
- `cycling` became pure maths: `is_due(cfg, now, count)` and `next_video(videos, current)`. The service does the
  switching.
- `niri.parse_outputs()` is separate from running `niri msg`.

All of these are now covered by unit tests.

## 3. Name your data: dataclasses for records, plain JSON for files

**Practice.** When the fields are known in advance, use a `dataclass` (or `NamedTuple`) instead of a positional
tuple or a dict with string keys. Keep dicts for truly key→value data, and for data that has to stay
JSON-compatible. Dataclass annotations document the contract but aren't enforced at runtime.

**Why it helps maintenance.** `job.scale` is self-explanatory; `job[4]` or `info["w"]` makes the reader go and
find where the tuple or dict was built. A typo in a dict key fails silently; a typo in an attribute name fails
loudly.

Sources: [Machine Learning Mastery: dataclasses for structured application data](https://machinelearningmastery.com/dataclasses-for-structured-application-data/),
[DEV: explicit is better than implicit, avoid dict overuse](https://dev.to/victorosilva/explicit-is-better-than-implicit-avoid-dict-overuse-57k4),
[chipx86: keyword-only arguments in dataclasses](https://notes.chipx86.com/Writing/TIL/Use+keyword-only+arguments+in+Python+dataclasses).

**Here.** `VideoInfo`, `Output`, `ScreenJob`, `Variant` and `CycleMode` are frozen dataclasses (frozen, so they
can be compared and used in sets, which the service relies on). The settings file stays a JSON dict, because
people edit it by hand and older or newer versions of the app must be able to read it. But it's only touched
through `config.py`, which documents the whole schema in one place.

## 4. Version your on-disk formats and migrate explicitly

**Practice.** Store a `version` number in every file the app writes. On load, run ordered migration steps
(v1→v2→…) to bring old files up to date. Give new fields defaults so old files stay valid. Leave files from a
*newer* version alone instead of breaking them. Test each migration.

**Why it helps maintenance.** Compatibility code scattered through the program ("if the old key exists then…")
piles up and is never removed, because nobody knows which versions still need it. Numbered migrations in one
place document the format's history and can be tested.

Sources: [Halon: configuration versioning](https://docs.halon.io/kb/miscellaneous/configuration-versioning),
[AiiDA: config migrations](https://aiida-core.readthedocs.io/en/latest/_modules/aiida/manage/configuration/migrations/migrations.html),
[better-openclaw: migrations](https://www.mintlify.com/bidewio/better-openclaw/guides/migrations),
[Packit: configuration versioning](https://packit.dev/research/ux/configuration-versioning),
[pydantic-versions: adoption guidance](https://pydantic-versions.readthedocs.io/en/latest/guide/adoption-guidance/).

**Here.** `config.json` gained `"version": 2`. The old "custom interval in hours" fallback, which used to live
inside the cycling code and the cycle dialog, is now the v1→v2 migration in `config.py`, with a test.

## 5. Type hints at the boundaries first

**Practice.** Annotate function signatures, starting with the ones other modules call, and extend inward
gradually. Treat hints as documentation that tools can check. Don't chase 100% coverage or complex generic types
in a small app.

**Why it helps maintenance.** Hints answer "what does this take and return?" without reading the body, make
refactoring safer, and let editors catch mistakes. Studies of real projects find maintainers put them where
they communicate most: at module boundaries.

Sources: [arXiv: type hints in Python libraries, adoption and maintenance](https://arxiv.org/pdf/2609.02782),
[Real Python: pros and cons of type hints](https://realpython.com/lessons/pros-and-cons-type-hints/),
[EuroPython 2025: type hints in real-world projects](https://www.ep2025.europython.eu/session/type-hints-in-real-world-projects-maintenance-improvement),
[learn-dev: typing](https://learn-dev.readthedocs.io/en/latest/typing.html).

**Here.** All module-level functions and public methods have annotations (`from __future__ import annotations`,
`X | None`, built-in generics). No type checker is required to run the app.

## 6. Logging: modules log, the entry point configures

**Practice.** Each module creates `log = logging.getLogger(__name__)` and only emits messages. Configure
handlers and format once, in the application's entry point. Don't `print()` for diagnostics.

**Why it helps maintenance.** When something goes wrong months later, the log is the only witness. Per-module
logger names show where a message came from, and one configuration point decides where logs go (the journal for
the service, a file for the TUI, which owns the terminal).

Sources: [Python docs: logging](https://docs.python.org/3/library/logging),
[Real Python: logging best practices](https://realpython.com/ref/best-practices/logging/).

**Here.** The service logs to stderr, which systemd puts in the journal
(`journalctl --user -u niri-live-wallpaper`). The TUI logs to `~/.local/state/niri-live-wallpaper/tui.log`
(rotated, so it stays small). Failures that used to be silently swallowed, like a missing program, a timeout or
a failed encode, are now logged.

## 7. One careful way to run external programs

**Practice.** Use `subprocess.run` with an **argument list**, never `shell=True`. Always set a **timeout**.
Handle `FileNotFoundError` (program not installed), `TimeoutExpired` and non-zero exits explicitly. Don't leave
`PIPE`s unread. Use `Popen` only for long-running or streaming processes.

**Why it helps maintenance.** This app is mostly glue around other programs (niri, systemd, ffmpeg, mpvpaper,
DMS, fzf). If every call site handles failure its own way, behaviour is inconsistent and one hung program can
freeze the UI. A single helper makes the rules visible and easy to change.

Sources: [Python docs: subprocess](https://docs.python.org/3.4/library/subprocess.html),
[Stackify: a guide to Python subprocess](https://stackify.com/a-guide-to-python-subprocess/),
[LinuxConfig: launching external processes](https://linuxconfig.org/how-to-launch-external-processes-with-python-and-the-subprocess-module).

Also give child processes **no terminal input** (`stdin=DEVNULL`) unless they need it. Programs like ffmpeg and
mpv read keys from an inherited terminal and steal them from an interactive app. This app hit exactly that bug:
Esc never reached the "cancel encoding" check.

**Here.** `proc.run()` applies those rules everywhere. A missing program or a timeout is logged and returned as
`None`, and the caller decides what that means (usually "degrade gracefully", as the README promises).
`systemctl` calls, which used to have no timeout, now have one.

## 8. Comments say *why*; docstrings say *what for*

**Practice.** Module docstrings explain what the module is responsible for. Function docstrings describe
behaviour, inputs and outputs. Inline comments record **reasons** and constraints the code can't express, such
as "mpvpaper would quit on SIGUSR1, so only signal the main process". Don't narrate the code. Treat stale
comments as bugs.

**Why it helps maintenance.** The code shows *what* happens. Six months later, the expensive question is *why
not the obvious way?*. That knowledge exists only in the author's head unless it's written down.

Sources: [PostHog: writing code comments](https://mcpservers.org/agent-skills/posthog/writing-code-comments),
[Szeged University: clean code, comments matter](https://okt.inf.szte.hu/projektmunka/en/background/clean_code_comments_matter.html),
[explainthis: maintainable code comments](https://www.explainthis.io/en/swe/maintainable-code-comments),
[Educative: comments and documentation](https://www.educative.io/courses/learn-python-3-complete-guide/comments-and-documentation).

**Here.** The existing "why" comments (frame callbacks, start-new-before-stop-old, even sizes for encoders,
wl-copy forking) were kept next to their code. Each module starts with a docstring describing its job, and
`config.py` holds the full settings schema.

## 9. Tests for the logic, with no extra dependencies

**Practice.** Unit-test the pure core thoroughly: parsing, scheduling, planning, migrations. Test the "shell"
(the parts with side effects) more lightly, or by hand. Prefer the standard library's `unittest` when the app
otherwise has no dependencies, so anyone can run the tests with just Python.

**Why it helps maintenance.** Tests are what make later changes safe. They are the difference between "I think
this still works" and knowing it. They also document the edge cases (`1:60` is invalid, `"2"` means 2:00, …).

Sources: [kyle.au: FCIS (test-suite shape)](https://kyle.au/notes/technology/development/functional-core-imperative-shell-pattern),
[Python Wiki: tests/ directory](https://wiki.python.org/moin/ProjectFileAndDirectoryLayout),
[pydantic-versions: test each migration](https://pydantic-versions.readthedocs.io/en/latest/guide/adoption-guidance/).

**Here.** `tests/` covers config migration and settings inheritance, cycle maths, variant planning, niri output
parsing and include-following, and frame-rate parsing. Run them with `python3 -m unittest`, no install needed.

## 10. Project metadata, one version number, a changelog

**Practice.** Describe the project in `pyproject.toml`: name, version, `requires-python`, and an entry point
under `[project.scripts]`. Keep the version in one place. Keep a human-written `CHANGELOG.md` (Keep a Changelog
format, SemVer). A dump of commit messages isn't a changelog.

**Why it helps maintenance.** `requires-python` and the entry point answer "how do I run or install this?"
without reading code. A changelog answers "what changed and what might break?" when updating. Version numbers
let bug reports say exactly which code they're about.

Sources: [PyPA: writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/),
[Keep a Changelog](https://keepachangelog.com/en/2.0.0/),
[EBRAINS handbook: how to keep a changelog](https://handbook.ebrains.eu/technical-deep-dive/development-lifecycle/how-to-keep-changelog/).

**Here.** `pyproject.toml` declares Python ≥ 3.10, no runtime dependencies, and an `nlw` command. The version
lives in `niri_live_wallpaper/__init__.py` (and `pyproject.toml`). `CHANGELOG.md` starts at 0.1.0.

## 11. Layout: flat, because the app runs straight from the checkout

**Practice.** PyPA describes two layouts. The **src layout** (`src/pkg/`) stops you from accidentally importing
the in-development copy and surfaces packaging mistakes, but the project has to be **installed** before it can
run. The **flat layout** (`pkg/` at the top level) can be run directly from the source tree.

**Why it helps maintenance here.** This app has no dependencies, isn't published to PyPI, and is used by running
`./nlw.py` from a clone. A flat layout keeps that working with no install step, and the systemd service can run
it from the checkout too. The src layout's main benefit, catching packaging mistakes before publishing, doesn't
apply. If the app is ever published, moving to `src/` is a mechanical change.

Sources: [PyPA: src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/),
[editables: scope](https://editables.readthedocs.io/en/latest/scope.html),
[Real Python: project layout](https://realpython.com/ref/best-practices/project-layout/).

**Here.** `niri_live_wallpaper/` sits at the top level. `nlw.py` is a three-line launcher. The systemd unit runs
`python -m niri_live_wallpaper run` with `PYTHONPATH` set to the checkout, so it works the same whether you run
from the clone or install with `pip`/`pipx`.

## 12. Keep it boring

These came up across almost every source, and they matter most for long-term support:

- **Few dependencies.** Every dependency is something that can break, change licence or disappear. This app uses
  only the standard library; external *programs* are optional where possible and documented in the README.
- **Degrade gracefully.** A missing optional tool (fd, wl-copy, gdbus, DMS) disables one feature with a clear
  message instead of crashing.
- **Refactors keep behaviour unchanged.** Change structure and behaviour in separate steps, so a regression can
  be traced to one of them. The 0.1.0 refactor changed no user-visible behaviour except the two notes in
  `CHANGELOG.md`.
- **Use version control.** This project isn't a git repository yet. `git init` plus small, described commits is
  the single biggest maintainability improvement still available.
