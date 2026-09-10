"""`import_local` across the all-fail tasks: how much of a total suite loss is one import?

For each task where a rename fails EVERY graded test, move the coupled symbol's
module-scope import into the test functions that actually use it, changing nothing
else, and re-grade under the same rename. What comes back is the number of tests
that never referenced the symbol at all.

    N          graded tests
    k          tests still failing after the move -- the ones naming the symbol
    recovery   N - k, attributable to the single module-scope import line

TWO GRADINGS PER TASK, in one container:

  control     rename only, no test-side change. MUST reproduce the witness --
              zero graded node ids reported. If it does not, this run's rename
              set differs from the operator's and the measurement is void. That
              is how `django-11179`'s incomplete rename was caught in M0d, where
              renaming one of five referencing files broke the library and every
              variant read 0.0.
  measured    import_local + the same rename.

`recovery == 0` on a task whose control reproduced is either a fourth OUTCOME or
a DEFECT that stops the run, and the two are separated in code rather than by
reading:

  HELPER_COUPLED   every graded test reaches the symbol through a shared helper
                   rather than through the module-scope import, so recovery is
                   genuinely 0 and no placement of that import can change it.
                   Requires ALL FOUR of:
                     1. the round trip held on every renamed file
                     2. the residue grep is empty
                     3. the module loaded -- graded node ids reported > 0
                     4. every graded test's own failure block names the symbol
  DEFECT           anything else. The run stops.

The premise of the stop rule -- "this cannot happen if the import is what couples
the module" -- is sound, and its antecedent is false on `django-14376`, where a
helper method called by every graded test holds the reference. Check 3 is what
separates this from the `str.replace` defect that voided the first run, where
nothing imported and nothing ran; checks 1 and 2 are what separate it from a
rename that was never well formed.

NOT APPLICABLE is a separate outcome, not a recovery of zero. A task whose test
module reaches the symbol some other way -- a class-body attribute access, say,
which runs at import time and cannot be deferred into a function -- has no
module-scope import to move. `pylint-4604` is that shape. Reporting it as
"recovers nothing" would be false.

Writes `import_local_run.json` unconditionally. The file is the artifact.

    ~/.venv-fc/bin/python repair/scan/import_local_run.py --all
    ~/.venv-fc/bin/python repair/scan/import_local_run.py --task django__django-12155
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "scale"), os.path.join(ROOT, "repro")):
    if p not in sys.path:
        sys.path.insert(0, p)

from f4_formcheck import failure_sections, section_for, names_symbol  # noqa: E402

RECORDS = os.path.join(ROOT, "scale", "records_m4")
OUT = os.path.join(HERE, "import_local_run.json")
WORKDIR = "/testbed"
PY = "/opt/miniconda3/envs/testbed/bin/python"
CONTAINER = "scan-import-local"


# ---------------------------------------------------------------- transform

class NotApplicable(Exception):
    """No module-scope import of the symbol to move."""


def import_local(src, symbol):
    """Move `symbol`'s module-scope import into every function that uses it.

    Returns the rewritten source. Raises `NotApplicable` when there is no
    module-scope `from X import symbol` to move, or when the symbol is reached at
    module scope outside a function -- a class-body attribute, a module-level
    constant -- because that reference runs at import time and no relocation of an
    import can defer it.
    """
    tree = ast.parse(src)
    lines = src.splitlines()

    node_imp = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if any(a.name == symbol and a.asname is None for a in node.names):
                node_imp = node
                break
    if node_imp is None:
        raise NotApplicable("no module-scope `from ... import %s`" % symbol)

    dots = "." * (node_imp.level or 0)
    modname = dots + (node_imp.module or "")
    keep = [a for a in node_imp.names if not (a.name == symbol and a.asname is None)]

    # Which functions reference the symbol, and does anything outside one?
    def refs(node):
        return any(isinstance(n, ast.Name) and n.id == symbol
                   for n in ast.walk(node))

    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and refs(n)]
    covered = set()
    for f in funcs:
        covered.update(range(f.lineno, (f.end_lineno or f.lineno) + 1))
    stray = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == symbol
             and n.lineno not in covered
             and not (node_imp.lineno <= n.lineno <= (node_imp.end_lineno or node_imp.lineno))]
    if stray:
        raise NotApplicable(
            "%s is referenced at module scope outside any function, line(s) %s"
            % (symbol, sorted(set(stray))))
    if not funcs:
        raise NotApplicable("%s is imported but never referenced in a function"
                            % symbol)

    edits = []          # (start_line, end_line_inclusive, replacement_lines)
    for f in funcs:
        body = f.body
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str) and len(body) > 1):
            first = body[1]          # insert after a docstring
        indent = " " * first.col_offset
        edits.append((first.lineno, first.lineno - 1,
                      ["%sfrom %s import %s" % (indent, modname, symbol)]))

    imp_start, imp_end = node_imp.lineno, node_imp.end_lineno or node_imp.lineno
    if keep:
        names = ", ".join(a.name + (" as " + a.asname if a.asname else "")
                          for a in keep)
        repl = ["from %s import %s" % (modname, names)]
    else:
        repl = []
    edits.append((imp_start, imp_end, repl))

    for start, end, repl in sorted(edits, key=lambda e: -e[0]):
        lines[start - 1:end] = repl
    out = "\n".join(lines) + ("\n" if src.endswith("\n") else "")
    ast.parse(out)
    return out


# ---------------------------------------------------------------- container

def sh(script, check=False):
    r = subprocess.run(["docker", "exec", "--workdir", WORKDIR, CONTAINER,
                        "sh", "-c", script], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("%r -> %s" % (script[:90], r.stderr.strip()[:300]))
    return r


def put(path, text):
    r = subprocess.run(["docker", "exec", "-i", "--workdir", WORKDIR, CONTAINER,
                        "sh", "-c", "mkdir -p $(dirname '%s') && cat > '%s'"
                        % (path, path)],
                       input=text, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("put %s: %s" % (path, r.stderr.strip()[:300]))


def grade(spec):
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from swebench.harness.test_spec.python import get_test_directives
    from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
    from swebench.harness.grading import test_passed
    from m4_grader import grade_log
    meta = spec["meta"]
    cmd = MAP_REPO_VERSION_TO_SPECS[meta["repo"]][meta["version"]]["test_cmd"]
    if isinstance(cmd, list):
        cmd = cmd[-1]
    directives = get_test_directives({"repo": meta["repo"],
                                      "test_patch": spec["tests_diff"]})
    full = " ".join([cmd, *directives])
    r = sh("export PATH=%s:$PATH && cd %s && %s"
           % (os.path.dirname(PY), WORKDIR, full))
    log = "+ " + full + "\n" + (r.stdout or "") + "\n" + (r.stderr or "")
    sm = MAP_REPO_TO_PARSER[meta["repo"]](log.split(cmd)[-1], None)
    graded = list(meta["FAIL_TO_PASS"]) + list(meta["PASS_TO_PASS"])
    return {
        "grade": grade_log(log, meta),
        "reported": [t for t in graded if t in sm],
        "failing": sorted(t for t in graded if not test_passed(t, sm)),
        "n_graded": len(graded),
    }, log


def rename_everywhere(symbol, new):
    """Rename across production sources, then verify no residue -- the M0d guard.

    Returns evidence rather than just the file list: checks 1 and 2 of the
    HELPER_COUPLED classification are exactly "these two did not raise", and a
    classification that cannot show its own evidence is worth as little as an
    unfired guard.
    """
    files = sh("grep -rl '\\b%s\\b' --include='*.py' . "
               "| grep -v '/tests\\?/' | grep -v '/testing/' | sort" % symbol).stdout.split()
    if not files:
        raise RuntimeError("no production file references %s" % symbol)
    pat = re.compile(r"\b%s\b" % re.escape(symbol))
    back = re.compile(r"\b%s\b" % re.escape(new))
    verified = 0
    for path in files:
        src = sh("cat '%s'" % path, check=True).stdout
        # Word boundaries, matching the `\b` the file selection and the residue
        # check above and below already use. `str.replace` rewrote any longer
        # identifier containing the symbol, and the residue grep could not see
        # it: `\bsymbol\b` no longer matches inside the corrupted token.
        renamed = pat.sub(new, src)
        if back.sub(symbol, renamed) != src:
            raise RuntimeError(
                "rename of %s in %s is not an alpha-rename: substituting %s back "
                "on a word boundary does not reproduce the input"
                % (symbol, path, new))
        put("%s/%s" % (WORKDIR, path), renamed)
        verified += 1
    residue = sh("grep -rl '\\b%s\\b' --include='*.py' . "
                 "| grep -v '/tests\\?/' | grep -v '/testing/' | sort" % symbol).stdout.split()
    if residue:
        raise RuntimeError("incomplete rename of %s: residue in %s"
                           % (symbol, residue))
    return {"files": files, "round_trip_verified": verified, "residue": []}


def sections_for(sections, test_id):
    """The failure block(s) for a test id, including subTest blocks.

    `section_for` cannot match a subTest block, whose header carries a trailing
    `(keys=(...))` beyond the test id -- and that is the very shape that produced
    the unterminated status line (`CHANGES.md` 35). The fallback matches by
    prefix and joins every block, because one test can error under several
    subTest keys. Done here rather than in `f4_formcheck`, whose `section_for`
    graded the published run and is not being changed under a scan.
    """
    body = section_for(sections, test_id)
    if body is not None:
        return body
    parts = [b for h, b in sections.items() if h.startswith(test_id + " (")]
    return "\n".join(parts) if parts else None


def classify_zero(symbol, rename_ev, got, log, spec):
    """`recovery == 0`: a HELPER_COUPLED verdict, or a DEFECT that stops the run.

    Four checks, and all four must hold. Each rules out one way of arriving at a
    zero that is not a property of the task.
    """
    meta = spec["meta"]
    graded = list(meta["FAIL_TO_PASS"]) + list(meta["PASS_TO_PASS"])
    checks, why = {}, []

    files = rename_ev["files"]
    checks["round_trip_on_every_renamed_file"] = bool(files) and \
        rename_ev["round_trip_verified"] == len(files)
    if not checks["round_trip_on_every_renamed_file"]:
        why.append("round trip verified on %d of %d renamed file(s)"
                   % (rename_ev["round_trip_verified"], len(files)))

    checks["residue_empty"] = not rename_ev["residue"]
    if not checks["residue_empty"]:
        why.append("residue: %s" % rename_ev["residue"])

    checks["module_loaded"] = len(got["reported"]) > 0
    if not checks["module_loaded"]:
        why.append("no graded node id was reported -- nothing ran, so this 0 is "
                   "ABSENCE and not a measurement")

    sections = failure_sections(log)
    unattributed = []
    for t in graded:
        body = sections_for(sections, t)
        if body is None or not names_symbol(body, symbol):
            unattributed.append(t if body is not None
                                else "%s (no failure block)" % t)
    checks["every_graded_test_reaches_the_symbol"] = not unattributed
    if unattributed:
        why.append("%d graded test(s) do not name the symbol in their own "
                   "failure block: %s" % (len(unattributed), unattributed[:3]))

    ok = all(checks.values())
    return ok, checks, why


def reset(spec, local_files=None):
    sh("git checkout -- . && git clean -fdq", check=True)
    sh("find . -name __pycache__ -type d -prune -exec rm -rf {} + "
       "; find . -name '*.pyc' -delete")
    sh("git apply --whitespace=nowarn /tmp/tests.diff", check=True)
    sh("git apply --whitespace=nowarn /tmp/gold.diff", check=True)
    for path, text in (local_files or {}).items():
        put("%s/%s" % (WORKDIR, path), text)


def run_task(instance_id, symbol, by_id):
    from container_task import build_task_spec
    from images import image_ref
    spec = build_task_spec(by_id[instance_id])
    image = image_ref(instance_id)
    row = {"task": instance_id, "symbol": symbol, "image": image}

    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, text=True)
    subprocess.run(["docker", "run", "-d", "--name", CONTAINER, "-w", WORKDIR,
                    image, "sleep", "infinity"], check=True,
                   capture_output=True, text=True)
    try:
        put("/tmp/gold.diff", spec["gold_diff"])
        put("/tmp/tests.diff", spec["tests_diff"])

        # which test files name the symbol
        reset(spec)
        test_files = sh("grep -rl '\\b%s\\b' --include='*.py' . "
                        "| grep -E '/tests?/|/testing/' | sort" % symbol).stdout.split()
        row["test_files"] = test_files
        if not test_files:
            row["outcome"] = "not_applicable"
            row["reason"] = "no test file references the symbol"
            return row

        # transform each, on the host
        local = {}
        try:
            for path in test_files:
                src = sh("cat '%s'" % path, check=True).stdout
                local[path] = import_local(src, symbol)
        except NotApplicable as exc:
            row["outcome"] = "not_applicable"
            row["reason"] = str(exc)
            return row
        except SyntaxError as exc:
            row["outcome"] = "not_applicable"
            row["reason"] = "could not parse %s: %s" % (path, exc)
            return row

        # CONTROL: rename only. Must reproduce the witness.
        reset(spec)
        ctl_ev = rename_everywhere(symbol, symbol + "__renamed")
        row["renamed_files"] = ctl_ev["files"]
        ctl, _ = grade(spec)
        row["control_reported"] = len(ctl["reported"])
        row["n_graded"] = ctl["n_graded"]
        row["control_reward"] = ctl["grade"]["reward"]
        if ctl["reported"]:
            row["outcome"] = "control_did_not_reproduce"
            row["reason"] = ("the rename left %d graded node id(s) reported; the "
                             "witness had none, so this rename set differs from "
                             "the operator's" % len(ctl["reported"]))
            return row

        # MEASURED: import_local + the same rename.
        reset(spec, local)
        rename_ev = rename_everywhere(symbol, symbol + "__renamed")
        got, mlog = grade(spec)
        k = len(got["failing"])
        recovery = got["n_graded"] - k
        row.update({
            "outcome": "measured",
            "k": k,
            "recovery": recovery,
            "reward": got["grade"]["reward"],
            "failing_after": got["failing"][:12],
            "reported_after": len(got["reported"]),
        })
        if recovery == 0:
            ok, checks, why = classify_zero(symbol, rename_ev, got, mlog, spec)
            row["zero_checks"] = checks
            if ok:
                row["outcome"] = "helper_coupled"
                row["reason"] = (
                    "every graded test reaches %s through a shared helper rather "
                    "than the module-scope import: the rename is a verified "
                    "alpha-rename, the module loaded (%d graded id(s) reported), "
                    "and every graded test's own failure block names the symbol. "
                    "No placement of that import can change this."
                    % (symbol, len(got["reported"])))
            else:
                row["outcome"] = "recovery_zero_defect"
                row["reason"] = "; ".join(why)
        return row
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER],
                       capture_output=True, text=True)
        subprocess.run(["docker", "rmi", image], capture_output=True, text=True)


def all_fail_witnesses():
    out = []
    for name in sorted(os.listdir(RECORDS)):
        rec = json.load(open(os.path.join(RECORDS, name), encoding="utf-8"))
        for w in rec.get("witnesses") or []:
            g = w["graded_report"]
            if not g["f2p_pass"] and not g["p2p_pass"]:
                out.append((rec["instance_id"], w["anchor"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip", action="append", default=[])
    args = ap.parse_args()

    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}

    todo = all_fail_witnesses()
    if args.task:
        todo = [t for t in todo if t[0] in args.task]
    todo = [t for t in todo if t[0] not in args.skip]

    rows = []
    if os.path.exists(OUT):
        rows = json.load(open(OUT))
    done = {(r["task"], r["symbol"]) for r in rows}

    for instance_id, symbol in todo:
        # `done` is updated in the loop, not only seeded from the file. A task
        # with the same symbol on two files -- sphinx-7590 carries
        # `DefinitionParser` in both c.py and cpp.py -- appears twice in the
        # witness rows, and this measurement is per (task, symbol): the rename
        # covers both files either way. Without the update it ran twice, spent a
        # second container, and put a byte-identical duplicate in the artifact
        # that any aggregate would have counted twice.
        if (instance_id, symbol) in done:
            continue
        done.add((instance_id, symbol))
        print("  %-34s %-22s ..." % (instance_id, symbol), flush=True)
        try:
            row = run_task(instance_id, symbol, by_id)
        except Exception as exc:                       # noqa: BLE001
            row = {"task": instance_id, "symbol": symbol,
                   "outcome": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
        rows.append(row)
        json.dump(rows, open(OUT, "w"), indent=2)      # unconditional, per row
        print("      -> %s %s" % (row["outcome"],
                                  {k: row[k] for k in ("k", "recovery", "n_graded")
                                   if k in row}), flush=True)
        if row["outcome"] == "helper_coupled":
            print("      -- recovery 0, and all four checks hold: the coupling is a "
                  "shared helper, not the module-scope import. Classified, not stopped.")
        if row["outcome"] == "recovery_zero_defect":
            print("      !! recovery 0 and the four checks do NOT hold: %s"
                  % row.get("reason", "")[:160])
            print("      !! treating as a defect and stopping.")
            return 1
        if row["outcome"] in ("control_did_not_reproduce", "error"):
            print("      !! %s -- stopping." % row["outcome"])
            return 1
    print("\n-> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
