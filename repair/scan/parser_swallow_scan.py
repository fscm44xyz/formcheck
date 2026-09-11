"""Does a swallowed status line count a PASSING graded test as failing?

THE SHAPE. Django's verbose runner writes one line per test, `name ... STATUS`.
A test whose status is never written leaves its line unterminated, and the next
test's line is appended to it:

    test_options_override... (...) ... test_parameters (...) ... ERROR

`parse_log_django` handles this line twice and gets it wrong both times:
`prev_test` takes `line.split(" ... ")[0]`, and the status branch takes
`line.split(" ... ERROR")[0]` -- which is the WHOLE prefix, `A (...) ... B (...)`.
So the map gains a key that no test id can equal, and BOTH test ids are absent
from it. Upstream `test_passed` is `case in status_map and status_map[case] in
(PASSED, XFAIL)`, so an absent id is counted as failing.

If the swallowed line had ended in `ok` rather than `ERROR`, that is a PASSING
graded test counted as failing -- and for `formcheck` a false failure is a false
witness.

CAN THE PARSER TELL THE TWO CASES APART? Not while parsing, but the evidence
survives in its output. A test id never contains " ... ", so a key that does is a
consumed line rather than a real result, and the ids inside it are recoverable.
That is the detector here:

    swallowed(id)  <=>  id not in status_map
                        and id is a substring of some other key

TRUE STATUS OF A SWALLOWED ID.
  * the id that is a SUFFIX of the merged key was last on the line, so the
    status the parser recorded against the merged key is its status.
  * an id earlier on the line never had a status written. unittest prints a
    `FAIL:`/`ERROR:` block for every failure, so an earlier id with no such
    block PASSED silently.

Both directions are counted separately. Reads only `scale/records_m4/`; no
container, no network, no model.

    ~/.venv-fc/bin/python repair/scan/parser_swallow_scan.py
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "scale"), os.path.join(ROOT, "repro")):
    if p not in sys.path:
        sys.path.insert(0, p)

import swebench_shim  # noqa: F401,E402
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS  # noqa: E402
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER  # noqa: E402

RECORDS = os.path.join(ROOT, "scale", "records_m4")
OUT = os.path.join(HERE, "parser_swallow_scan.json")
PASSING = ("PASSED", "XFAIL")


def logs_of(rec):
    """Every stored log on a record, tagged by where it came from."""
    out = []
    ctl = (rec.get("control") or {}).get("log")
    if ctl:
        out.append(("control", None, ctl))
    for i, row in enumerate(rec.get("rows") or []):
        if row.get("graded_log"):
            out.append((row.get("verdict") or "?", row.get("anchor"), row["graded_log"]))
    return out


def scan_log(log, repo, version, graded):
    """-> (merged_keys, [swallowed row], n_absent) for one log."""
    parser = MAP_REPO_TO_PARSER[repo]
    cmd = MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]
    if isinstance(cmd, list):
        cmd = cmd[-1]
    tail = log.split(cmd)[-1]
    sm = parser(tail, None)

    absent = [g for g in graded if g not in sm]
    merged = {k: v for k, v in sm.items() if " ... " in k}
    if not merged:
        return {}, [], len(absent)

    rows = []
    for key, status in merged.items():
        inside = [g for g in graded if g != key and g in key]
        for gid in inside:
            if gid in sm:
                continue                      # recorded elsewhere; not lost
            last = key.endswith(gid)
            if last:
                truth, how = status, "status recorded against the merged key"
            else:
                # unittest prints a block for every failure; no block => passed.
                pat = re.compile(r"^(FAIL|ERROR):\s+%s\b" % re.escape(gid.split(" (")[0]),
                                 re.M)
                blocks = [m.group(1) for m in pat.finditer(tail)]
                if blocks:
                    truth, how = ("FAILED" if blocks[0] == "FAIL" else "ERROR",
                                  "recovered from its %s: block" % blocks[0])
                else:
                    truth, how = "PASSED", "no FAIL:/ERROR: block anywhere in the log"
            rows.append({
                "graded_id": gid, "merged_key": key[:180],
                "position": "last on line" if last else "earlier on line",
                "true_status": truth, "how": how,
                "counted": "failing",
                "false_failure": truth in PASSING,
            })
    return merged, rows, len(absent)


def main():
    files = sorted(f for f in os.listdir(RECORDS) if f.endswith(".json"))
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}

    results, n_logs = [], 0
    n_absent_total = 0
    logs_with_absent = 0
    for name in files:
        rec = json.load(open(os.path.join(RECORDS, name), encoding="utf-8"))
        iid = rec["instance_id"]
        inst = by_id[iid]
        graded = json.loads(inst["FAIL_TO_PASS"]) + json.loads(inst["PASS_TO_PASS"])
        is_witness = bool(rec.get("witnesses"))
        for where, anchor, log in logs_of(rec):
            n_logs += 1
            try:
                merged, rows, n_absent = scan_log(log, rec["repo"], rec["version"], graded)
                n_absent_total += n_absent
                logs_with_absent += 1 if n_absent else 0
            except Exception as exc:                       # noqa: BLE001
                results.append({"task": iid, "where": where, "anchor": anchor,
                                "error": "%s: %s" % (type(exc).__name__, exc)})
                continue
            if merged:
                results.append({
                    "task": iid, "repo": rec["repo"], "where": where,
                    "anchor": anchor, "is_witness_task": is_witness,
                    "n_merged_keys": len(merged),
                    "merged_keys": [k[:180] for k in merged],
                    "swallowed": rows,
                })

    json.dump({"logs_scanned": n_logs, "records": len(files),
               "absent_graded_ids": n_absent_total,
               "logs_with_absent_ids": logs_with_absent,
               "hits": results}, open(OUT, "w"), indent=1)

    print("logs scanned: %d   across %d records\n" % (n_logs, len(files)))
    hits = [r for r in results if "swallowed" in r]
    errs = [r for r in results if "error" in r]
    if errs:
        print("logs the scan could not parse: %d" % len(errs))
        for e in errs[:5]:
            print("   %-34s %s" % (e["task"], e["error"][:80]))
        print()

    if not hits:
        print("No merged status line in any stored log.")
    else:
        print("%-34s %-14s %-24s %-9s %s"
              % ("task", "log", "swallowed graded id", "true", "counted"))
        print("-" * 104)
        for h in hits:
            for s in h["swallowed"]:
                print("%-34s %-14s %-24s %-9s %s%s"
                      % (h["task"], h["where"], s["graded_id"].split(" (")[0][:24],
                         s["true_status"], s["counted"],
                         "   <-- FALSE FAILURE" if s["false_failure"] else ""))
        print("-" * 104)

    sw = [s for h in hits for s in h["swallowed"]]
    false_fail = [s for s in sw if s["false_failure"]]
    tasks = {h["task"] for h in hits}
    wtasks = {h["task"] for h in hits if h.get("is_witness_task")}
    ftasks = {h["task"] for h in hits for s in h["swallowed"] if s["false_failure"]}
    print("\nIS THE ZERO VACUOUS? Absence is what the detector discriminates, so it")
    print("has to be present for a zero to mean anything.")
    print("  graded logs parsed                     : %d" % n_logs)
    print("  logs with at least one absent graded id: %d" % logs_with_absent)
    print("  absent graded ids, total               : %d" % n_absent_total)
    print("  of those, carrying the merging signature: %d" % len(sw))
    print("\ntasks with a merged status line          : %d of %d" % (len(tasks), len(files)))
    print("of those, among the 28 witness tasks     : %d" % len(wtasks))
    print("swallowed graded ids                     : %d" % len(sw))
    print("swallowed ids whose log shows them PASSING")
    print("  -- counted failing, a FALSE FAILURE    : %d  (in %d task(s))"
          % (len(false_fail), len(ftasks)))
    if wtasks:
        print("\nwitness tasks affected:")
        for t in sorted(wtasks):
            print("   ", t)
    print("\n-> %s" % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
