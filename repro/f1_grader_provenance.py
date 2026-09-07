"""Phase 1 -- re-anchor the grader, and verify the re-anchoring differentially.

WHY THIS EXISTS. `m4_grader.py` was written in July as an offline reproduction of
`SWEBenchTaskSet._calculate_reward` in the `verifiers` repo, at

    verifiers/envs/experimental/composable/tasksets/swe/swe_bench/taskset.py

That path was DELETED on 2026-08-31 by commit 66a6064 ("feat!: remove the legacy
(v0) stack"). There is no SWE-bench taskset in `verifiers` today: SWE-like work
routes through Harbor, whose reward is produced by a verifier INSIDE the task
image and merely read back from `/logs/verifier/reward.json`
(`verifiers/v1/tasksets/harbor/taskset.py:284-324`). So there is no in-repo
grading path left to diff against, and describing `m4_grader` as "the verifiers
grader" is no longer true.

What IS true, and what this script checks: the deleted verifiers code was itself
a thin caller of upstream `swebench`, and so is ours. This script transcribes the
v0.2.1 implementation literally (recovered with `git show v0.2.1:<path>`) and runs
it against our implementation on every log in this directory. If they agree on
all of them, `m4_grader` is a faithful offline swebench-format grader whose
provenance is documented rather than asserted.

Run under .venv (swebench 4.0.3 + the Windows shim).
"""
import os
import sys
import json
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swebench_shim  # noqa: F401
from m4_grader import grade_log

from swebench.harness.constants import (
    APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT,
    FAIL_ONLY_REPOS, FAIL_TO_PASS, PASS_TO_PASS, KEY_INSTANCE_ID,
    MAP_REPO_VERSION_TO_SPECS, EvalType, ResolvedStatus,
)
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.grading import get_eval_tests_report, get_resolution_status

META = json.load(open(os.path.join(HERE, "meta.json")))


class _TestSpec:
    """The fields of `swebench`'s TestSpec that the v0.2.1 code touches. Built
    from meta.json instead of `make_test_spec`, which needs the dataset (network);
    every field below is used verbatim by the transcription."""
    repo = META["repo"]
    version = META["version"]
    instance_id = META["instance_id"]
    FAIL_TO_PASS = META["FAIL_TO_PASS"]
    PASS_TO_PASS = META["PASS_TO_PASS"]


# ---------------------------------------------------------------------------
# Literal transcription of verifiers v0.2.1 (2026-07-20), recovered via
#   git show v0.2.1:verifiers/envs/experimental/composable/tasksets/swe/swe_bench/taskset.py
# `_get_logs_eval` (lines 60-87) and `_calculate_reward` (lines 513-540).
# Only `make_test_spec` is replaced, by the stub above.
# ---------------------------------------------------------------------------
def _v021_get_logs_eval(test_spec, content):
    repo = test_spec.repo
    version = test_spec.version
    log_parser = MAP_REPO_TO_PARSER[repo]
    test_cmd = MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]
    if isinstance(test_cmd, list):
        test_cmd = test_cmd[-1]
    bad_codes = [c for c in [APPLY_PATCH_FAIL, RESET_FAILED, TESTS_ERROR, TESTS_TIMEOUT]
                 if c in content]
    if bad_codes:
        return {}, False
    content = content.split(test_cmd)[-1]
    return log_parser(content, test_spec), True


def _v021_calculate_reward(test_output):
    test_spec = _TestSpec()
    eval_status_map, found = _v021_get_logs_eval(test_spec, test_output)
    eval_ref = {
        KEY_INSTANCE_ID: test_spec.instance_id,
        FAIL_TO_PASS: test_spec.FAIL_TO_PASS,
        PASS_TO_PASS: test_spec.PASS_TO_PASS,
    }
    eval_type = (EvalType.FAIL_ONLY if test_spec.repo in FAIL_ONLY_REPOS
                 else EvalType.PASS_AND_FAIL)
    report = get_eval_tests_report(eval_status_map, eval_ref, eval_type=eval_type)
    return float(get_resolution_status(report) == ResolvedStatus.FULL.value)


def main():
    logs = sorted(glob.glob(os.path.join(HERE, "log_*.txt")))
    print("Phase 1 -- grader provenance, checked differentially\n")
    print(f"  ours      : m4_grader.grade_log   (offline, meta.json)")
    print(f"  reference : verifiers v0.2.1 _calculate_reward, transcribed literally")
    print(f"  logs      : {len(logs)}\n")
    disagree = []
    for path in logs:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        ours = grade_log(text, META)["reward"]
        theirs = _v021_calculate_reward(text)
        flag = "" if ours == theirs else "   <-- DISAGREE"
        if ours != theirs:
            disagree.append(os.path.basename(path))
        print(f"  {os.path.basename(path):28s} ours={ours}  v0.2.1={theirs}{flag}")
    print("\n" + "=" * 74)
    if disagree:
        print(f"DISAGREEMENT on {len(disagree)} log(s): {disagree}")
        print("The re-anchoring claim does NOT hold; do not describe m4_grader as faithful.")
        return 1
    print(f"AGREEMENT on all {len(logs)} logs.")
    print("m4_grader is a faithful offline reproduction of the July grading path.")
    print("Correct description from here on: an offline SWE-bench-format grader over")
    print("upstream swebench 4.0.3 (get_eval_tests_report / get_resolution_status),")
    print("matching verifiers v0.2.1 -- NOT 'the verifiers grader', which no longer")
    print("exists in that repo (deleted 2026-08-31, commit 66a6064).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
