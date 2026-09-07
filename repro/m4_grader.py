"""Reusable offline SWE-bench-format grader.

grade_log(log_text, meta) -> dict with reward + full F2P/P2P breakdown.
Pure function of (captured test log, task meta). Runs under .venv (swebench + shim).
Single source of truth for reward in the gate runners.

PROVENANCE (checked, not asserted -- see f1_grader_provenance.py).
Resolution is decided by UPSTREAM `swebench` 4.0.3: `get_eval_tests_report` +
`get_resolution_status`, with `MAP_REPO_TO_PARSER` for log parsing. This function
reproduces how `verifiers` called them at tag v0.2.1 (2026-07-20), in
`verifiers/envs/experimental/composable/tasksets/swe/swe_bench/taskset.py`
(`_get_logs_eval`, `_calculate_reward`). `f1_grader_provenance.py` transcribes
that v0.2.1 code literally and checks both agree on every log here.

That verifiers path NO LONGER EXISTS: the whole v0 stack was removed on
2026-08-31 (commit 66a6064), and no SWE-bench taskset lives in `verifiers` today.
SWE-like tasks route through Harbor, where the reward is produced by a verifier
inside the task image and read back from `/logs/verifier/reward.json`
(`verifiers/v1/tasksets/harbor/taskset.py:284-324`) -- so there is no in-repo
grading path left to compare against. Do NOT call this "the verifiers grader";
call it an offline SWE-bench-format grader over upstream swebench.

Two deliberate differences from v0.2.1, both to keep grading offline:
  * task facts come from `meta.json`, not `make_test_spec` (which needs the dataset);
  * the pytest log parser is called with `test_spec=None`, which it accepts.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import swebench_shim  # noqa: F401

from swebench.harness.constants import (
    APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT,
    FAIL_ONLY_REPOS, FAIL_TO_PASS, PASS_TO_PASS, KEY_INSTANCE_ID,
    MAP_REPO_VERSION_TO_SPECS, EvalType, ResolvedStatus,
)
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.grading import get_eval_tests_report, get_resolution_status


def grade_log(log_text, meta):
    repo, version = meta["repo"], meta["version"]
    parser = MAP_REPO_TO_PARSER[repo]
    test_cmd = MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]
    if isinstance(test_cmd, list):
        test_cmd = test_cmd[-1]

    if [c for c in (APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT) if c in log_text]:
        status_map, found = {}, False
    else:
        status_map = parser(log_text.split(test_cmd)[-1], None)
        found = True

    eval_ref = {
        KEY_INSTANCE_ID: meta["instance_id"],
        FAIL_TO_PASS: meta["FAIL_TO_PASS"],
        PASS_TO_PASS: meta["PASS_TO_PASS"],
    }
    et = EvalType.FAIL_ONLY if repo in FAIL_ONLY_REPOS else EvalType.PASS_AND_FAIL
    report = get_eval_tests_report(status_map, eval_ref, eval_type=et)
    reward = float(get_resolution_status(report) == ResolvedStatus.FULL.value)
    f2p, p2p = report["FAIL_TO_PASS"], report["PASS_TO_PASS"]
    return {
        "reward": reward,
        "found": found,
        "n_parsed": len(status_map),
        "f2p_pass": len(f2p["success"]), "f2p_fail": len(f2p["failure"]),
        "p2p_pass": len(p2p["success"]), "p2p_fail": len(p2p["failure"]),
        "f2p_failing": list(f2p["failure"]),
        "p2p_failing": list(p2p["failure"])[:10],
    }


def grade_file(log_path, meta):
    with open(log_path, encoding="utf-8") as f:
        return grade_log(f.read(), meta)
