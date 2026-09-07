"""Grade a captured log EXACTLY as SWEBenchTaskSet._calculate_reward does.

  python grade.py log_gold.txt

Uses the real swebench grading primitives (log parser + get_eval_tests_report +
get_resolution_status). Runs under .venv (swebench installed, Windows shim).
"""
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

def get_logs_eval(content):
    parser = MAP_REPO_TO_PARSER[repo]
    test_cmd = MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]
    if isinstance(test_cmd, list):
        test_cmd = test_cmd[-1]
    if [c for c in (APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT) if c in content]:
        return {}, False
    content = content.split(test_cmd)[-1]
    return parser(content, None), True

def main():
    log = open(os.path.join(HERE, sys.argv[1]), encoding="utf-8").read()
    status_map, found = get_logs_eval(log)
    eval_ref = {
        KEY_INSTANCE_ID: meta["instance_id"],
        FAIL_TO_PASS: meta["FAIL_TO_PASS"],
        PASS_TO_PASS: meta["PASS_TO_PASS"],
    }
    eval_type = EvalType.FAIL_ONLY if repo in FAIL_ONLY_REPOS else EvalType.PASS_AND_FAIL
    report = get_eval_tests_report(status_map, eval_ref, eval_type=eval_type)
    reward = float(get_resolution_status(report) == ResolvedStatus.FULL.value)

    f2p = report.get("FAIL_TO_PASS", {})
    p2p = report.get("PASS_TO_PASS", {})
    print(f"=== {sys.argv[1]} ===")
    print(f"parsed {len(status_map)} test results from log; found={found}")
    print(f"FAIL_TO_PASS  success={len(f2p.get('success', []))}  failure={len(f2p.get('failure', []))}")
    print(f"PASS_TO_PASS  success={len(p2p.get('success', []))}  failure={len(p2p.get('failure', []))}")
    if f2p.get("failure"):
        print("  F2P failing:", f2p["failure"])
    if p2p.get("failure"):
        print("  P2P failing (first 10):", p2p["failure"][:10])
    print(f"\nREWARD = {reward}")

if __name__ == "__main__":
    main()
