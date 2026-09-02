"""Import make_tour.py against a controlled working directory.

reason: make_tour reads config.json at *import* time -- every [cfg] constant is a
module-level global resolved from the cwd. A test that wants to know what a given
config produces therefore has to import the module fresh with that config in
place, not import once and poke at the globals afterwards.
"""
import contextlib
import importlib.util
import io
import itertools
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAKE_TOUR = os.path.join(REPO, "make_tour.py")

_counter = itertools.count()


def scraper_module(name):
    """Import a scraper/ module by name, with scraper/ on the path.

    reason: photos.py imports lead.py as a flat sibling, so the folder
    itself has to be importable -- there is no package.
    """
    import importlib
    scraper = os.path.join(REPO, "scraper")
    if scraper not in sys.path:
        sys.path.insert(0, scraper)
    return importlib.import_module(name)


def _repo_module(name, relpath):
    """Import a repo script under a private name, once.

    reason: status_module() and tour_module() were the same ten lines twice,
    differing only in two string literals. One body, so the spec/sys.modules/
    exec_module dance cannot drift between them.
    """
    import importlib.util
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def status_module():
    """Import status.py once. It is read-only and takes no cwd from the caller.

    reason: status.py resolves ROOT from its own __file__ and loads the scraper
    helpers at import time, so it does not need the temp-cwd dance make_tour
    needs -- and the pure functions under test take their inputs as arguments.
    """
    return _repo_module("status_under_test", "status.py")


def prospects_module():
    """Import prospects.py once. Its rebuild() takes agents_dir/dest_dir as
    arguments precisely so a test never has to touch the real prospects/."""
    return _repo_module("prospects_under_test", "prospects.py")


def active_view_module():
    """Import active_view.py once. Its rebuild() takes agents_dir/dest_dir as
    arguments precisely so a test never has to touch the real needs_attention/."""
    return _repo_module("active_view_under_test", "active_view.py")


def publish_module():
    """Import publish.py once, for contacted_at()/follow_up_date()."""
    return _repo_module("publish_under_test", "publish.py")


def floorplan_module():
    """Import floorplan.py once. Every function takes its inputs as arguments
    -- no cwd, no config.json -- so one import is safe to share."""
    return _repo_module("floorplan_under_test", "floorplan.py")


def photo_quality_module():
    """Import photo_quality.py once. Same shape as floorplan_module() -- every
    function takes its inputs as arguments, no cwd, no config.json."""
    return _repo_module("photo_quality_under_test", "photo_quality.py")


def migrate_layout_module():
    """Import migrate_layout.py once. Every function takes agents_dir/root as
    arguments so a test never touches the real agents/ tree."""
    return _repo_module("migrate_layout_under_test", "migrate_layout.py")


def tour_module():
    """Import tour.py once, for the pure helpers and the wiring assertions.

    reason: tour.py imports make_tour and publish at module scope. Neither
    touches the network or the filesystem beyond reading a config.json that a
    test cwd does not have, so a plain import is safe -- but it must be given a
    private module name so it cannot collide with the freshly-imported
    make_tour_under_test_N modules listing() creates.
    """
    return _repo_module("tour_under_test", "tour.py")


def dashboard_module():
    """Import dashboard.py once.

    reason: it loads status.py, tour.py, publish.py and the scraper lazily,
    inside Sources.__init__ -- nothing at module scope reads a file, binds a
    socket or parses argv. So a plain import is free, and every function worth
    testing takes a Sources bundle so a test never touches the real tree.
    """
    return _repo_module("dashboard_under_test", "dashboard.py")


def source():
    """make_tour.py as text, for the wiring assertions."""
    return repo_source("make_tour.py")


def repo_source(relpath):
    """Any repo script as text, for the wiring assertions.

    reason: several guards read the *structure* of a function rather than
    running it -- which stitch a call is handed, which flag gates a call site.
    Those tests need the file as text, and each one opening it inline leaked a
    handle and drifted on encoding.
    """
    with open(os.path.join(REPO, relpath), encoding="utf-8") as f:
        return f.read()


@contextlib.contextmanager
def listing(config=None, argv=None, assets=()):
    """Temp listing folder as cwd, with make_tour imported fresh against it.

    assets: filenames to create as placeholders, so the os.path.exists() checks
    in finish() see a logo/plate/watermark without needing real artwork.
    """
    tmp = tempfile.mkdtemp(prefix="tour_test_")
    prev_cwd, prev_argv = os.getcwd(), list(sys.argv)
    name = f"make_tour_under_test_{next(_counter)}"
    try:
        if config is not None:
            with open(os.path.join(tmp, "config.json"), "w") as f:
                json.dump(config, f)
        for asset in assets:
            with open(os.path.join(tmp, asset), "wb") as f:
                f.write(b"placeholder")
        os.chdir(tmp)
        sys.argv = list(argv or ["make_tour.py"])
        spec = importlib.util.spec_from_file_location(name, MAKE_TOUR)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        yield mod, tmp
    finally:
        sys.modules.pop(name, None)
        os.chdir(prev_cwd)
        sys.argv = prev_argv
        shutil.rmtree(tmp, ignore_errors=True)


def capture_finish(mod, **kwargs):
    """Run finish() with every ffmpeg call stubbed; return the argv it built.

    reason: the filtergraph *is* the deliverable -- which layer carries an
    enable= window is the whole of the card/branding rule. Stubbing run() lets
    the real finish() build the real graph without a six-minute encode.
    """
    captured = []
    mod.run = lambda cmd: captured.append(cmd)
    mod.duration = lambda path: kwargs.pop("_duration", 60.0)
    mod.dimensions = lambda path: (1920, 1080)
    mod.trim_filter = lambda path: ("", (400, 200))
    kwargs.setdefault("silent", "work_silent.mp4")
    kwargs.setdefault("music", None)
    kwargs.setdefault("out", "out/x.mp4")
    # reason: finish() narrates every layer it renders. That is right for an
    # operator watching a build and pure noise under a test runner.
    with contextlib.redirect_stdout(io.StringIO()):
        mod.finish(kwargs.pop("silent"), kwargs.pop("music"),
                   kwargs.pop("brand", None), kwargs.pop("out"), **kwargs)
    return captured[0]


def filtergraph(cmd):
    """The -filter_complex argument out of a captured ffmpeg argv."""
    return cmd[cmd.index("-filter_complex") + 1]
