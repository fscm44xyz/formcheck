"""Phase 4.2 -- run formcheck over a mounted SWE-bench task, generically.

Same classification as pytest-10356, with one difference stated up front, because
it decides what these tasks can and cannot show:

    THESE TASKS HAVE NO INDEPENDENT CONTRACT ORACLE.

For pytest-10356 we hand-wrote one (an issue reproduction read through pytest's
public API). Writing one per task is exactly the expensive human work this is
meant to avoid, so here the only behavioural check available is the task's own
PASS_TO_PASS suite: everything the repo already tested, minus the graded F2P test
under examination.

That suite is a real check, but a partial one -- it cannot tell whether the
ISSUE's fix still works. pytest-10356 proved the gap concretely: the `bug_none`
mutant broke the fix and still passed all 79 P2P tests. So a transform that
silently changes behaviour could pass P2P, fail F2P, and be misreported as a
witness.

The gate: only operators whose sole realistic failure mode is LOUD -- an
incomplete rewrite that raises on first use, which P2P does detect -- may be
judged here. That is `symbol_rename` and nothing else. Every other operator is
reported UNVALIDATED on these tasks, however good its argument. The result is
narrower evidence, honestly labelled, rather than wider evidence that rests on an
oracle that cannot disconfirm it.

Run under .venv (swebench + shim).
"""
import os
import re
import sys
import ast
import json
import shutil
import difflib
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swebench_shim  # noqa: F401,E402
from m4_grader import grade_log  # noqa: E402
from f0_equiv import Refused  # noqa: E402
from f2_operators import FAMILY, BORDER  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
F4 = os.path.join(ROOT, "f4")
TEST_HINTS = ("test", "tests", "testing", "conftest.py", "doc", "docs")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class MountedTask:
    def __init__(self, iid):
        self.iid = iid
        self.base = os.path.join(F4, iid)
        self.repo = os.path.join(self.base, "repo")
        self.meta = json.load(open(os.path.join(self.base, "meta.json")))
        self.issue = read(os.path.join(self.base, "issue.txt"))
        self.py = os.path.join(self.base, ".venv", "Scripts", "python.exe")
        if not os.path.exists(self.py):
            self.py = os.path.join(self.base, ".venv", "bin", "python")
        self.test_files = re.findall(r"^\+\+\+ b/(\S+)", read(
            os.path.join(self.base, "tests.diff")), re.M)
        self.changed = re.findall(r"^\+\+\+ b/(\S+)", read(
            os.path.join(self.base, "gold.diff")), re.M)

    # ---- repo plumbing -------------------------------------------------
    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args],
                              capture_output=True, text=True)

    def purge_bytecode(self):
        for root, _, _ in os.walk(self.repo):
            if os.path.basename(root) == "__pycache__":
                shutil.rmtree(root, ignore_errors=True)

    def reset(self):
        self.git("checkout", "--", ".")
        self.git("clean", "-fd")
        self.purge_bytecode()
        for name in ("tests.diff", "gold.diff"):
            r = subprocess.run(["git", "-C", self.repo, "apply",
                                "--whitespace=nowarn",
                                os.path.join(self.base, name)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"apply {name} failed: {r.stderr.strip()[:200]}")

    def graded(self):
        """(reward, grading dict). The graded command is `pytest -rA` over the
        test files the task's own test patch touches -- the shape swebench runs."""
        run = subprocess.run(
            [self.py, "-m", "pytest", "-rA", "-p", "no:cacheprovider",
             *self.test_files],
            cwd=self.repo, capture_output=True, text=True, timeout=1800)
        log = "+ pytest -rA " + " ".join(self.test_files) + "\n" + run.stdout \
            + "\n" + run.stderr
        g = grade_log(log, self.meta)
        return g["reward"], g, log

    # ---- source set ----------------------------------------------------
    def source_files(self, must_contain=None):
        """Repo source files the operators may rewrite. Test and doc trees are
        EXCLUDED on purpose: the transform changes the solution, never the tests
        -- rewriting the graded tests would defeat the whole check."""
        out = {}
        for root, dirs, files in os.walk(self.repo):
            rel_root = os.path.relpath(root, self.repo).replace("\\", "/")
            if rel_root == ".":
                rel_root = ""          # the repo root itself; NOT a hidden dir
            parts = [p.lower() for p in rel_root.split("/") if p]
            if any(p in TEST_HINTS or p.startswith(".") for p in parts):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d.lower() not in TEST_HINTS]
            for fn in files:
                if not fn.endswith(".py") or fn.startswith("test_") \
                        or fn.endswith("_test.py") or fn == "conftest.py":
                    continue
                rel = f"{rel_root}/{fn}" if rel_root else fn
                path = os.path.join(root, fn)
                try:
                    text = read(path)
                except Exception:
                    continue
                if must_contain is not None and must_contain not in text:
                    continue
                out[rel] = text
        return out

    def write_sources(self, sources):
        for rel, text in sources.items():
            with open(os.path.join(self.repo, *rel.split("/")), "w",
                      encoding="utf-8") as f:
                f.write(text)

    def gold_touched(self, target):
        """Module-level symbols whose body the gold patch overlaps, in `target`."""
        ranges, current = [], None
        for line in read(os.path.join(self.base, "gold.diff")).splitlines():
            if line.startswith("+++ b/"):
                current = line[6:].strip()
            elif line.startswith("@@") and current == target:
                m = re.search(r"\+(\d+)(?:,(\d+))?", line)
                if m:
                    start = int(m.group(1))
                    ranges.append((start, start + max(int(m.group(2) or 1), 1) - 1))
        try:
            tree = ast.parse(read(os.path.join(self.repo, *target.split("/"))))
        except (SyntaxError, FileNotFoundError):
            return set()
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                lo, hi = node.lineno, node.end_lineno
                if any(not (hi < a or lo > b) for a, b in ranges):
                    names.add(node.name)
        return names


def failure_sections(log):
    """Per-test failure blocks, keyed by whatever the runner calls the test.

    Scanning the whole log for `E ` lines does NOT work: a passing test that
    deliberately raises prints `E TypeError: ...` too. Measured, not assumed --
    the pytest-10356 baseline log has such a line with zero failures, which
    would have forced every verdict to INVALID.

    THREE BLOCK SHAPES, because SWE-bench is not one test runner. Phase 4 ran
    only pytest repos and this function only understood pytest's per-test form;
    M3 ran ten repos and found the other two, misattributing every failure in
    them (`CHANGES.md` 18):

      pytest per-test    `______ test_name ______`
      pytest collection  `______ ERROR collecting path/to/test_x.py ______`
                         -- one block for a whole module that failed to import,
                         which is precisely what an alpha-rename causes when a
                         test imports the symbol by name
      unittest / django  `====...` then `ERROR: test_name (mod.Class)` then
                         `----...` then the traceback. No underscore rules at
                         all, so the old parser found nothing whatsoever.
    """
    out, current, buf = {}, None, []
    for line in log.splitlines():
        m = re.match(r"^_{3,}\s+(.+?)\s+_{3,}$", line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf)
            current, buf = m.group(1).strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)

    # unittest / django: `ERROR: name (mod.Class)` or `FAIL: ...`, body running
    # to the next `====` separator.
    lines = log.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(?:ERROR|FAIL):\s+(.+?)\s*$", line)
        if not m:
            continue
        body = []
        for nxt in lines[i + 1:]:
            if re.match(r"^={10,}$", nxt):
                break
            body.append(nxt)
        out.setdefault(m.group(1).strip(), "\n".join(body))
    return out


def section_for(sections, test_id):
    """The failure block for a test id, across the runners SWE-bench uses.

    Order matters: the per-test block is preferred, and the module-wide
    collection error is a FALLBACK. A test that has its own failure block failed
    on its own terms; only a test with no block of its own can be explained by
    the module having failed to import.
    """
    tail = test_id.split("::")[-1]
    base = tail.split("[")[0]

    # 1. pytest per-test, and unittest `name (mod.Class)` which arrives already
    #    in that form from swebench's django parser.
    for header, body in sections.items():
        head_tail = header.split(".")[-1]
        if header == tail or head_tail == tail \
                or head_tail.split("[")[0] == base:
            return body
    if test_id in sections:
        return sections[test_id]

    # 1b. sympy's `bin/test`. Its blocks ARE underscore-delimited, so they parse,
    #     but the label is `path/to/test_x.py:test_name` while swebench's sympy
    #     parser reports failing tests by their BARE name (it reads lines ending
    #     in ` F` / ` E`). `header.split(".")[-1]` therefore yields
    #     `py:test_name`, which matches nothing -- the header is right there and
    #     is missed on punctuation. Compare on the part after the last colon.
    for header, body in sections.items():
        if ".py:" not in header:
            continue
        name = header.rsplit(":", 1)[-1].strip()
        if name == tail or name.split("[")[0] == base or header == test_id:
            return body

    # 2. pytest collection error: the whole module failed to import, so no test
    #    in it has a block of its own. An alpha-rename that a test imports by
    #    name produces exactly this and nothing else.
    path = test_id.split("::")[0]
    if path and path != test_id:
        for header, body in sections.items():
            if header.startswith("ERROR collecting") and path in header:
                return body

    # 3. unittest module-level import failure. django reports it as a synthetic
    #    test `test_cookie (unittest.loader._FailedTest)` naming the MODULE that
    #    would not import -- never the tests that were wanted. So the id's
    #    dotted path is decomposed and any component may be the module named in
    #    the synthetic failure: `test_add (messages_tests.test_cookie.CookieTests)`
    #    is explained by `test_cookie (unittest.loader._FailedTest)`.
    parts = re.findall(r"\(([^)]*)\)", test_id)
    components = set()
    for part in parts:
        components.update(c for c in part.split(".") if c)
    components.update(c for c in test_id.split("::")[0].split("/") if c)
    for header, body in sections.items():
        if "_FailedTest" not in header:
            continue
        named = header.split(" ")[0].strip()
        if named and (named in components
                      or named.removesuffix(".py") in components):
            return body
    return None


def names_symbol(text, name):
    """Does this failure exist only because the symbol's NAME changed?

    The mock phrasing is included deliberately: `mock.patch` reports
    `<module 'm'> does not have the attribute 'sym'`, which none of the
    interpreter's own messages match. Leaving it out made the synthetic probe in
    `f4_mock_probe.py` classify reachable mock coupling as INVALID."""
    return (f"has no attribute '{name}'" in text
            or f"does not have the attribute '{name}'" in text
            or f"name '{name}' is not defined" in text
            or f"cannot import name '{name}'" in text
            or f"module '{name}'" in text and "No module named" in text)


def run_task(iid):
    task = MountedTask(iid)
    out = {"instance_id": iid, "repo": task.meta["repo"],
           "oracle": "PASS_TO_PASS suite (partial: cannot verify the issue's fix)",
           "changed_files": task.changed, "cases": []}
    print(f"\n=== {iid} ({task.meta['repo']}) ===")

    # --- CONTROL: the untransformed reference must score 1.0 ---
    task.reset()
    reward, g, _ = task.graded()
    out["control"] = {"reward": reward, "f2p": f"{g['f2p_pass']}/"
                      f"{g['f2p_pass'] + g['f2p_fail']}",
                      "p2p": f"{g['p2p_pass']}/{g['p2p_pass'] + g['p2p_fail']}"}
    print(f"  control (gold, untransformed): reward={reward} "
          f"F2P {out['control']['f2p']} P2P {out['control']['p2p']}")
    if reward != 1.0:
        out["verdict"] = "UNCHECKED"
        out["reason"] = ("the untransformed reference solution does not score 1.0 "
                         "in this mount, so no 0.0 here is evidence of anything")
        print(f"  -> UNCHECKED: {out['reason']}")
        task.reset()
        return out

    for target in [f for f in task.changed if f.endswith(".py")]:
        task.reset()
        touched = task.gold_touched(target)
        print(f"  target {target}  gold-touched symbols: {sorted(touched)}")
        for op in FAMILY:
            if op.tier == BORDER:
                continue
            task.reset()
            base_sources = {target: read(os.path.join(task.repo, *target.split("/")))}
            anchors = [a for a in op.anchors(base_sources, target, task.issue)
                       if a.get("func", a.get("name")) in touched]
            if not anchors:
                out["cases"].append({"operator": op.id, "target": target,
                                     "verdict": "NOT_APPLICABLE",
                                     "note": "no anchor in the gold-touched region"})
                print(f"    {'NOT_APPLICABLE':14s} {op.id}")
                continue
            for anchor in anchors:
                out["cases"].append(run_case(task, op, target, anchor))
    task.reset()
    counts = {}
    for c in out["cases"]:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    out["counts"] = counts
    out["verdict"] = ("FORM_COUPLED" if counts.get("WITNESS") else
                      "NO_WITNESS" if counts.get("CLEAN") else "UNCHECKED")
    return out


def run_case(task, op, target, anchor):
    label = f"{op.id}:{anchor['label']}"
    rec = {"operator": op.id, "target": target, "anchor": anchor["label"],
           "tier": anchor.get("tier", op.tier)}
    if not op.loud_failure:
        rec["verdict"] = "UNVALIDATED"
        rec["note"] = ("no independent contract oracle on this task, and this "
                       "operator's failure mode is silent -- the P2P suite cannot "
                       "disconfirm it")
        print(f"    {'UNVALIDATED':14s} {label}")
        return rec
    try:
        task.reset()
        name = anchor.get("name", "")
        sources = task.source_files(must_contain=name)
        sources[target] = read(os.path.join(task.repo, *target.split("/")))
        rec["files_scanned"] = len(sources)
        new, report = op.apply(sources, target, anchor, task.issue)
    except Refused as exc:
        rec["verdict"] = "REFUSED"
        rec["reason"] = str(exc)
        print(f"    {'REFUSED':14s} {label}  -- {str(exc)[:90]}")
        return rec
    except Exception as exc:  # noqa: BLE001 - a transform failure is data
        rec["verdict"] = "REFUSED"
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"    {'REFUSED':14s} {label}  -- {rec['reason'][:90]}")
        return rec

    task.write_sources(new)
    reward, g, log = task.graded()
    rec["graded"] = {"reward": reward,
                     "f2p": f"{g['f2p_pass']}/{g['f2p_pass'] + g['f2p_fail']}",
                     "p2p": f"{g['p2p_pass']}/{g['p2p_pass'] + g['p2p_fail']}",
                     "f2p_failing": g["f2p_failing"][:3]}
    rec["equivalence_argument"] = report["argument"]
    rec["preconditions"] = report["preconditions"]
    # A P2P failure has two very different causes, and collapsing them would be
    # wrong in both directions.
    #   * The test fails because it REFERENCES the renamed symbol -- `has no
    #     attribute 'X'`, `name 'X' is not defined`, `cannot import name 'X'`.
    #     An alpha-rename changes no expression's value, so such a test is
    #     asserting the symbol's NAME. That is coupling, located in P2P.
    #   * The test fails any other way -- then the rewrite really did change
    #     behaviour, and the transform is INVALID.
    name = anchor.get("name", "")
    sections = failure_sections(log)
    failing = g["p2p_failing"] + g["f2p_failing"]
    unexplained = []
    for test_id in failing:
        body = section_for(sections, test_id)
        if body is None or not names_symbol(body, name):
            unexplained.append(test_id if body is not None
                               else f"{test_id} (no failure section found)")
    rec["p2p_failure_analysis"] = {
        "failing_tests": len(failing),
        "all_reference_the_symbol": bool(failing) and not unexplained,
        "unexplained_examples": unexplained[:3],
    }
    if g["p2p_fail"] > 0 and unexplained:
        rec["verdict"] = "INVALID"
        rec["note"] = (f"{len(unexplained)} failing test(s) do not reference "
                       f"{name!r} -- not behaviour-preserving")
    elif g["p2p_fail"] > 0:
        rec["verdict"] = "WITNESS"
        rec["note"] = (
            f"{g['p2p_fail']} P2P test(s) fail, every one of them because it "
            f"references the internal symbol {name!r} by name; the "
            f"{g['p2p_pass']} tests that do not name it still pass. The coupling "
            "is in PASS_TO_PASS, not in the graded F2P test.")
    elif reward == 1.0:
        rec["verdict"] = "CLEAN"
    else:
        rec["verdict"] = "WITNESS"
        rec["note"] = "the graded F2P test rejects the alpha-rename"
    print(f"    {rec['verdict']:14s} {label}  reward={reward} "
          f"P2P {rec['graded']['p2p']}  (files={rec.get('files_scanned')})")
    if rec["verdict"] == "WITNESS":
        with open(os.path.join(task.base, f"witness_{anchor['label']}.log.txt"),
                  "w", encoding="utf-8") as f:
            f.write(log)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instances", nargs="*")
    args = ap.parse_args()
    mounts = json.load(open(os.path.join(F4, "mounts.json")))
    ids = args.instances or [k for k, v in mounts.items() if v["mounted"]]
    results = []
    for iid in ids:
        try:
            results.append(run_task(iid))
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {iid}: {type(exc).__name__}: {exc}")
            results.append({"instance_id": iid, "verdict": "ERROR",
                            "reason": f"{type(exc).__name__}: {exc}"[:300]})
    json.dump(results, open(os.path.join(F4, "formcheck_results.json"), "w"),
              indent=2)
    print(f"\n-> {os.path.join(F4, 'formcheck_results.json')}")


if __name__ == "__main__":
    main()
