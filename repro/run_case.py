"""Reproduce one SWE-bench rollout locally (no Docker).

  python run_case.py <base|gold|alt>

Restores the repo, applies the hidden test patch, applies the chosen solution,
runs the exact test command, and writes the raw log to log_<mode>.txt.

The tests are ALWAYS run by the pytest-editable venv (autodetected), regardless of
which interpreter launches this script -- so `python run_case.py gold` cannot
silently run against the wrong pytest and produce a false 0.0.
"""
import os, sys, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# --- locate the pytest checkout (env override, else <root>/pytest) ---
_DEFAULT_REPO = os.path.abspath(os.path.join(HERE, "..", "..", "pytest"))
REPO = os.environ.get("REWARDPATCH_PYTEST_REPO", _DEFAULT_REPO)
if not os.path.isdir(os.path.join(REPO, "src", "_pytest")):
    raise SystemExit(
        f"pytest checkout not found at: {REPO}\n"
        f"Set REWARDPATCH_PYTEST_REPO to a pytest clone checked out at the task "
        f"base commit (3c1534944cbd34e8a41bc9e76818018fadefc9a1), or place it at "
        f"{_DEFAULT_REPO}. See README.md."
    )


def find_pytest_python():
    """The interpreter that RUNS the tests: env override, else the .venv-pytest
    created next to the pytest checkout. Chosen independently of whichever python
    launched this script."""
    env = os.environ.get("REWARDPATCH_PYTEST_PYTHON")
    if env:
        if not os.path.exists(env):
            raise SystemExit(f"REWARDPATCH_PYTEST_PYTHON does not exist: {env}")
        return env
    base = os.path.abspath(os.path.join(HERE, "..", "..", ".venv-pytest"))
    for cand in (os.path.join(base, "Scripts", "python.exe"),   # Windows
                 os.path.join(base, "bin", "python")):           # POSIX
        if os.path.exists(cand):
            return cand
    raise SystemExit(
        "Test-runner interpreter not found. Create a venv with pytest installed "
        f"editable at {base}, or set REWARDPATCH_PYTEST_PYTHON. See README.md."
    )


PY = find_pytest_python()   # runs pytest; deliberately NOT sys.executable
STRUCT = os.path.join(REPO, "src", "_pytest", "mark", "structures.py")
TEST_CMD_ECHO = "+ pytest -rA testing/test_mark.py"
TEST_FILE = "testing/test_mark.py"


def assert_editable_pytest():
    """Fail loudly unless PY imports pytest from REPO/src (the editable install).
    Without this, running against a different or absent pytest silently yields a
    false 0.0 -- the failure mode this guard exists to prevent."""
    r = subprocess.run(
        [PY, "-c", "import _pytest,sys; sys.stdout.write(_pytest.__file__)"],
        capture_output=True, text=True,
    )
    path = (r.stdout or "").strip()
    repo_src = os.path.abspath(os.path.join(REPO, "src")).lower()
    if r.returncode != 0 or not path or not os.path.abspath(path).lower().startswith(repo_src):
        raise SystemExit(
            "The test-runner python does not import pytest from the repo checkout, "
            "so results would be meaningless.\n"
            f"  python : {PY}\n  REPO   : {REPO}\n"
            f"  _pytest resolved to: {path or '<import failed>'}\n"
            f"Fix: install pytest editable into that venv:\n  {PY} -m pip install -e {REPO}"
        )


def git(*args, check=True):
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r


def purge_bytecode():
    """Delete `__pycache__` under the checkout's source tree.

    `git clean -fd` does NOT remove it: `.pyc` is gitignored, and clean skips
    ignored files without `-x`. Restoring a `.py` whose compiled form is still on
    disk can therefore leave a stale module importable, and with an editable
    install that shows up as a spurious failure in the NEXT case rather than in
    the one that caused it. Measured, not theorised: without this purge, running
    a rename transform after another transform made the independent oracle report
    a broken contract for a transform that is fine when run alone.
    """
    removed = 0
    for base in ("src", "testing"):
        for root, dirs, _ in os.walk(os.path.join(REPO, base)):
            if os.path.basename(root) == "__pycache__":
                shutil.rmtree(root, ignore_errors=True)
                removed += 1
    return removed


def restore():
    """Return the checkout to a clean base state. Use this everywhere instead of
    an ad-hoc checkout+clean, so no case can inherit the previous one's state."""
    git("checkout", "--", ".")
    git("clean", "-fd", "testing", "src")
    purge_bytecode()


def apply_patch(path):
    r = subprocess.run(["git", "-C", REPO, "apply", "--whitespace=nowarn", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git apply {os.path.basename(path)} failed:\n{r.stderr}")


# ---- alternative correct fix: MRO-aware, WITHOUT the invented consider_mro kwarg ----
OLD_GUM = '''def get_unpacked_marks(obj: object) -> Iterable[Mark]:
    """Obtain the unpacked marks that are stored on an object."""
    mark_list = getattr(obj, "pytestmark", [])
    if not isinstance(mark_list, list):
        mark_list = [mark_list]
    return normalize_mark_list(mark_list)'''

NEW_GUM = '''def get_unpacked_marks(obj: object) -> List[Mark]:
    """Obtain the unpacked marks that are stored on an object.

    For classes, collect marks from the class and all of its base classes in
    MRO order, so markers from multiple base classes are merged rather than one
    shadowing the others.
    """
    if isinstance(obj, type):
        mark_list: List = []
        for klass in obj.__mro__:
            item = klass.__dict__.get("pytestmark", [])
            if isinstance(item, list):
                mark_list.extend(item)
            else:
                mark_list.append(item)
    else:
        mark_list = getattr(obj, "pytestmark", [])
        if not isinstance(mark_list, list):
            mark_list = [mark_list]
    return list(normalize_mark_list(mark_list))'''

OLD_STORE = '''    assert isinstance(mark, Mark), mark
    # Always reassign name to avoid updating pytestmark in a reference that
    # was only borrowed.
    obj.pytestmark = [*get_unpacked_marks(obj), mark]'''

NEW_STORE = '''    assert isinstance(mark, Mark), mark
    # Always reassign name to avoid updating pytestmark in a reference that
    # was only borrowed.  Read only the marks stored *directly* on obj (not the
    # MRO-merged view) so base-class marks aren't copied onto the subclass.
    own = obj.__dict__.get("pytestmark", []) if isinstance(obj, type) else getattr(obj, "pytestmark", [])
    if not isinstance(own, list):
        own = [own]
    obj.pytestmark = [*normalize_mark_list(own), mark]'''


def apply_alt():
    with open(STRUCT, "r", encoding="utf-8") as f:
        src = f.read()
    for old, new in [(OLD_GUM, NEW_GUM), (OLD_STORE, NEW_STORE)]:
        if old not in src:
            raise RuntimeError("alt: anchor not found:\n" + old[:80])
        src = src.replace(old, new, 1)
    with open(STRUCT, "w", encoding="utf-8") as f:
        f.write(src)


def main():
    mode = sys.argv[1]
    assert_editable_pytest()
    # restore to a clean base checkout
    restore()

    apply_patch(os.path.join(HERE, "tests.diff"))   # hidden tests always applied
    if mode == "gold":
        apply_patch(os.path.join(HERE, "gold.diff"))
    elif mode == "alt":
        apply_alt()
    elif mode == "base":
        pass
    else:
        raise SystemExit("mode must be base|gold|alt")

    run = subprocess.run(
        [PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider", TEST_FILE],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    log = TEST_CMD_ECHO + "\n" + run.stdout + "\n" + run.stderr
    out = os.path.join(HERE, f"log_{mode}.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(log)

    # restore
    restore()

    tail = "\n".join(run.stdout.splitlines()[-3:])
    print(f"[{mode}] pytest exit={run.returncode}  log={out}")
    print(f"[{mode}] {tail}")


if __name__ == "__main__":
    main()
