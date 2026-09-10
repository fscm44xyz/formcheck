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

`recovery == 0` on a task whose control reproduced is treated as a DEFECT and
stops the run: it cannot happen if the import is what couples the module.

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
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "scale"), os.path.join(ROOT, "repro")):
    if p not in sys.path:
        sys.path.insert(0, p)

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
    """Rename across production sources, then verify no residue -- the M0d guard."""
    files = sh("grep -rl '\\b%s\\b' --include='*.py' . "
               "| grep -v '/tests\\?/' | grep -v '/testing/' | sort" % symbol).stdout.split()
    if not files:
        raise RuntimeError("no production file references %s" % symbol)
    for path in files:
        src = sh("cat '%s'" % path, check=True).stdout
        put("%s/%s" % (WORKDIR, path), src.replace(symbol, new))
    residue = sh("grep -rl '\\b%s\\b' --include='*.py' . "
                 "| grep -v '/tests\\?/' | grep -v '/testing/' | sort" % symbol).stdout.split()
    if residue:
        raise RuntimeError("incomplete rename of %s: residue in %s"
                           % (symbol, residue))
    return files


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
        row["renamed_files"] = rename_everywhere(symbol, symbol + "__renamed")
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
        rename_everywhere(symbol, symbol + "__renamed")
        got, _ = grade(spec)
        k = len(got["failing"])
        row.update({
            "outcome": "measured",
            "k": k,
            "recovery": got["n_graded"] - k,
            "reward": got["grade"]["reward"],
            "failing_after": got["failing"][:12],
            "reported_after": len(got["reported"]),
        })
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
        if (instance_id, symbol) in done:
            continue
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
        if row["outcome"] == "measured" and row["recovery"] == 0:
            print("      !! recovery 0 with a reproduced control -- impossible if "
                  "the import is the coupling. Treating as a defect and stopping.")
            return 1
        if row["outcome"] in ("control_did_not_reproduce", "error"):
            print("      !! %s -- stopping." % row["outcome"])
            return 1
    print("\n-> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
