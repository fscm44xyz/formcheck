# formcheck — detecting form-coupled graders with executable witnesses

`verifiers`' task validation (`validate`) has two checks, `gold` and `setup`
(`verifiers/v1/cli/validate.py:66-71`). Neither asks whether the reward would
also accept a correct solution written differently: the gold patch passes its
own tests, so a test coupled to the incidental form of that patch is invisible
to both. Commit `651484c` (2026-08-29) made the gap visible without filling it —
`Task.validate` became tri-state, so a taskset with no check now reports
`unchecked` instead of `valid`. `formcheck` fills it, mechanically: it applies
behaviour-preserving transforms to the reference solution (specialise away an
invented keyword-only parameter; alpha-rename a symbol), re-runs the graded
tests, and reports a witness when the transformed solution still satisfies the
issue's contract and still scores 0.0. No LLM is involved in producing a witness.

## The witness on `pytest-dev/pytest#10356`

Output of `repro/f0_gate.py`; grading by upstream `swebench` 4.0.3:

| solution | reward | F2P | P2P |
|---|---|---|---|
| gold patch (control) | 1.0 | 1/1 | 79/79 |
| hand-written alt (control) | 0.0 | 0/1 | 79/79 |
| gold + `kwonly_specialize` | 0.0 | 0/1 | 79/79 |

The mechanical transform reproduced what took a human to write. The transformed
gold satisfies the issue's contract (independent oracle: both markers
collected) and fails exactly the graded test, `test_mark_mro`, and nothing else.

## Coupling is not only in the graded test

On `pydata/xarray#4966`, alpha-renaming `UnsignedIntegerCoder` fails 4
PASS_TO_PASS tests (each an `AttributeError` on the name) while all 4
FAIL_TO_PASS tests pass. The reward goes to zero through PASS_TO_PASS.

## Run it yourself

Setup — a pytest checkout at the task's base commit, three venvs, and
`verifiers` at `04b0bf5` with `verifiers-formcheck.patch` applied — is in
[repro/README.md](repro/README.md). Then, from `repro/` (Windows paths; on POSIX
use `bin/python` instead of `Scripts/python`):

```
../../.venv-pytest/Scripts/python run_case.py gold ; ../../.venv/Scripts/python grade.py log_gold.txt          # REWARD = 1.0  (control)
../../.venv-pytest/Scripts/python f0_witness.py    ; ../../.venv/Scripts/python grade.py log_f0_witness.txt    # REWARD = 0.0  (mechanical witness)
../../.venv/Scripts/python f0_gate.py                                                                          # the table above
../../.venv-vf/Scripts/python f3_run.py                                                                        # valid = False, reason 'invalid'
```

The last command runs `Task.formcheck` through `verifiers`' own
`validate._run_check` and prints the `results.jsonl` row it would persist.

## Scope

n = 3 tasks (`pytest#10356`, `flask#5014`, `xarray#4966`); three witnesses in
two of them. Mechanism demonstration, not a rate. The `verifiers` run uses the
`subprocess` runtime on Windows with a local stand-in taskset; `formcheck`
belongs inside Harbor task images, where the reference score is reproducible by
construction.

## Contents

- [writeup.md](writeup.md) — method, measurements, retractions, and an appendix
  with every command.
- [judge_rubric.md](judge_rubric.md) — contract-vs-form rubric for the border
  cases the operators refuse.
- [verifiers-formcheck.patch](verifiers-formcheck.patch) — `--only-formcheck`
  for `validate` (121 lines, base `04b0bf5`).
- [overlays/](overlays/) — the pytest#10356 repair overlay and the one
  flask#5014 adjudication.
- [repro/](repro/) — scripts, captured logs, and per-transform evidence
  (`repro/overlay_f2/`).
