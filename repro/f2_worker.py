"""Phase 2 worker: apply every applicable equivalence-preserving transform to the
gold patch, run the graded tests and the oracle for each. Runs under .venv-pytest.

Anchors are restricted to the symbols the GOLD PATCH ITSELF touches. That is the
principled scope -- the fix's own form is what a graded test can be coupled to --
and it is also what keeps the operator honest: without it, `symbol_rename` would
sweep every definition in the module, and picking the ones that happen to produce
a witness would be selecting for the outcome.

Writes log_f2_<case>.txt per case and f2_cases.json. Classification and grading
happen in f2_gate.py, under .venv.
"""
import os
import re
import sys
import json
import shutil
import difflib
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_case
import oracle
from f0_equiv import Refused
from f2_operators import FAMILY, BORDER

HERE = run_case.HERE
ISSUE = os.path.join(HERE, "issue.txt")
TARGET = "src/_pytest/mark/structures.py"
SCAN_ROOT = "src"
TEST_HINTS = ("test", "tests", "testing", "doc", "docs")
# The dynamic-reach precondition is only sound if it can SEE every production
# reference -- an `__all__` entry in `src/pytest/__init__.py` is exactly the kind
# of reach a 2-file scan would miss. So scan the production tree, and only the
# production tree: test files are never rewritten, because the transform changes
# the solution and not the graded tests.

# What the task's oracle can actually observe. A transform whose `observable`
# is not covered here cannot be confirmed by it -- see f2_gate.py.
ORACLE_OBSERVES = "set of marker names on the collected item (public iter_markers)"
ORACLE_COVERS = {
    "callable signature (arity / parameter names)": True,
    "symbol identity (module-level name)": True,
    "order of elements in a returned collection": False,   # a set hides order
    "human-readable text of an exception message": False,  # never raised here
}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def reset():
    run_case.restore()


def changed_ranges(diff_path):
    """New-file line ranges touched by a unified diff, per file path."""
    out, current = {}, None
    for line in _read(diff_path).splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
            out.setdefault(current, [])
        elif line.startswith("@@") and current:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2) or 1)
                out[current].append((start, start + max(count, 1) - 1))
    return out


def touched(node_span, ranges):
    lo, hi = node_span
    return any(not (hi < a or lo > b) for a, b in ranges)


def read_sources(must_contain=None):
    """Production sources under `SCAN_ROOT`, optionally only those naming a symbol."""
    out = {}
    root_dir = os.path.join(run_case.REPO, SCAN_ROOT)
    for root, dirs, files in os.walk(root_dir):
        rel_root = os.path.relpath(root, run_case.REPO).replace("\\", "/")
        parts = [p.lower() for p in rel_root.split("/") if p]
        if any(p in TEST_HINTS or p.startswith(".") for p in parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d.lower() not in TEST_HINTS]
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test_")                     or fn.endswith("_test.py") or fn == "conftest.py":
                continue
            rel = f"{rel_root}/{fn}"
            try:
                text = _read(os.path.join(root, fn))
            except Exception:
                continue
            if must_contain is not None and must_contain not in text:
                continue
            out[rel] = text
    return out


def write_sources(sources):
    for p, text in sources.items():
        with open(os.path.join(run_case.REPO, *p.split("/")), "w",
                  encoding="utf-8") as f:
            f.write(text)


def _sources_for(anchor):
    """Target file + every production file naming the anchor's symbol."""
    key = anchor.get("name") or anchor.get("func")
    out = read_sources(must_contain=key) if key else {}
    out[TARGET] = _read(os.path.join(run_case.REPO, *TARGET.split("/")))
    return out


def enumerate_cases(issue_text):
    """Every (operator, anchor) whose anchor lies in a gold-touched region."""
    reset()
    run_case.apply_patch(os.path.join(HERE, "gold.diff"))
    sources = read_sources()
    ranges = changed_ranges(os.path.join(HERE, "gold.diff")).get("a/" + TARGET) \
        or changed_ranges(os.path.join(HERE, "gold.diff")).get(TARGET, [])
    import ast
    tree = ast.parse(sources[TARGET])
    touched_names = {n.name for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                     and touched((n.lineno, n.end_lineno), ranges)}
    cases = []
    for op in FAMILY:
        found = op.anchors(sources, TARGET, issue_text)
        kept = [a for a in found
                if a.get("func", a.get("name", "")) in touched_names
                or a.get("name") in touched_names]
        for a in kept:
            cases.append({"op": op, "anchor": a})
        if not kept:
            cases.append({"op": op, "anchor": None,
                          "na": f"no anchor inside the gold-touched region "
                                f"({sorted(touched_names)}); "
                                f"{len(found)} anchor(s) elsewhere in the module"})
    reset()
    return cases, sorted(touched_names), ranges


def run_case_graded(name, op, anchor, issue_text):
    reset()
    run_case.apply_patch(os.path.join(HERE, "tests.diff"))
    run_case.apply_patch(os.path.join(HERE, "gold.diff"))
    before = _sources_for(anchor)
    after, report = op.apply(before, TARGET, anchor, issue_text)
    write_sources(after)
    diff = "".join(difflib.unified_diff(
        before[TARGET].splitlines(keepends=True),
        after[TARGET].splitlines(keepends=True),
        fromfile=f"a/{TARGET} (gold)", tofile=f"b/{TARGET} (gold + {op.id})"))
    run = subprocess.run(
        [run_case.PY, "-m", "pytest", "-rA", "-p", "no:cacheprovider",
         run_case.TEST_FILE],
        cwd=run_case.REPO, capture_output=True, text=True, timeout=600)
    log = run_case.TEST_CMD_ECHO + "\n" + run.stdout + "\n" + run.stderr
    with open(os.path.join(HERE, f"log_f2_{name}.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    with open(os.path.join(HERE, f"f2_{name}.diff"), "w", encoding="utf-8") as f:
        f.write(diff)
    reset()
    return report


def run_case_oracle(op, anchor, issue_text):
    reset()
    run_case.apply_patch(os.path.join(HERE, "gold.diff"))
    before = _sources_for(anchor)
    after, _ = op.apply(before, TARGET, anchor, issue_text)
    write_sources(after)
    proj = tempfile.mkdtemp(prefix="f2_oracle_")
    try:
        with open(os.path.join(proj, "test_repro.py"), "w") as f:
            f.write(oracle.REPRO)
        with open(os.path.join(proj, "conftest.py"), "w") as f:
            f.write(oracle.CONFTEST)
        subprocess.run([run_case.PY, "-m", "pytest", "-p", "no:cacheprovider", "-q",
                        "--no-header", "-o", "addopts=", proj],
                       cwd=proj, capture_output=True, text=True, timeout=300)
        mpath = os.path.join(proj, "markers.txt")
        markers = _read(mpath).split(",") if os.path.exists(mpath) else []
        markers = sorted(m for m in markers if m)
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        reset()
    return markers


def main():
    run_case.assert_editable_pytest()
    issue_text = _read(ISSUE)
    cases, touched_names, ranges = enumerate_cases(issue_text)
    print("Phase 2 -- equivalence-preserving transform family\n")
    print(f"  gold-touched module-level symbols : {touched_names}")
    print(f"  scanned tree                      : {SCAN_ROOT}/ "
          f"({len(read_sources())} production files, tests excluded)")
    print(f"  oracle observes                   : {ORACLE_OBSERVES}\n")

    out = {"oracle_observes": ORACLE_OBSERVES, "oracle_covers": ORACLE_COVERS,
           "touched_symbols": touched_names, "cases": []}
    for case in cases:
        op, anchor = case["op"], case["anchor"]
        if anchor is None:
            print(f"  [{op.id:20s}] N/A   {case['na']}")
            out["cases"].append({"operator": op.id, "tier": op.tier,
                                 "outcome": "NOT_APPLICABLE", "note": case["na"]})
            continue
        name = f"{op.id}_{re.sub(r'[^A-Za-z0-9]+', '_', anchor['label'])[:40]}"
        if op.tier == BORDER:
            print(f"  [{op.id:20s}] ROUTED (tier BORDER) {anchor['label']}")
            out["cases"].append({"operator": op.id, "tier": op.tier, "name": name,
                                 "anchor": anchor["label"], "outcome": "ROUTED"})
            continue
        try:
            report = run_case_graded(name, op, anchor, issue_text)
            markers = run_case_oracle(op, anchor, issue_text)
        except Refused as e:
            print(f"  [{op.id:20s}] REFUSED  {anchor['label']}  -- {e}")
            out["cases"].append({"operator": op.id, "tier": op.tier, "name": name,
                                 "anchor": anchor["label"], "outcome": "REFUSED",
                                 "reason": str(e)})
            reset()
            continue
        print(f"  [{op.id:20s}] ran      {anchor['label']}  oracle={markers}")
        out["cases"].append({"operator": op.id, "tier": report["tier"], "name": name,
                             "anchor": anchor["label"], "outcome": "RAN",
                             "oracle_markers": markers, "report": report})

    json.dump(out, open(os.path.join(HERE, "f2_cases.json"), "w"), indent=2)
    print(f"\n  {len(out['cases'])} case(s) recorded -> f2_cases.json")


if __name__ == "__main__":
    main()
