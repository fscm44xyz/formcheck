"""Phase 3 -- run `formcheck` through the REAL verifiers validate path.

Not a simulation of the integration: this calls `verifiers.v1.cli.validate`'s own
`_run_check` with `mode="formcheck"`, which provisions a runtime, runs
`Task.setup`, dispatches to the patched hook, and classifies the result with the
untouched `_classify`. The row printed is the row `validate` would persist to
`results.jsonl`.

What is real here: the verifiers version (origin/main), the hook contract, the
dispatch, the runtime, the classification, the transforms, the graded tests, the
oracle, and the grading.

What is NOT real, and must not be claimed: the runtime is `subprocess`, not a
container, and the taskset is a local stand-in, because no SWE-bench taskset
lives in `verifiers` any more (v0 removed 2026-08-31, commit 66a6064) and Harbor
scores inside a task image. This shows the hook works on the real path; it does
not show it running against a hub SWE environment.

Run with .venv-vf.
"""
import os
import sys
import json
import asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import f3_fcntl_shim  # noqa: F401,E402

from verifiers.v1.cli.validate import _run_check, validation_mode  # noqa: E402
from verifiers.v1.configs.cli.validate import ValidateConfig  # noqa: E402
from verifiers.v1.runtimes import SubprocessConfig  # noqa: E402
import verifiers.v1 as vf  # noqa: E402

import run_case  # noqa: E402
from f3_formcheck import PytestMarkMroTask, MarkMroData  # noqa: E402

META = json.load(open(os.path.join(HERE, "meta.json")))


async def main():
    run_case.assert_editable_pytest()
    cfg = ValidateConfig(taskset={"id": "harbor"}, runtime=SubprocessConfig(),
                         only_formcheck=True)
    print("Phase 3 -- Task.formcheck on the real verifiers validate path\n")
    print(f"  verifiers        : {vf.__name__} (origin/main worktree, patched)")
    print(f"  validation_mode  : {validation_mode(cfg)!r}   "
          f"(new; alongside 'gold' | 'setup' | 'all')")
    print(f"  runtime          : {type(cfg.runtime).__name__}")
    print(f"  task             : {META['instance_id']}\n")

    task = PytestMarkMroTask(
        MarkMroData(idx=0, name=META["instance_id"], prompt=""), META)
    row = await _run_check(task, cfg, "formcheck")

    print("  transform log (as the hook saw it):")
    for label, verdict, why in task.formcheck_log:
        print(f"    {verdict:12s} {label:52s} {why}")

    print("\n  results.jsonl row that `validate` would persist:")
    for key in ("index", "name", "mode", "valid", "reason", "elapsed", "error"):
        print(f"    {key:9s} = {row.get(key)!r}")

    reason = row["reason"]
    print("\n" + "=" * 76)
    if reason == "invalid" and row["valid"] is False:
        print("FORM-COUPLED: the task's reward rejects a behaviour-preserving")
        print("variant of its own reference solution. `validate --only-gold` calls")
        print("this same task valid, because the gold patch passes its own tests.")
        print(f"witnesses: {getattr(task, 'formcheck_witnesses', [])}")
    elif reason == "unchecked":
        print("UNCHECKED: nothing could be judged. Reported as absence of a check,")
        print("not as agreement -- the distinction verifiers #2466 introduced.")
    elif reason == "valid":
        print("NO WITNESS: transforms were judged and none exposed coupling.")
    else:
        print(f"reason={reason!r} error={row.get('error')!r}")
    json.dump({"row": row, "log": task.formcheck_log},
              open(os.path.join(HERE, "f3_result.json"), "w"), indent=2)


if __name__ == "__main__":
    asyncio.run(main())
