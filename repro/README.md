# Reproduction — `pytest-dev/pytest#10356`

Run-it-yourself scripts for every quantitative claim in `../writeup.md` about the
`pytest#10356` false negative and its four-gate repair. All grading uses upstream
`swebench` 4.0.3 (`get_eval_tests_report` / `get_resolution_status` + its pytest
log parser); no grading logic is reimplemented. Our caller reproduces how
`verifiers` called it at tag v0.2.1 (2026-07-20) -- that path was deleted on
2026-08-31 (commit 66a6064). `f1_grader_provenance.py` checks the two agree on
every captured log.

## What gets reproduced

| claim in the writeup | command | expected |
|---|---|---|
| the inherited test is a real false negative | `run_case.py` + `grade.py` | gold **1.0**, correct alt **0.0** on the *original* test |
| the alt is genuinely correct (independent witness) | `oracle.py` | base loses a marker `['foo']`; alt carries both `['bar','foo']` |
| the repaired test recovers the false negative | `m4_heldout_gate.py` | alt **0.0 → 1.0** on the *repaired* test (G3) |
| the four gates | `m4_heldout_gate.py` | G1 gold 1.0; G3 alt 1.0; G2 training 0/4 survive; held-out **1/3** survive |
| H_dup is the documented boundary, by mechanism | `m4_mechanism.py` | `iter_markers()` = `['a','b','c','a','b']`; name set `{a,b,c}` → survives |
| the versioned overlay | `m4_overlay.py` | writes `patch.diff`, `evidence.json`, `mutants/`, `validation.json` |

## Prerequisites (one-time setup)

**No paths to edit by hand.** The scripts autodetect the pytest checkout and the
test-runner interpreter relative to this repo, with environment-variable overrides
if your layout differs. Default layout:

```
<root>/
├── pytest/              # pytest cloned at the task base commit
├── .venv-pytest/        # venv with pytest installed editable (runs the tests)
├── .venv/               # venv with swebench (runs the grader)
├── verifiers/           # verifiers at 04b0bf5 with ../verifiers-formcheck.patch applied
├── .venv-vf/            # venv with that verifiers installed editable + swebench (runs f3_run.py)
└── rewardpatch/repro/   # these scripts + gold.diff, tests.diff, meta.json
```

- `run_case.py` finds the pytest clone at `../../pytest`; override with
  `REWARDPATCH_PYTEST_REPO=/path/to/pytest`.
- `m4_heldout_gate.py` finds the test-runner python at `../../.venv-pytest`
  (`Scripts/python.exe` on Windows, `bin/python` on POSIX); override with
  `REWARDPATCH_PYTEST_PYTHON=/path/to/venv/python`.

If a default is missing, the script exits with the exact variable to set. Nothing
is hardcoded to any one machine.

**No silent wrong results.** The tests are always run by the autodetected
`.venv-pytest`, chosen independently of whichever interpreter launches the script —
so `python run_case.py gold` works whether `python` is the grader venv, the system
python, or anything else. Before running, each script asserts that this
interpreter imports `pytest` from the repo checkout (the editable install); if it
does not, it **exits loudly** with the exact `pip install -e` to run, rather than
producing a meaningless `0.0` against the wrong pytest.

Setup, exactly as used:

```bash
# 1. pytest checkout at the task's base commit
git clone https://github.com/pytest-dev/pytest.git primein/pytest
git -C primein/pytest checkout 3c1534944cbd34e8a41bc9e76818018fadefc9a1

# 2. test-runner venv (Python 3.11): editable pytest
python -m venv primein/.venv-pytest
primein/.venv-pytest/Scripts/python -m pip install -e primein/pytest

# 3. grader venv: swebench (+ pandas/pyarrow only if regenerating data)
python -m venv primein/.venv
primein/.venv/Scripts/python -m pip install "swebench==4.0.3"

# 4. verifiers at the patch's base commit, with the formcheck patch applied
git clone https://github.com/PrimeIntellect-ai/verifiers.git primein/verifiers
git -C primein/verifiers checkout 04b0bf5
git -C primein/verifiers apply primein/rewardpatch/verifiers-formcheck.patch

# 5. verifiers venv (Python 3.11): editable verifiers + swebench (f3 grades in-process)
python -m venv primein/.venv-vf
primein/.venv-vf/Scripts/python -m pip install -e primein/verifiers "swebench==4.0.3"
```

`gold.diff`, `tests.diff`, `meta.json` are committed here, so no dataset download is
needed. To regenerate them from SWE-bench Verified: `write_patches.py` (needs
`swebench_verified.parquet` in this directory, and `pandas`/`pyarrow` in `.venv`).

The four commands on the front page (control, witness, gate, `f3_run.py`) need
only this setup. `f4_*.py` (multi-task) additionally need the parquet and, for
`f4_adjudicate.py` without `--dry-run`, an `OPENAI_API_KEY`.

Windows note: `swebench` imports the Unix-only `resource` module at import time;
`swebench_shim.py` stubs it. Every grader imports the shim first.

## Commands (exact)

Let `PYT = primein/.venv-pytest/Scripts/python` (runs tests), `PYG =
primein/.venv/Scripts/python` (runs grader), `PYV = primein/.venv-vf/Scripts/python`
(verifiers). From `primein/rewardpatch/repro/`:

```bash
# --- the false negative on the ORIGINAL inherited test ---
$PYT run_case.py gold        # applies gold patch, runs the graded test file
$PYT run_case.py alt         # applies a correct-but-different fix
$PYG grade.py log_gold.txt   # -> REWARD = 1.0   (gold passes its own test)
$PYG grade.py log_alt.txt    # -> REWARD = 0.0   (correct alt fails: TypeError on consider_mro)

# --- the alt is genuinely correct, independent of the graded assertion ---
$PYT oracle.py               # base: ['foo'] (bug) ; alt: ['bar','foo'] (contract satisfied)

# --- the repaired test + the four gates (train/held-out split) ---
$PYG m4_heldout_gate.py      # G1 1.0 ; G3 0.0->1.0 ; G2 train 0/4 ; held-out 1/3 (H_dup survives)

# --- H_dup survives by the predicted mechanism ---
$PYT m4_mechanism.py         # iter_markers ['a','b','c','a','b'] ; set {a,b,c} -> passes

# --- emit the versioned overlay (writes ./overlay/, upstream untouched) ---
$PYG m4_overlay.py

# --- the mechanical witness (Phase 0) and the verifiers path (Phase 3) ---
$PYT f0_witness.py           # gold + kwonly_specialize; writes log_f0_witness.txt, f0_result.json
$PYG f0_gate.py              # reward table: gold 1.0 / alt 0.0 / transformed gold 0.0 ; VERDICT
$PYV f3_run.py               # Task.formcheck via validate._run_check -> valid=False, reason 'invalid'
```

The committed, canonical overlay is `../overlays/pytest-dev__pytest-10356@rewardpatch-1/`.
`m4_overlay.py` regenerates an identical copy under `./overlay/` here.

## File map

- `run_case.py` — apply gold / a correct alt / base against the ORIGINAL inherited
  test; capture the real log. (M0)
- `grade.py`, `m4_grader.py` — offline SWE-bench-format grader over upstream
  `swebench`, a pure function of (log, `meta.json`). `m4_grader` is the reusable
  module; see its docstring for provenance.
- `f1_grader_provenance.py` — differential check of that provenance against a
  literal transcription of `verifiers` v0.2.1.
- `f0_equiv.py` — equivalence-PRESERVING transform operators (the mirror of
  `m4_mutants.py`), with checked preconditions.
- `f0_witness.py` / `f0_gate.py` — Phase 0: does a mechanical transform reproduce
  the hand-written witness? Writes `log_f0_witness.txt`, `f0_transform.diff`.
- `issue.txt` — the task's issue text (pytest-dev/pytest#7792), the input to the
  contract precondition.
- `f2_operators.py` — the equivalence-preserving operator family (tier,
  equivalence argument, perturbed observable, checked preconditions).
- `f2_worker.py` / `f2_gate.py` / `f2_overlay.py` — Phase 2: apply the family,
  classify (WITNESS / CLEAN / INVALID / UNVALIDATED / REFUSED / N-A), emit
  `overlay_f2/`.
- `f3_formcheck.py` / `f3_run.py` — Phase 3: `Task.formcheck` on the real
  verifiers v1 validate path (`../verifiers-formcheck.patch`).
- `f3_fcntl_shim.py` — Windows `fcntl` stub; verifiers v1 does not import on
  Windows without it.

## Two rig defects found and fixed while building Phases 0-3

Both were found by results disagreeing between phases, and both are recorded
because they change how much any single number here should be trusted.

1. **Stale bytecode.** `git clean -fd testing src` does not delete
   `__pycache__` (`.pyc` is gitignored, and clean skips ignored files without
   `-x`). A restored `.py` could leave a stale compiled module importable, and
   the failure surfaced in the NEXT case, not the one that caused it. Every
   reset now goes through `run_case.restore()`, which purges bytecode. Re-running
   Phase 0, Phase 2 and the four July gates after the fix reproduced every prior
   result unchanged, so no published number was affected.
2. **An unproven harness reading as a witness.** Phase 3's first revision ran the
   graded tests in the runtime's own scratch workdir, collected zero tests, and
   scored every transform 0.0 -- reporting four "witnesses", two of them false.
   `FormCheckMixin.formcheck` now runs a CONTROL first: if the untransformed
   reference solution does not score 1.0, it returns `None` (unchecked) and
   reports nothing. A 0.0 is only evidence when 1.0 was reachable.
- `oracle.py` — independent behavioral witness via public `item.iter_markers()`.
- `m1_run.py` — apply the *repaired* test + each hand-written solution.
- `m4_mutants.py` — mechanical mutant generator (no LLM): operators + the held-out
  set incl. `H_dup` (the duplication mutant).
- `m4_worker.py` / `m4_heldout_gate.py` — run all solutions; report G1/G3 and G2
  with the train/held-out split + Mutation Survival Rate.
- `m4_mechanism.py` — confirm `H_dup`'s survival mechanism.
- `m4_overlay.py` — emit the versioned overlay (spec §4.4).
- `swebench_shim.py` — Windows `resource` stub (import-only).
- `gold.diff`, `tests.diff`, `meta.json` — the task's gold patch, inherited test
  patch, and F2P/P2P grading keys.
