"""Blast radius of the boundary defect across the 28 witness tasks.

The two substring branches in `SymbolRename` could land a rewrite inside a
longer identifier. A task hit that way had its DEFINITION renamed and its IMPORT
left behind, which fails with `cannot import name '<anchor>'` -- text naming the
anchor, so `names_symbol` read it as coupling and the row came back WITNESS. In
the records a witness produced that way is indistinguishable from a genuine one,
which is why this cannot be settled by reading them.

WHAT THIS MEASURES. For each recorded witness row, the task's production tree is
rebuilt offline -- base commit + tests.diff + gold.diff, the same tree
`formcheck_read` saw -- and the anchor is re-derived and applied twice:

    OLD   repro/f2_operators.py at 189451b, the code that produced the run
    NEW   repro/f2_operators.py at HEAD, both branches taking AST spans

The recorded rename was well-formed if and only if the two agree byte for byte
on every file. This is a direct comparison of what the published run's operator
did against what a correct one does; it does not go through the round-trip
invariant, which is a check on one operator's output rather than a comparison
between two.

    witness stands   OLD == NEW; the rename was well-formed, so the WITNESS
                     verdict does not rest on a broken rewrite.
    witness void     they differ, or NEW refuses where OLD did not. The recorded
                     rewrite was not an alpha-rename and the row is void.
    undetermined     the tree could not be rebuilt, or the reconstruction does
                     not reproduce the recorded run. NOT counted either way.

The third bucket is a real answer and is reported as one. A task whose tree
cannot be rebuilt is not evidence that its witness stands.

Raw per-task table only. No corrected rate is computed here: 34 rows over 28
tasks is not the denominator any published number uses, and re-deriving one
belongs to whoever decides what the number should now mean.

    FORMCHECK_REPO_CACHE=<dir> ~/.venv-fc/bin/python repair/scan/blast_radius_28.py
    ... repair/scan/blast_radius_28.py requests xarray   # a subset, by substring

Needs network for the clones; needs no Docker and no model.
"""

import hashlib
import json
import os
import subprocess
import sys
import glob
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "repro"))
sys.path.insert(0, os.path.join(ROOT, "scale"))

OLD_REV = "189451b"
CACHE = os.environ.get("FORMCHECK_REPO_CACHE",
                       os.path.expanduser("~/.cache/formcheck-blast"))
RESULT = os.path.join(HERE, "BLAST_RADIUS_28.json")

STANDS, VOID, UNDET = "witness stands", "witness void", "undetermined"

# The tree walk `scale/container_task.py` runs inside the container, verbatim in
# behaviour: whole repository, production .py only, test-ish directories and
# test files excluded.
HINTS = {"test", "tests", "testing", "doc", "docs"}


def read_tree(root):
    out = {}
    for dirpath, dirs, files in os.walk(root):
        rel_root = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_root == ".":
            rel_root = ""
        parts = [p.lower() for p in rel_root.split("/") if p]
        if any(p in HINTS or p.startswith(".") for p in parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in HINTS]
        for fn in files:
            if (not fn.endswith(".py") or fn.startswith("test_")
                    or fn.endswith("_test.py") or fn == "conftest.py"):
                continue
            rel = (rel_root + "/" + fn) if rel_root else fn
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    out[rel] = f.read()
            except Exception:
                continue
    return out


def sh(args, cwd=None, check=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("%s: %s" % (" ".join(args[:3]), (r.stderr or r.stdout).strip()[:300]))
    return r


def load_old_operator():
    """`SymbolRename` as it stood at OLD_REV -- the code that produced the run."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "f2_operators_old.py")
    src = sh(["git", "show", "%s:repro/f2_operators.py" % OLD_REV], cwd=ROOT, check=True).stdout
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("f2_operators_old", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_repo(repo):
    """One blobless clone per repo; commits are fetched on demand."""
    d = os.path.join(CACHE, repo.replace("/", "__"))
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(d, exist_ok=True)
        sh(["git", "init", "-q"], cwd=d, check=True)
        sh(["git", "remote", "add", "origin", "https://github.com/%s.git" % repo],
           cwd=d, check=True)
    return d


def materialise(repo, base_commit, tests_diff, gold_diff):
    """base commit + tests.diff + gold.diff, the tree formcheck_read saw."""
    d = ensure_repo(repo)
    if sh(["git", "cat-file", "-e", base_commit + "^{commit}"], cwd=d).returncode != 0:
        r = sh(["git", "fetch", "--filter=blob:none", "--no-tags", "-q",
                "origin", base_commit], cwd=d)
        if r.returncode != 0:
            r = sh(["git", "fetch", "--filter=blob:none", "--no-tags", "-q", "origin"], cwd=d)
            if r.returncode != 0:
                raise RuntimeError("fetch failed: %s" % (r.stderr or "").strip()[:200])
    sh(["git", "checkout", "-f", "-q", base_commit], cwd=d, check=True)
    sh(["git", "clean", "-fdqx"], cwd=d)
    for name, diff in (("tests.diff", tests_diff), ("gold.diff", gold_diff)):
        p = os.path.join(CACHE, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(diff)
        r = sh(["git", "apply", "--whitespace=nowarn", p], cwd=d)
        if r.returncode != 0:
            raise RuntimeError("apply %s: %s" % (name, (r.stderr or "").strip()[:200]))
    return d


def tree_digest(contents, paths, root):
    """`_tree_digest` as the 500-task run computed it.

    One `sha256sum`-shaped line per digested path, hashed together. The run
    predates the repair-M0a widening, so the digested paths are the targets
    alone -- the test files are NOT included, and adding them here would produce
    a digest that could never match a recorded one.
    """
    lines = []
    for t in paths:
        if t in contents:
            lines.append("%s  %s" % (
                hashlib.sha256(contents[t].encode("utf-8")).hexdigest(), t))
        else:
            f = os.path.join(root, t)
            if os.path.isfile(f):
                with open(f, "rb") as fh:
                    lines.append("%s  %s" % (hashlib.sha256(fh.read()).hexdigest(), t))
            else:
                lines.append("MISSING %s" % t)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def classify(old_mod, new_mod, sources, target, anchor, issue):
    """Compare the two operators on one recorded witness row."""
    def run(mod):
        try:
            out, _rep = mod.SymbolRename().apply(dict(sources), target, anchor, issue)
            return ("applied", out)
        except mod.Refused as exc:
            return ("refused", str(exc))
        except Exception as exc:                       # noqa: BLE001
            return ("error", "%s: %s" % (type(exc).__name__, exc))

    old_kind, old_val = run(old_mod)
    new_kind, new_val = run(new_mod)
    detail = {"old": old_kind, "new": new_kind,
              "old_out": old_val if old_kind == "applied" else None}

    if old_kind == "applied" and new_kind == "applied":
        if old_val == new_val:
            # Two operators agreeing on a tree neither of them touched is not
            # evidence that a rename was well-formed -- it is evidence that no
            # rename happened, which means the reconstruction is not the tree
            # the run saw. Counting it as "stands" would be a check reporting a
            # verdict for a reason invisible in its own output.
            changed = [p for p in new_val if new_val[p] != sources.get(p)]
            if not changed:
                return UNDET, "both applied but changed no file -- no rename to judge", detail
            return STANDS, "old and new agree byte for byte, %d file(s) rewritten" % len(changed), detail
        differing = sorted(p for p in set(old_val) | set(new_val)
                           if old_val.get(p) != new_val.get(p))
        return VOID, "rewrite differs in %d file(s): %s" % (
            len(differing), ", ".join(differing[:3])), detail
    if old_kind == "applied" and new_kind == "refused":
        return VOID, "corrected operator refuses: %s" % new_val[:160], detail
    if old_kind == "refused":
        # The record says this row applied and produced a witness. If the
        # operator that produced the run refuses on the rebuilt tree, the
        # reconstruction is not the tree it saw, and nothing about the recorded
        # rename follows from it.
        return UNDET, "reconstruction does not reproduce the run (old refused: %s)" % old_val[:120], detail
    return UNDET, "old %s / new %s: %s" % (old_kind, new_kind, str(old_val)[:120]), detail


POSITIVE_CONTROL = [
    ("superstring FIRST on the import line",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.mod import BaseFoo, Foo\n\n\ndef go():\n    return Foo()\n"}),
    ("symbol as a substring of the MODULE path",
     {"pkg/mod.py": "class Foo:\n    pass\n",
      "pkg/use.py": "from pkg.Foolib import Foo\n\n\ndef go():\n    return Foo()\n"}),
]


def positive_control(old_mod, new_mod):
    """Can this comparison say VOID at all?

    Every row coming back in one bucket is only a finding if the other buckets
    were reachable. These two shapes are ones the OLD operator provably corrupts
    and the NEW one does not, pushed through the SAME `classify` the 34 rows go
    through. If they do not come back VOID, the measurement is not discriminating
    and its result means nothing.
    """
    ok = True
    print("positive control -- shapes the old operator corrupts:")
    for label, sources in POSITIVE_CONTROL:
        anchor = {"label": "Foo", "name": "Foo", "tier": "MEDIUM", "file": "pkg/mod.py"}
        bucket, note, _d = classify(old_mod, new_mod, sources, "pkg/mod.py", anchor,
                                    "an issue naming nothing")
        print("   %-16s %-38s %s" % (bucket, label, note[:70]))
        if bucket != VOID:
            ok = False
    print("   -> the comparison %s report VOID\n" % ("CAN" if ok else "CANNOT"))
    return ok


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}

    import f2_operators as new_mod
    old_mod = load_old_operator()

    if not positive_control(old_mod, new_mod):
        print("ABORT: the comparison cannot distinguish a corrupted rename from a")
        print("well-formed one, so no per-task verdict below would mean anything.")
        return 2

    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    tasks = []
    for f in sorted(glob.glob(os.path.join(ROOT, "scale", "records_m4", "*.json"))):
        rec = json.load(open(f))
        if not rec.get("witnesses"):
            continue
        if only and not any(o in rec["instance_id"] for o in only):
            continue
        tasks.append(rec)
    print("witness tasks: %d   witness rows: %d\n"
          % (len(tasks), sum(len(t["witnesses"]) for t in tasks)))

    results = []
    for i, rec in enumerate(tasks, 1):
        iid = rec["instance_id"]
        inst = by_id[iid]
        print("[%2d/%d] %s" % (i, len(tasks), iid), flush=True)
        try:
            d = materialise(rec["repo"], inst["base_commit"],
                            inst["test_patch"], inst["patch"])
            sources = read_tree(d)
        except Exception as exc:                       # noqa: BLE001
            for w in rec["witnesses"]:
                results.append({"instance_id": iid, "anchor": w["anchor"],
                                "file": w.get("file"), "bucket": UNDET,
                                "note": "tree not rebuilt: %s" % str(exc)[:200]})
                print("        %-16s %s  -- %s" % (UNDET, w["anchor"], str(exc)[:90]))
            continue

        for w in rec["witnesses"]:
            name, target = w["anchor"], w.get("file") or rec["targets"][0]
            if target not in sources:
                results.append({"instance_id": iid, "anchor": name, "file": target,
                                "bucket": UNDET,
                                "note": "target %s absent from the rebuilt tree" % target})
                print("        %-16s %s  -- target absent" % (UNDET, name))
                continue
            cands = [a for a in new_mod.SymbolRename().anchors(sources, target, inst["problem_statement"])
                     if a["name"] == name]
            if not cands:
                results.append({"instance_id": iid, "anchor": name, "file": target,
                                "bucket": UNDET,
                                "note": "anchor %r not re-derived in %s" % (name, target)})
                print("        %-16s %s  -- anchor not re-derived" % (UNDET, name))
                continue
            anchor = dict(cands[0])
            anchor["file"] = target
            bucket, note, detail = classify(old_mod, new_mod, sources, target, anchor,
                                            inst["problem_statement"])
            # CORROBORATION. If applying the OLD operator to the rebuilt tree
            # reproduces the digest this row recorded, then the rewrite being
            # compared IS the rewrite the run made -- not a reconstruction that
            # merely resembles it. Where it does not, the comparison is between
            # something else and the corrected operator, and says nothing about
            # the recorded rename.
            reproduced = None
            if detail["old_out"] is not None:
                got = tree_digest(detail["old_out"], rec["targets"], d)
                reproduced = (got == w.get("tree_digest"))
                if not reproduced and bucket != UNDET:
                    bucket = UNDET
                    note = ("old operator does not reproduce the recorded digest "
                            "for this row (%s != %s)" % (got[:12], str(w.get("tree_digest"))[:12]))
            results.append({"instance_id": iid, "anchor": name, "file": target,
                            "bucket": bucket, "note": note,
                            "recorded_rewrite_reproduced": reproduced})
            print("        %-16s %s  -- %s" % (bucket, name, note[:90]))

    if only:
        print("\nFILTERED RUN (%s) -- %s not written."
              % (", ".join(only), os.path.relpath(RESULT, ROOT)))
    else:
        with open(RESULT, "w", encoding="utf-8") as f:
            json.dump({"old_rev": OLD_REV, "rows": results}, f, indent=1, sort_keys=True)

    print("\n" + "=" * 78)
    print("%-32s %-24s %-30s %s"
          % ("task", "anchor", "file", "recorded rename"))
    print("-" * 110)
    for r in results:
        print("%-32s %-24s %-30s %s"
              % (r["instance_id"], r["anchor"], r["file"] or "", r["bucket"]))
    print("-" * 110)
    repro_ok = sum(1 for r in results if r.get("recorded_rewrite_reproduced") is True)
    print("recorded rewrite reproduced from the rebuilt tree: %d of %d rows"
          % (repro_ok, len(results)))
    print("-" * 110)
    counts = {b: sum(1 for r in results if r["bucket"] == b) for b in (STANDS, VOID, UNDET)}
    tasks_in = {b: len({r["instance_id"] for r in results if r["bucket"] == b})
                for b in (STANDS, VOID, UNDET)}
    for b in (STANDS, VOID, UNDET):
        print("%-16s rows %2d   tasks %2d" % (b, counts[b], tasks_in[b]))
    print("rows %d over %d tasks" % (len(results), len({r["instance_id"] for r in results})))
    print("\nCounted separately and not combined. No corrected rate is derived here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
