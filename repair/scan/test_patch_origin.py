"""Does the benchmark's own test patch INTRODUCE the coupled reference?

Static. No Docker, no model, no inference beyond reading unified diffs.

For each witness (task, coupled symbol), ask where the test tree's reference to
that symbol comes from:

  introduced    the symbol appears on a `+` line of the task's test_patch, in a
                file that already existed. The benchmark added the coupling.
  new_file      the symbol appears on a `+` line, but the test_patch CREATES that
                file (`--- /dev/null`). Everything in such a file is "introduced"
                by construction, so it says nothing about whether the benchmark
                added coupling to existing tests. Counted separately, never
                folded in.
  pre_existing  the symbol appears in the test_patch only on context or `-`
                lines, or does not appear in it at all -- the reference is in the
                repository's test tree already.
  mixed         both: some `+` lines and some context/`-` lines reference it.

For introduced/new_file, where the `+` reference sits:

  module_import   a module-scope `from ... import` / `import` (including the
                  continuation lines of a parenthesised import)
  local_import    an indented import, inside a function or method
  in_test         any other reference -- a call, an attribute, an argument

`pre_existing` is asserted, not assumed: a graded test that fails on the rename
must reference the symbol somewhere, so if the test_patch never adds it, the
reference was already there.

    ~/.venv-fc/bin/python repair/scan/test_patch_origin.py
    ~/.venv-fc/bin/python repair/scan/test_patch_origin.py --json out.json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scale"))
sys.path.insert(0, os.path.join(ROOT, "repro"))

RECORDS = os.path.join(ROOT, "scale", "records_m4")
_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def split_files(patch):
    """`[(path, is_new, [lines])]` -- one entry per file the diff touches."""
    out, path, lines, is_new = [], None, [], False
    for line in patch.splitlines():
        m = _DIFF_GIT.match(line)
        if m:
            if path is not None:
                out.append((path, is_new, lines))
            path = m.group(1) if m.group(2) == "/dev/null" else m.group(2)
            lines, is_new = [], False
            continue
        if path is None:
            continue
        if line.startswith("--- ") and line[4:].strip() == "/dev/null":
            is_new = True
        lines.append(line)
    if path is not None:
        out.append((path, is_new, lines))
    return out


def classify(patch, symbol):
    """Where the test patch references `symbol`, and how.

    The import-block state machine walks the POST-IMAGE -- context lines plus
    added lines, in order -- not the added lines alone. A parenthesised import
    can have an unchanged head and an added continuation, and reading only `+`
    lines classifies that continuation as an in-test reference. `django-12155`
    is exactly that shape: the head `from django.contrib.admindocs.utils import (`
    is context and `parse_docstring` arrives on an added continuation line.
    """
    word = re.compile(rf"\b{re.escape(symbol)}\b")
    added, context, kinds, files_added = [], [], set(), set()

    for path, is_new, lines in split_files(patch):
        open_import, head_indented = False, False
        for raw in lines:
            if raw.startswith(("+++", "---", "@@", "index ", "new file",
                               "deleted file", "similarity", "rename ")):
                continue
            if raw.startswith("-"):
                # pre-image only: it cannot affect the post-image import state
                if word.search(raw[1:]):
                    context.append((path, raw[1:]))
                continue
            if not raw.startswith(("+", " ")):
                continue

            body = raw[1:]
            is_added = raw.startswith("+")
            stripped = body.strip()
            is_import_head = re.match(r"^\s*(from|import)\b", body) is not None
            indented = body[:1] in (" ", "\t")

            if word.search(body):
                if is_added:
                    added.append((path, is_new, body))
                    files_added.add((path, is_new))
                    if is_import_head:
                        kinds.add("local_import" if indented else "module_import")
                    elif open_import:
                        kinds.add("local_import" if head_indented else "module_import")
                    else:
                        kinds.add("in_test")
                else:
                    context.append((path, body))

            # post-image import-block state
            if is_import_head and "(" in stripped and ")" not in stripped:
                open_import, head_indented = True, indented
            elif open_import and ")" in stripped:
                open_import = False

    if added and context:
        origin = "mixed"
    elif added:
        origin = "new_file" if all(new for _, new in files_added) else "introduced"
    else:
        origin = "pre_existing"
    return origin, sorted(kinds), added, context


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}

    rows = []
    for name in sorted(os.listdir(RECORDS)):
        rec = json.load(open(os.path.join(RECORDS, name), encoding="utf-8"))
        for w in rec.get("witnesses") or []:
            inst = by_id[rec["instance_id"]]
            origin, kinds, added, context = classify(inst["test_patch"], w["anchor"])
            rows.append({
                "task": rec["instance_id"], "repo": rec["repo"],
                "symbol": w["anchor"], "origin": origin, "kinds": kinds,
                "n_added_lines": len(added), "n_context_lines": len(context),
                "added_lines": [b.rstrip() for _, _, b in added][:6],
            })
    return rows, args.json


if __name__ == "__main__":
    rows, out = main()
    print(f"{len(rows)} witness (task, symbol) pairs across "
          f"{len({r['task'] for r in rows})} tasks\n")
    print(f"{'task':34s} {'symbol':24s} {'origin':13s} {'where the + line sits':28s} +/ctx")
    for r in rows:
        print(f"{r['task']:34s} {r['symbol']:24s} {r['origin']:13s} "
              f"{','.join(r['kinds']) or '-':28s} {r['n_added_lines']}/{r['n_context_lines']}")
    if out:
        json.dump(rows, open(out, "w"), indent=2)
        print(f"\n-> {out}")
