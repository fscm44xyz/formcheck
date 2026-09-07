"""Grade all M1 logs with the real swebench grader and print the G1-G4 table.
Runs under .venv (swebench + Windows shim)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import swebench_shim  # noqa

from swebench.harness.constants import (
    APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT,
    FAIL_ONLY_REPOS, FAIL_TO_PASS, PASS_TO_PASS, KEY_INSTANCE_ID,
    MAP_REPO_VERSION_TO_SPECS, EvalType, ResolvedStatus,
)
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.grading import get_eval_tests_report, get_resolution_status

HERE = os.path.dirname(__file__)
meta = json.load(open(os.path.join(HERE, "meta.json")))
repo, version = meta["repo"], meta["version"]

def grade(name):
    log = open(os.path.join(HERE, f"log_m1_{name}.txt"), encoding="utf-8").read()
    parser = MAP_REPO_TO_PARSER[repo]
    test_cmd = MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]
    if isinstance(test_cmd, list):
        test_cmd = test_cmd[-1]
    content = log.split(test_cmd)[-1]
    status_map = parser(content, None)
    eval_ref = {KEY_INSTANCE_ID: meta["instance_id"],
                FAIL_TO_PASS: meta["FAIL_TO_PASS"], PASS_TO_PASS: meta["PASS_TO_PASS"]}
    et = EvalType.FAIL_ONLY if repo in FAIL_ONLY_REPOS else EvalType.PASS_AND_FAIL
    report = get_eval_tests_report(status_map, eval_ref, eval_type=et)
    reward = float(get_resolution_status(report) == ResolvedStatus.FULL.value)
    f2p, p2p = report["FAIL_TO_PASS"], report["PASS_TO_PASS"]
    return reward, len(f2p["success"]), len(f2p["failure"]), len(p2p["success"]), len(p2p["failure"])

CASES = [
    ("gold",      "G1 positive preservation", 1.0),
    ("alt",       "G3 false-neg recovery",    1.0),
    ("bug_none",  "G2 neg (pre-patch MRO bug)", 0.0),
    ("bug_direct","G2 neg (own marks only)",    0.0),
    ("bug_first", "G2 neg (first base only)",   0.0),
    ("bug_dropown","G2 neg (drops own class)",  0.0),
]

print(f"Task: {meta['instance_id']}   (repaired test_mark_mro, behavioral)")
print(f"{'solution':12s} {'gate':30s} {'F2P s/f':8s} {'P2P s/f':9s} {'reward':7s} {'expect':7s} verdict")
print("-" * 92)
allok = True
for name, gate, expect in CASES:
    r, fs, ff, ps, pf = grade(name)
    ok = (r == expect)
    allok &= ok
    print(f"{name:12s} {gate:30s} {fs}/{ff:<6d} {ps}/{pf:<7d} {r:<7} {expect:<7} {'OK' if ok else 'MISMATCH'}")
print("-" * 92)
print("ALL GATES PASS" if allok else "SOME GATE FAILED -- investigate")
