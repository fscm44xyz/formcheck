"""Independent behavioral oracle for pytest-10356.

Checks the OBSERVABLE contract the issue states -- "a test inheriting from two
marked base classes should carry BOTH markers" -- through pytest's PUBLIC API
(item.iter_markers()), NOT through the private get_unpacked_marks(consider_mro=...)
signature that the graded test happens to assert on.

Runs the scenario as a real pytest session for each mode:
  base : unpatched source   -> expect the BUG (only one marker survives)
  alt  : alternative fix     -> expect BOTH markers (contract satisfied)

If base shows one marker and alt shows both, the oracle is validated (it
distinguishes correct from incorrect) AND the alt fix is behaviorally correct.
"""
import os, sys, subprocess, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))
from run_case import REPO, git, apply_alt, restore, PY  # reuse exact same edit

REPRO = '''import pytest

@pytest.mark.foo
class Foo:
    pass

@pytest.mark.bar
class Bar:
    pass

class TestDings(Foo, Bar):
    def test_dings(self):
        assert True
'''

CONFTEST = '''def pytest_collection_modifyitems(items):
    for item in items:
        if item.name == "test_dings":
            names = sorted({m.name for m in item.iter_markers()})
            with open(item.config.rootpath / "markers.txt", "w") as f:
                f.write(",".join(names))
'''

def run_mode(mode):
    restore()
    if mode == "alt":
        apply_alt()

    proj = tempfile.mkdtemp(prefix=f"oracle_{mode}_")
    try:
        with open(os.path.join(proj, "test_repro.py"), "w") as f:
            f.write(REPRO)
        with open(os.path.join(proj, "conftest.py"), "w") as f:
            f.write(CONFTEST)
        subprocess.run([PY, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                        "--no-header", "-o", "addopts=", proj],
                       cwd=proj, capture_output=True, text=True, timeout=300)
        mpath = os.path.join(proj, "markers.txt")
        markers = open(mpath).read().split(",") if os.path.exists(mpath) else []
        markers = [m for m in markers if m]
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        restore()
    return sorted(markers)

def main():
    print("Independent oracle -- observable contract via public iter_markers():")
    print('  issue: "test_dings inheriting from @foo Foo and @bar Bar should carry BOTH markers"\n')
    results = {}
    for mode in ("base", "alt"):
        m = run_mode(mode)
        results[mode] = m
        verdict = "both markers present" if set(m) == {"foo", "bar"} else "MARKER LOST (bug)"
        print(f"  {mode:4s}: test_dings markers = {str(m):<18}  -> {verdict}")

    print()
    base_bug = set(results["base"]) != {"foo", "bar"}
    alt_ok = set(results["alt"]) == {"foo", "bar"}
    if base_bug and alt_ok:
        print("ORACLE VALIDATED: base exhibits the bug, alt satisfies the contract.")
        print("=> the alternative fix is behaviorally CORRECT, independently of the graded assertion.")
    else:
        print(f"ORACLE INCONCLUSIVE: base_bug={base_bug} alt_ok={alt_ok}")

if __name__ == "__main__":
    main()
