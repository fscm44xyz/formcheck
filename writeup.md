# formcheck — detecting form-coupled graders with executable witnesses

> **This is the method document, at n=3 tasks, written July–August 2026.** Its
> scope claims are superseded by the 500-task run reported in
> **[REPORT.md](REPORT.md)** — where the corresponding figure is 22.2% of
> controlled tasks, not a mechanism demonstration. It is retained for §3–§5, which
> are the method, and §9, which is the record of what this work got wrong.

*An offline admission check for RL task rewards, built on Prime Intellect's
`verifiers` stack. It answers a question `validate --only-gold` cannot ask: not
"is the ground truth right?" but "would this reward also accept a correct
solution written differently?" — and it answers it by constructing the
counter-example rather than asserting one.*

*Every number below is labelled **measured**, **qualitative**, or **open**. Where
something here was got wrong earlier, the retraction is in the text, not
in a footnote: the errors are how the method acquired its two safety rules.*

---

## Summary

Prime's own task validation is model-free and has exactly two checks — `gold` and
`setup`, with `all` running both (`verifiers/v1/cli/validate.py:66-71`). Both are blind, by construction,
to a reward that rejects a *correct* solution: the gold patch passes its own
tests, so a test coupled to that patch's incidental form is invisible. On
2026-08-29 Prime made the hole visible without filling it — commit `651484c`
turned `Task.validate` tri-state so a taskset with no check reports `unchecked`
instead of silently reporting `valid`.

`formcheck` adds the missing check, mechanically. It transforms the reference solution in ways
that preserve observable behaviour — specialising away an invented keyword-only
parameter, alpha-renaming an internal symbol — and re-runs the graded tests. A
transformed solution that still satisfies the issue's contract and *still fails
the graded tests* is a false negative, exhibited with an executable witness. No
LLM is involved in producing it.

**What is measured here, and the n it rests on:** three usable tasks —
`pytest#10356`, plus `flask#5014` and `xarray#4966`, the two of five newly
attempted tasks that reproduced their own reference score. Three witnesses, found
in two of those three tasks. That is a mechanism demonstration at n=3 tasks. It is
not a rate, and nothing below is presented as one.

**The most transferable finding, and the one not anticipated:** on
`pydata/xarray#4966` the coupling lives in **PASS_TO_PASS**, not in the graded
`FAIL_TO_PASS` test. Four P2P tests fail purely because they name an internal
symbol; the seventeen that do not name it pass, and all four F2P tests pass. A
reward can reject a correct solution through the tests that were supposed to be
the *stable* part of the task.

**What limits this in practice is not detection but reproducibility.** Of five
tasks, four mounted and only **two** could reproduce their own reference score
outside Docker. The remedy was always the same — pin dependencies to the task's
era. That is precisely what Harbor's images already encode, which is the
operational conclusion: `formcheck` belongs *inside* those images.

---

## 1. The problem, in Prime's terms — and in their code

Prime's July 2026 post on scaling agentic RL to 365k+ tasks states that tasks
mined from merged PRs inherit that PR's tests, and those tests "often assert
implementation details rather than behavior." An agent that fixes the underlying
issue differently but correctly still fails them, and the reward reads as a false
negative. Prime also states the structural reason it goes unnoticed: gold/no-op
validation is blind to this **by construction**.

The code says the same thing, more precisely.

**`Task.validate` has no opinion by default.** `verifiers/v1/task.py:180`:

```python
async def validate(self, runtime: Runtime) -> bool | None:
    """Check the ground truth, or return None when no model-free check exists."""
    return None
```

**Almost nothing overrides it.** Across the whole repository there are exactly
two implementations: `environments/gsm8k/gsm8k/taskset.py:46` and
`verifiers/v1/tasksets/lean/taskset.py:129`. Every other taskset — including
every code task — returns `None`. *(measured, by grep over `origin/main`.)*

**And there are only two things it can check.**
`verifiers/v1/cli/validate.py:66-71`:

```python
def validation_mode(config: ValidateConfig) -> str:
    if config.only_gold:
        return "gold"
    if config.only_setup:
        return "setup"
    return "all"
```

`gold` asks whether the ground truth checks out. `setup` asks whether the
environment builds. Neither asks whether the reward would accept a correct
solution that differs from the reference. There is no third check, and no hook
that could carry one.

**Prime instrumented the gap on 2026-08-29.** Commit `651484c` ("Report unchecked
gold validation", #2466) made validation tri-state: `FINAL_VALUES = {"valid":
True, "invalid": False, "unchecked": None}`, `_classify` returns `"unchecked"`
when `valid is None`, and `valid_rate` is computed only over items actually
checked. The PR it implements (#2293) put it plainly: *"The failure is silent and
flattering: absence of a check is reported as agreement."* After that commit,
running `validate --only-gold` over a code taskset honestly reports that nothing
was checked. The hole is now visible and still open.

**Independent corroboration of scale.** DeepSWE (arXiv 2607.07946) measures
**19–28% verifier false negatives on SWE-Bench Pro**. *(measured — by them, on a
different corpus, by a different method.)* It is cited as evidence the phenomenon
is large, not as a substitute for the numbers here: it measures false negatives of
a verifier end-to-end, while §2 measures implementation-coupling signals in graded
tests. Related but not the same quantity.

**What Prime has already closed, and is therefore not claimed here.**
`IsolatedVerifierEnv` (`verifiers/v1/envs/isolated_verifier/env.py`) reruns a
task's metrics and rewards in a fresh runtime after the solver's box is
destroyed, closing the "grade in a box the agent controlled" gap as a shipped
feature. It does not touch this one: a test that rejects a correct solution
rejects it just as reliably in a pristine container.

---

## 2. The inversion: from repairing to detecting

This project started as a repairer, built in July. Measurement led out of it.

**What was measured then** *(measured; sample caveats stated)*:

| corpus | coupling in graded tests | how |
|---|---|---|
| SWE-bench Verified (curated) | ~2–4% | scan of all 500 test patches |
| Scale-SWE (uncurated) | **35%** — 316 of 907 graded tasks with ≥1 signal | 972-row prefix sample, Python-only, repo-clustered |

**These are not the 22.2% in `REPORT.md`, and the two must not be read as one
number that grew.** The ~2–4% here is a *static scan* counting test patches that
carry a coupling signal, over all 500 tasks; the 22.2% is an *executable witness*
rate — a transform that provably preserved behaviour and still scored 0.0 — over
the 126 tasks where that could be judged. Different evidence, different
denominators, different questions.

And among those 316 coupled tasks, the *kind* of coupling *(measured)*:

| signal | tasks | share of coupled |
|---|---|---|
| mocks an internal symbol | 218 | 69% |
| exact `call_args` / `assert_called` | 182 | 58% |
| exact message equality | 68 | 22% |
| private-symbol reference | 46 | 15% |

The uncomfortable part is the shape, not the size. **The dominant kinds are the
least repairable.** When a test mocks an internal and asserts its call arguments,
the intended behaviour is observable *only through the mock* — there is no
independent oracle to repair the assertion against. The repairable slice lived in
the minority message-coupling type, and a large part of even that turned out to
be contract the issue actually specifies. Under audit the estimate of the
safely-repairable fraction shrank threefold, to a single-digit percentage
*(qualitative — a direction, from 26 non-random hand-classified cases; never a
population rate)*.

So repairing was the wrong product. But the same measurement points at the right
one:

> **Detection does not need a repair to be safe — it needs a counter-example to
> be real.** You cannot always rewrite a mock-coupled assertion into a behavioural
> one. You *can* mechanically construct a solution that is behaviourally the same
> as the reference and watch the grader reject it. That rejection is the finding,
> and it needs no judgement to produce.

The inversion is literal. The July mutant generator perturbed a solution to
*break* behaviour, checking the tests caught it (negative preservation). The new
operators perturb the reference to *preserve* behaviour, checking whether the
tests reject it anyway. Same machinery, opposite sign, and the output changes from
a proposed patch you must trust to a diff you can run.

The July repair remains in the repository (`overlays/…@rewardpatch-1/`) as the
case that produced the investment, and as a useful control: §6 shows the machine
rediscovering, without an LLM, two of the three couplings a human catalogued there
by hand.

---

## 3. The method

### 3.1 A transform family, not a heuristic

Four operators, each carrying four things — none optional.

| operator | tier | observable it can perturb | equivalence argument | what breaks it |
|---|---|---|---|---|
| `kwonly_specialize` | HIGH | callable signature | a keyword-only parameter with a constant default, read only in param-only `if` tests and passed only as a literal (or omitted) at every call site, is a static switch; specialising per constant and dispatching each call site to its specialisation evaluates the same branch on the same arguments in the same order | the parameter is read dynamically (`**kwargs`, `getattr`, signature introspection), or a call site passes a non-constant |
| `symbol_rename` | HIGH if `_`-private, else MEDIUM | symbol identity | renaming a definition and every static reference to it — including `from X import name` — is a pure alpha-rename; no expression's value changes | the name is reached by a path the rewrite cannot follow: an `__all__` entry, a `mock.patch` target, `getattr`, an entry point |
| `collection_reverse` | MEDIUM | element order | if the issue fixes no order and no caller depends on position, order is unspecified | any consumer is order-sensitive — including precedence rules like "nearest wins", which are ordering semantics even when the issue never writes the word "order" |
| `message_reword` | HIGH | exception message text | the exception *type* is the contract, the wording is form; rewording changes no control flow | a consumer matches on the text, or the issue quotes the wording |

Equivalence here is **argued and regression-checked, never proven**, and the word
proof is not used. Each operator states its own argument and names the condition
that would defeat it, so a reader can attack the argument rather than the verdict.

### 3.2 Preconditions are checked, and a failure refuses

`kwonly_specialize` on `pytest#10356` reports what it verified *(measured)*:

```
P1 signature    keyword-only, default True
P2 contract     the issue names neither 'consider_mro' nor 'get_unpacked_marks'
P3 call sites   1 in this module + 2 in 1 other scanned module, none passing the
                parameter; non-default constants passed: [False]
P4 no dynamic   read only in 1 param-only `if` test; no **kwargs
```

When a precondition fails the operator **refuses**; it never forces. On the same
task, `symbol_rename` refused `MarkDecorator` because the name appears in a
non-annotation string literal at `src/pytest/__init__.py:117` — an `__all__`
entry, i.e. a public re-export an alpha-rename cannot follow.

That refusal is also a worked example of a false positive since removed. It
originally fired on `) -> "MarkDecorator":` in `structures.py:48` — a
**forward-reference type annotation**, which is a static type reference, not
dynamic reach. Treating annotations as dynamic over-refuses, so they are now
renamed along with the symbol. Relaxing that alone would have been unsafe,
because the two-file scan in use at the time could not see the `__all__` entries
at all; the relaxation shipped together with widening the scan from 2 files to the
whole production tree (67 files for pytest). Same verdict, sound reason.

**The anchor set above was chosen by hand, and it is wider than §3.3's stated
criterion.** §3.3 says an operator is offered symbols whose definition the
reference patch overlaps. When that rule is applied mechanically — changed line
numbers taken from the diff's hunk arithmetic, resolved against the definitions'
real line ranges in the post-patch file — `pytest#10356` yields
`{get_unpacked_marks, store_mark}`. The set actually used in Phase 2 was
`{get_unpacked_marks, store_mark, normalize_mark_list, MarkDecorator}`. The gold
patch touches neither of the last two: `normalize_mark_list` appears nowhere in
it, and `MarkDecorator` appears only as the class enclosing the `__call__` that
git happens to print in a hunk header — git prints the nearest *preceding*
definition there, which is frequently one the hunk does not modify.

So two of the seven Phase 2 rows are **not reachable from the gold patch alone**:
`symbol_rename:MarkDecorator` (REFUSED — the refusal worked through immediately
above) and `symbol_rename:normalize_mark_list` (CLEAN). Everything reported in
this section was really run and the verdicts are real; what cannot be claimed is
that the criterion in §3.3 produced this anchor set. A human did. The rule has
not been widened to recover those rows, because widening it until known-
interesting rows come back is selecting for the outcome — the exact thing §3.3
exists to prevent.

Both rows the headline rests on survive the correction:
`symbol_rename:get_unpacked_marks` and
`kwonly_specialize:get_unpacked_marks(*, consider_mro=...)` are anchored under
the mechanical rule, and the former is still a WITNESS under it. `scale/SCOPE.md`
sets out the two rules side by side, row by row.

### 3.3 Anchors are restricted to what the gold patch touches

An operator is only offered symbols whose definition the reference patch actually
overlaps. This is principled — the fix's own form is what a graded test can be
coupled to — and it is also the thing that keeps the operator honest. Without it,
`symbol_rename` would sweep every definition in a module and one could pick the
ones that happened to produce a witness. That would be selecting for the outcome.
The restriction is what makes "no witness" a real result.

### 3.4 G4, mechanised

The contract check from the July work is now a precondition, not a human
judgement: **if the issue names the object a transform would touch, the transform
refuses and the case is routed to `judge_rubric.md`.** The check normalises
markdown, matches whole identifiers, and quotes what it found.

The rubric's refined rule is why this is a routing decision and not a verdict:
*being named in the issue is a strong proxy, not proof.* Contract requires that
the issue names the payload **and** that it is public surface consumers depend
on. A proposed name for something internal is still form. The mechanised check
implements the cheap half and hands the expensive half onward.

### 3.5 Six outcomes, all first-class

| verdict | meaning |
|---|---|
| **WITNESS** | contract satisfied, graded reward 0.0, and the failures are attributable to the transform — the reward rejects a behaviour-preserving variant of its own reference |
| **CLEAN** | contract satisfied, graded reward 1.0 — the tests tolerate this transform |
| **INVALID** | the oracle says the contract broke — the transform was not behaviour-preserving. Discarded and counted; this is the honest bound on the phrase "preserves behaviour" |
| **UNVALIDATED** | the transform can perturb an observable the available oracle cannot watch, so its pass is uninformative. **Never a witness** |
| **REFUSED** | a precondition failed, including G4. Routed, never forced |
| **NOT_APPLICABLE** | the operator has no anchor in the gold-touched region |

`INVALID` is a discard, not a finding; it occurred 0 times here, which is why the
distributions in §6 and §9 show five non-zero entries. `UNVALIDATED` and `REFUSED`
are not failures of the run. They are the two ways the method declines to
over-claim, and §4 is the story of why they exist.

---

## 4. Two principles, and how each was earned

Both of these were bought with mistakes made here. They are in the text because
they are the load-bearing part of the design, and because a method that only
reports its successes should not be believed.

### 4.1 "A 0.0 is only evidence if the 1.0 was reachable"

The first version of the `formcheck` hook ran the graded tests inside the
runtime's own scratch directory instead of the repository. It collected zero
tests. Every transform therefore scored 0.0, and the run reported **four
witnesses — two of them false**. Nothing in the output looked wrong; the numbers
were plausible and the verdict was confident.

It was caught only because the result contradicted an earlier phase that had run
the same transforms a different way. That is not a safety mechanism, it is luck.

The fix is a mandatory control, before anything else runs:

```python
self.formcheck_reset()
_, control = await self.formcheck_graded(runtime)
if control != 1.0:
    return None      # `unchecked` -- never a coupling claim on an unproven harness
```

If the untransformed reference does not score 1.0, the hook reports `unchecked`
and asserts nothing. A zero is not evidence of coupling unless a one was
achievable in the same harness. §7 shows this rule firing on half the tasks
mounted there — which is exactly the point: it converts an environment fault into an
honest abstention instead of a finding.

### 4.2 "An oracle that cannot disconfirm a transform cannot confirm it"

`collection_reverse` on `pytest#10356` reverses the list returned by
`get_unpacked_marks`. The graded test fails — `At index 0 diff` — and the oracle
(a *set* of marker names, read through pytest's public API) reports the contract
satisfied. It looks exactly like a witness.

It is not. In pytest, marker order determines precedence: `get_closest_marker`
resolves by position. Reversing the list is a genuine behaviour change that this
oracle is structurally blind to, because a set hides order. **Here the graded test
is right and the transform is wrong.**

So each operator declares the observable class it can perturb, and each task
declares what its oracle actually watches. When the two do not intersect the
result is `UNVALIDATED`, whatever the graded reward said. The rule is symmetric
and that is the whole content of it: an oracle that could not have caught the
transform being wrong has not shown that it is right.

The same blindness was already documented in July as the `H_dup` boundary — a
duplication mutant that survived the repaired test because set-equality cannot
see duplicates. It is the same limitation, found twice, now enforced by the
classifier rather than remembered by a human.

---

## 5. Integration: it runs on the real path

`verifiers-formcheck.patch` — **3 files changed, +52 −9, against `origin/main`
`04b0bf5`** (147 lines of unified diff).

1. **`verifiers/v1/task.py`** — a `formcheck` hook beside `validate`, with the
   same tri-state contract that `651484c` established:

   ```python
   async def formcheck(self, runtime: Runtime) -> bool | None:
       """Check that the task's reward does not reject a CORRECT solution, or
       return None when no such check exists."""
   ```

   `False` = a witness exists. `True` = transforms were judged and none produced
   one. `None` = nothing could be judged — reported `unchecked`, never `valid`,
   so an absent check does not read as agreement.

2. **`verifiers/v1/configs/cli/validate.py`** — `only_formcheck`, and the
   at-most-one validator extended to three flags.

3. **`verifiers/v1/cli/validate.py`** — `validation_mode` returns `"formcheck"`;
   `_run_check` dispatches by mode; `_run_all` runs it alongside gold and setup.
   `_classify` is **untouched**: the existing vocabulary already distinguishes
   valid / invalid / unchecked, and `mode` disambiguates what was checked.

**Run for real, not simulated.** `verifiers` `main` was installed in a venv and
called the library's own `_run_check(task, cfg, "formcheck")`. It provisioned a
runtime, ran `Task.setup`, dispatched to the hook, and classified with the
untouched `_classify`. The row it produced is the row `validate` would persist:

The July rig, `SubprocessRuntime` (see the retraction below for what has since
changed):

```
index=0  name='pytest-dev__pytest-10356'  mode='formcheck'
valid=False  reason='invalid'  elapsed=37.88  error=None
```

*On `elapsed`.* This row is `repro/f3_result.json`, which is the only persisted
artifact of a Phase 3 run and has held `37.88` unchanged since the first commit
of this document. An earlier draft of this section printed `46.44`, a figure that
appears nowhere but in that sentence: it came from a console session that was not
saved, of the same task on the same subprocess path. A third figure, `26.65`,
circulated from a demo rehearsal and is not in this repository or its history at
all, so nothing here can say what it measured. The three are not the same run
reported three ways -- they are separate runs of one task whose cost is dominated
by a pytest invocation, and only one of them left an artifact. The artifact is
what is quoted.

For comparison, `validate --only-gold` on this same task: the local stand-in
implements the gold check, so it reports `valid` — the gold patch passes its own
tests. A real code taskset, which returns `None` from `validate` (§1), reports
`unchecked`. In both cases `formcheck` reports `invalid`.

**Limits — one of these has since been retracted.** This section first read: *the
runtime is `subprocess`, not a container; the taskset is a local stand-in.* The
first half was true of the July rig and is now true of nothing. `formcheck` runs
on verifiers' own `DockerRuntime`, with the image resolved through
`resolve_runtime_config` from `task.data.image` — the same call, on the same
path, by which a Harbor task reaches its container. §7 argued on paper that the
check belonged inside the task's own image; M0 (`evidence/m0-gate`, `4ab9760`)
executed it,
and the seven verdicts came back identical to the July rig's on operator, anchor,
verdict and refusal reason.

What remains not-real is the taskset. It is still a local stand-in, because no
SWE-bench taskset lives in `verifiers` any more — the whole v0 stack was removed
on 2026-08-31 (commit `66a6064`) — and SWE-like tasks now route through Harbor,
where the reward is produced by a verifier *inside the task image* and read back
from `/logs/verifier/reward.json`
(`verifiers/v1/tasksets/harbor/taskset.py:284-324`). So the hook is demonstrated
on the real runtime path, in the real image. It is still **not** demonstrated
against a hub SWE environment.

---

## 6. Results

### 6.1 The witnesses *(measured — 3 witnesses, in 2 of the 3 usable tasks)*

| task | operator | anchor | type of coupling | where it bites |
|---|---|---|---|---|
| `pytest-dev/pytest#10356` | `kwonly_specialize` | `get_unpacked_marks(*, consider_mro=…)` | invented keyword-only parameter | F2P — `TypeError: got an unexpected keyword argument 'consider_mro'` |
| `pytest-dev/pytest#10356` | `symbol_rename` | `get_unpacked_marks` | internal symbol imported by the test | F2P |
| `pydata/xarray#4966` | `symbol_rename` | `UnsignedIntegerCoder` | internal symbol named by the tests | **P2P** |

Full outcome distribution across the three tasks with a valid control
*(measured)*: **WITNESS 3, CLEAN 2, INVALID 0, REFUSED 2, UNVALIDATED 1,
NOT_APPLICABLE 7** — 15 rows in total. The denominators used throughout: 4
operators × 3 tasks = **12 operator-slots**; 7 of them had no anchor in the
gold-touched region (the 7 `NOT_APPLICABLE`); the 5 that did yielded **8
anchor-cases**, because `symbol_rename` found four anchors on `pytest#10356` and
one on each of the others; 7 + 8 = 15.

Invalid-transform rate: **0 of 5 judged transforms** *(measured, and tightly
bounded — see §9)*.

### 6.2 Coupling does not only live in the graded test

The `xarray` witness is the finding that was not anticipated. Renaming
`UnsignedIntegerCoder`:

- **4 PASS_TO_PASS tests fail**, every one with
  `AttributeError: module 'xarray.coding.variables' has no attribute
  'UnsignedIntegerCoder'`;
- **17 P2P tests that do not name the symbol pass**;
- **all 4 FAIL_TO_PASS tests pass**.

An alpha-rename changes no expression's value, so those four tests are asserting
the *name*. The reward goes to zero through PASS_TO_PASS — the part of the task
that is supposed to be the stable background, not the thing under test. Any
detector that only inspects the F2P tests would miss this class entirely.

It also forced a mid-flight correction that belongs on the record: the classifier
originally called *any* P2P breakage `INVALID`. That would have reported this as
"the transform broke behaviour". It now partitions P2P failures into those whose
failure text names the renamed symbol (coupling) and those that fail any other way
(genuinely invalid), attributing each failure through its own pytest failure block
rather than by scanning the log for `E ` lines — a passing test that runs a nested
pytest session prints those too.

### 6.3 The machine reproduced the human, minus the part the human flagged

July's overlay catalogued three coupled forms in `pytest#10356`, by hand:

1. private import from `_pytest.mark.structures` → **rediscovered** by
   `symbol_rename` (WITNESS);
2. invented keyword `get_unpacked_marks(..., consider_mro=False)` → **rediscovered**
   by `kwonly_specialize` (WITNESS);
3. exact list order `[c, a, b]` → **declined**, `UNVALIDATED`, because the oracle
   cannot see order.

The third is precisely the item the human had also recorded as a documented
boundary (`H_dup`). The mechanical family found what the human found and refused
to claim the one the human had already marked as beyond the oracle. *(qualitative
— one task, and the comparison is against this project's own earlier labels.)*

### 6.4 Mock coupling: reachable, not observed — and a retraction

**An interim report previously claimed that `symbol_rename` structurally
cannot exhibit the dominant mock-based coupling, because `mock.patch` targets are
string literals and the operator refuses on string occurrences of the name. That
claim was wrong, and the reasoning behind it was wrong.**

The operator only ever scans **production** sources. Test files are never in its
source set, because the transform rewrites the solution and not the graded tests.
So a `mock.patch("mod.sym")` inside a test triggers no refusal at all: the rename
proceeds, and the test breaks because it named the symbol. That is a witness.

It was settled with a **synthetic probe** (`repro/f4_mock_probe.py`), labelled in
its own docstring as *not a measurement*. It takes `store_mark` on `pytest#10356`
— CLEAN in the real task — and injects a `mock.patch` on it into a PASS_TO_PASS
test:

```
baseline (real task):      tests reported FAILED: none            -> CLEAN
with injected mock.patch:  testing/test_mark.py::test_pytest_param_id_requires_string
                           E AttributeError: <module '_pytest.mark.structures'…>
                           every failing test references 'store_mark': True
                                                                  -> WITNESS
```

So: **mock coupling is reachable by this mechanism** *(measured, on a synthetic
case)*, and it was not observed in the wild at n=3 because none of the three
tasks contained an instance — absence of data, not a structural bar *(open: its
real prevalence under this operator is unmeasured)*.

The probe paid for itself twice. It also exposed that the classifier did not
recognise `mock`'s phrasing — `does not have the attribute 'X'` matches none of
the interpreter's own messages — so it would have labelled that reachable witness
`INVALID`. Fixed.

### 6.5 Where the ceiling actually is

`NOT_APPLICABLE` in **7 of 12 operator-slots** across the three usable tasks
*(measured)*. The gold patch rarely introduces the object a given operator needs:
no invented keyword-only parameter, no raised message, no returned collection. The
binding constraint on coverage is anchor availability, not refusals and not
oracle strength.

---

## 7. Reproducibility is the operational finding

*(measured, n=5)*

| stage | rate |
|---|---|
| mounted (clone + venv + editable install) | **4 / 5** |
| reproduced its own reference score (control = 1.0) | **2 / 4 mounted**, 2 / 5 attempted |

The one that did not mount, `psf/requests#1142`, fails for a reason worth naming:
its 2013 `setup.py` imports the package to read its version, and
`requests/utils.py:23` does not import on Python 3.11.

The two that mounted but could not reach a valid control:

- `pytest-dev/pytest#7571` needs pytest 6.0, which cannot run on Python 3.11 —
  `TypeError: required field "lineno" missing from alias`. An interpreter
  incompatibility, not a pin.
- `pylint-dev/pylint#6903` stalled at P2P 4/8 after three era-pins. It was
  abandoned rather than fought, and recorded as `unchecked`.

The remedy, every time it worked, was the same: **pin dependencies to the task's
era** — `pytest==7.4.4`, `werkzeug==2.3.7`, `numpy==1.26.4`, `astroid==2.11.7`,
plus a missing optional `dask`. Modern resolvers install current versions of
everything and the repo's own test suite stops working: Werkzeug 3 removed
`__version__`, NumPy 2 removed `np.unicode_`, pytest 9 removed
`_pytest.monkeypatch.notset`.

**That list is a description of what a Docker image is for.** The operational
conclusion follows directly, and it is the main thing worth telling Prime about
deployment:

> `formcheck` should run **inside the Harbor task image**, where those pins are
> already encoded. Outside them, half the tasks cannot reproduce their own gold —
> and because of the mandatory control (§4.1), the check correctly switches itself
> off rather than reporting anything. A detector that abstains on half the corpus
> for environment reasons is not a detector; the fix is not a better detector but
> the right place to run it.

---

## 8. Routing the border

Cases the mechanical family declines are routed to `judge_rubric.md`, which stays
a separate artefact: an auditable contract-vs-form judge with a text-anchored
decision procedure, worked examples, and an explicit statement that no reliability
metric is claimed for it.

Across the three tasks there are **3 border cases** *(measured)*, and only one of
them is a question a judge can settle:

| case | why it left the mechanical path | does the rubric decide it? |
|---|---|---|
| `flask#5014` — the issue names `Blueprint` | REFUSED by G4 | **Yes** — is being named enough to make it contract? |
| `pytest#10356` — `MarkDecorator` in `__all__` | REFUSED, dynamic reach | No — settled mechanically |
| `pytest#10356` — `collection_reverse` | UNVALIDATED, oracle blind to order | No — needs a better oracle, not a judge |

### The one adjudication that was run *(measured, n=1)*

`repro/f4_adjudicate.py` extracts the verbatim prompt from `judge_rubric.md` §6 —
unchanged, not reworded — fills in the issue and the assertion, and sends it.

| | |
|---|---|
| provider / API | OpenAI, Responses API (`client.responses.create`) |
| model | `gpt-5.6-luna` — $0.20 in / $1.20 out per 1M tokens |
| prompt | 1,832 characters |
| tokens | **419 in / 240 out** |
| **cost** | **$0.00037** |
| verdict | **CONTRACT** |

The judge's reply, in full:

```json
{
  "verdict": "CONTRACT",
  "confidence": 0.98,
  "evidence": "Things do not work correctly if a Blueprint is given an empty name ... It would be helpful if a `ValueError` was raised when trying to do that.",
  "rationale": "The issue explicitly names the `Blueprint` API/class whose constructor must reject an empty name. Therefore the public symbol reached as `flask.Blueprint` is part of the task contract, not merely an incidental implementation choice."
}
```

**The pipeline reaches a verdict end to end** — mechanical operator → G4 refusal →
rubric → adjudicated CONTRACT, with a quoted issue span. The operator's refusal
was right, and the routing did its job. That is what n=1 shows. It shows nothing
about how often the judge is right, and no such claim is made.

**Read the rationale, not the label.** The verdict is correct, but the reasoning
leads with the *naming* rule: "explicitly names … **Therefore** the public symbol
… is part of the task contract." The word "public" appears, as a description of
the symbol — not as the independent condition that decides. The rubric's prose is
explicit that naming is a **strong proxy, not proof**, and that what settles
contract is whether the payload is public surface consumers depend on. Here the
judge reached the right answer by the weaker road.

That is not a surprise, and it is the open point flagged before running: §6's
runnable prompt encodes the simple form of the test ("if the issue names the
payload → CONTRACT"), while the refinement lives in the rubric's prose and never
reaches the model. On `flask` both roads arrive at CONTRACT, so this case cannot
distinguish them — it confirms the routing works and leaves the judge's
discrimination untested. **A case where the two roads diverge is the one worth
running next**: an issue that names an internal symbol it merely proposes, where
naming says CONTRACT and public-surface says FORM.

**One schema deviation, small but real:** the rubric specifies
`confidence: "high | medium | low"`; the model returned the float `0.98`. The
reply is otherwise well-formed JSON with the right keys and a genuinely elided
quote from the issue, but a strict parser in an automated pipeline would reject
it. Worth fixing in the prompt before this is run at any scale.

**Why that model** *(a judgement call, not a measurement)*. The task is
short-context reading against an explicit decision procedure, not code synthesis,
so the cheapest current-generation model is the right tier. The cheapest
available was not taken (`gpt-5-nano`, $0.05 / $0.40): a judge that returns the right
label for the wrong reason defeats the purpose of routing to a rubric at all,
which is the audit trail — and, as above, even this model partly did that. Price
is not the binding constraint at this size: one case across the range from
`gpt-5-nano` to `gpt-5.1` costs roughly $0.0001 to $0.003. `--model` re-runs the
same prompt on a stronger judge for a fraction of a cent.

*Correction, twice over.* An early estimate put this at ~$0.04 per case, assuming
the whole rubric document entered the prompt; it does not, since §6 is
self-contained. A second put it at ~$0.001. The measured figure is **$0.00037** — the estimate was
still nearly 3× high, because the reply was shorter than assumed. Small numbers,
but the pattern is the point: every estimate in this work has run high until it
was measured.

The inputs and the result are committed under
`overlays/pallets__flask-5014@formcheck-1/` (prompt, reply, issue, task meta), so
they survive deletion of the `f4/` working tree — and the script falls back to
reading them from there when `f4/` is gone.

---

## 9. Radical honesty

**Measured.**
Coupling prevalence, 35% vs ~2–4%, and the signal-type distribution
(218/182/68/46), from the July corpus scan. The four-gate result on
`pytest#10356` and `H_dup`'s survival. The outcome distribution (WITNESS 3 / CLEAN 2 / INVALID 0 / REFUSED 2 /
UNVALIDATED 1 / NOT_APPLICABLE 7) over 15 rows — 12 operator-slots, 8 of them
anchor-cases. Mount rate 4/5 and control rate 2/4. The grader
provenance check: 17 logs, 17 agreements. The synthetic probe's baseline→witness
flip. The one adjudication: CONTRACT, 419/240 tokens, $0.00037 — a single routed
case, not a judge accuracy figure.

**Correction to the line above (2026-09-09).** This section previously reported
the grader provenance check as *"12 logs, 12 agreements"*, and
`writeup-v2-repair.md` carried the same figure while §8 of this document said
**17 of 17** — a number that contradicted itself inside the honesty section,
which is the worst place in the repository for one. **17 is correct.** The
artefact settles it without interpretation: `repro/f1_grader_provenance.py` globs
`log_*.txt`, counts what it finds, and prints the total; there are 17 such logs
and all 17 agree. They have been 17 since this repository's first commit
(`evidence/tier-axis`, `a95db58`), so the 12 was already false when it was
committed here — it was
carried over unchecked from the pre-repository July rig, where it described a
smaller log set. **The error ran in the conservative direction:** it understated
the corroboration by five logs. No claim anywhere rested on the difference, and
re-running the script prints the count, so this was checkable at any time and was
not checked.

**Qualitative — direction, never a percentage.**
The type→repairability mapping. The auto-repairable fraction, which shrank
threefold under audit to single digits. The comparison in §6.3 against this project's own
July labels.

**Open.**
The real prevalence of mock coupling under `symbol_rename` — reachable,
unmeasured. The reliability of the semantic judge, still untested: the one case
that was run could not discriminate the naming rule from the public-surface rule, and
its reply broke the rubric's own `confidence` schema. Whether an oracle stronger
than a name-set changes the invalid rate. The anchor availability rate across a
real corpus. Behaviour inside Harbor images. Any non-Python corpus.

**Three things that constrain every number above.**

1. **n=3 tasks is a mechanism demonstration.** Not a rate, not a coverage figure,
   not an extrapolation.
2. **The 0/5 invalid-transform rate is bounded by the oracles, not by the
   operators.** `pytest#10356`'s oracle watches a *set* of marker names, so it is
   blind to order and duplication. The other tasks have no hand-written contract
   oracle at all: there, only operators whose sole realistic failure mode is loud
   (an incomplete rename raising on first use) are judged, using the task's own
   P2P suite — which cannot verify the issue's fix still works. That gap is known
   to be real: on `pytest#10356` the `bug_none` mutant broke the fix and passed all
   79 P2P tests. **A stronger oracle finds more invalid transforms, never fewer.**
3. **This was Windows and subprocess; it is now Linux and containers.** This
   constraint first read: *"This is Windows and subprocess, not Harbor and
   containers"* — `verifiers` v1 does not import on Windows without an `fcntl`
   shim, and importing `swebench` installs an asyncio policy that breaks every
   subprocess the runtime starts. That was true of the July rig and is now true
   of nothing, for the same reason recorded in §5: M0 (`evidence/m0-gate`,
   `4ab9760`) moved
   the check onto verifiers' own `DockerRuntime`, inside the task's own image,
   and returned seven verdicts identical to the July rig's on operator, anchor,
   verdict and refusal reason. Both shims belong to the host-side rig and are
   unnecessary on Linux (`CHANGES.md` 3). What is still not demonstrated is a hub
   SWE environment, which is the limit §5 states.

**Errors made here, and what each one bought.** These are in the writeup because
each is now a rule or a check, and because the method's credibility rests on the
ones caught, not on the ones missed.

| what went wrong | how it surfaced | what it became |
|---|---|---|
| `git clean -fd` never deletes `__pycache__` (gitignored); stale bytecode made the oracle fail in the case *after* the one that caused it — a defect present in the July rig too | results disagreeing between phases | `run_case.restore()` purges bytecode. Re-running Phase 0, Phase 2 and the four July gates changed **no** published result |
| the graded tests ran in the runtime's scratch dir, collected zero tests, and produced **4 witnesses, 2 false** | contradiction with an earlier phase | the mandatory control of §4.1 |
| pointing `runtime.workdir` at the checkout **deleted it**: `SubprocessRuntime.stop()` does `shutil.rmtree(self.workdir)` | the next run could not find the repo | chdir inside the child process, plus a guard that refuses to run if the runtime's workdir is the checkout |
| the classifier did not recognise `mock`'s error phrasing, and attributed failures by scanning all `E ` lines — including ones printed by *passing* tests | the synthetic probe | phrasing added; failures attributed through their own pytest failure block |
| the "operator is structurally confined to the minority" claim | writing the probe to check it | retracted in §6.4 |
| two patches to the probe silently failed to apply, and two runs used stale code while reporting success | `grep` after the fact | verify replacements landed before trusting a run |

---

## 10. What this gives Prime

**An admission gate with an executable witness, in the place where admission
already happens.** `validate` gains a third check. A task that fails it comes with
a diff you can apply and a test log you can read — not a score, not an opinion.
The output of a `formcheck` failure is the counter-example itself.

**A check that knows what it cannot judge.** `UNVALIDATED`, `REFUSED` and
`unchecked` are first-class outcomes with distinct meanings: *I cannot see this*,
*the issue may specify this*, *this harness has not earned the right to report*.
A validation tool that reports confidently on an environment it cannot reproduce
is worse than one that abstains, and the July precedent for that judgement is
Prime's own: absence of a check must not read as agreement.

*Superseded, the way §5 and §9.3 are.* This paragraph first read: *"Half our
attempted corpus ended in the third, correctly."* That was true of the July rig,
where 2 of 4 mounted tasks reached a valid control and the rest correctly
abstained. It is now true of nothing: inside the tasks' own images the rate is
**494 of 500 controlled**, so the harness abstains on 1.2% rather than half
(`REPORT.md` §8). The argument the sentence was making is unaffected and is the
stronger for it — abstention remained available and fired six times, on tasks
named in `REPORT.md` §8, rather than being designed out once it became rare.

**A complement to Agentic Judging, in a different position in the pipeline.**
`AgenticJudgeEnv` shipped 2026-08-07 (verifiers 0.3.0 / prime-rl 0.8.0). By
default it does not *overrule* the deterministic tests — it **replaces** them:
`task_weight = 0.0`, `judge_weight = 1.0` (`env.py:261-268`), applied at
`env.py:330-333`. The judge is explicitly told that "recorded scores can be wrong
and references can be narrower than the task… Your verdict is what YOU verified
by execution" (`env.py:92-96`), and it is not trained (`env.py:320`), so whatever
bias it has is static and reaches every rollout. The verdict *channel* is
defended — `setup` removes any pre-seeded verdict file and names the
planted-symlink attack (`env.py:185-193`) — but there is no calibration, no ground
truth, and no adjudication against a verdict that is simply wrong.

`formcheck` sits before that, once per task, deterministically: it decides
mechanically whether a task's reward can reject a correct solution at all. One is
a per-rollout substitution whose error rate is currently unknown; the other is a
per-task check whose output is a runnable witness. Knowing which tasks genuinely
need the judge is not only a cost question — it bounds how much reward surface is
handed to an uncalibrated verdict.

**And a concrete deployment answer:** run it inside Harbor images. The
reproducibility data in §7 is the argument, and it is the single change that would
move this from a demonstration to something that could sweep a corpus.

---

## Appendix — run it yourself

**This appendix reproduces the n=3 claims in this document.** For the 500-task
numbers — the 22.2%, the per-task records, the aggregate — use
[REPORT.md Appendix A](REPORT.md#appendix-a--reproduce-it) instead; it needs only
a venv and the committed records, and no July rig at all. The two do not overlap.

Setup is one-time and lives in [`repro/README.md`](repro/README.md): a pytest
clone at the task's base commit, three venvs, and `verifiers` at `04b0bf5` with
`verifiers-formcheck.patch` applied, laid out as siblings under one root. With
that in place, from `formcheck/repro/`:

```bash
export PYT=../../.venv-pytest/bin/python   # runs the task's tests
export PYG=../../.venv/bin/python          # runs the swebench grader
export PYV=../../.venv-vf/bin/python       # verifiers + the formcheck patch
# on Windows these are ../../.venv-*/Scripts/python.exe
```

Every quantitative claim above then has a script and an exact command.

**The original false negative, and the mechanical witness that reproduces it**

```bash
$PYT run_case.py gold ; $PYG grade.py log_gold.txt     # 1.0
$PYT run_case.py alt  ; $PYG grade.py log_alt.txt      # 0.0  (hand-written, July)
$PYT oracle.py                                          # base ['foo'] ; alt ['bar','foo']
$PYT f0_witness.py                                      # mechanical transform + oracle
$PYG f0_gate.py                                         # binary verdict + control table
```

**The transform family, classified**

```bash
$PYT f2_worker.py     # applies every applicable operator; writes f2_cases.json
$PYG f2_gate.py       # WITNESS / CLEAN / REFUSED / UNVALIDATED / N-A + invalid rate
$PYG f2_overlay.py    # evidence in overlay form (arguments, tiers, preconditions)
```

**On the real verifiers path**

```bash
$PYV f3_run.py        # _run_check(task, cfg, "formcheck") -> the results.jsonl row
```

Patch: `../verifiers-formcheck.patch` (+52 −9 across 3 files, base
`origin/main` `04b0bf5`).

**Multi-task**

```bash
$PYG f4_mount.py --parquet <verified.parquet> <instance-ids...>   # mount rate
$PYG f4_formcheck.py                                              # control + family
$PYT f4_mock_probe.py                                             # synthetic probe
$PYG f4_adjudicate.py --dry-run                                   # render the prompt, spend nothing
$PYG f4_adjudicate.py                   # one OpenAI call (gpt-5.6-luna, $0.00037)
$PYG f4_adjudicate.py --model <a-stronger-model>                  # same prompt, stronger judge
```

**Grader provenance**

```bash
$PYG f1_grader_provenance.py    # this grader vs a literal transcription of v0.2.1
```

Resolution is decided by upstream `swebench` 4.0.3 (`get_eval_tests_report` /
`get_resolution_status`); no grading logic was reimplemented. The caller here
reproduces how `verifiers` called it at tag **v0.2.1** (2026-07-20). That path no
longer exists — the v0 stack was removed on 2026-08-31 (`66a6064`) — so there is
nothing in-repo left to diff against, and the script instead transcribes the
v0.2.1 implementation literally and checks both agree on every captured log:
**17 of 17**. It is therefore described as an offline SWE-bench-format grader, not
as "the verifiers grader".

**Artefacts**

- `judge_rubric.md` — the border-adjudication judge (separate artefact)
- `overlays/pytest-dev__pytest-10356@rewardpatch-1/` — the July repair, kept as
  the case that produced the investment
- `repro/overlay_f2/…@formcheck-1/` — per-transform evidence: the diff, the
  equivalence argument, the tier, the checked preconditions, the graded outcome
- `overlays/pallets__flask-5014@formcheck-1/` — the one adjudication: rendered
  prompt, the judge's reply, the issue and task meta it was run against
- `writeup-v2-repair.md` — the previous, repair-framed writeup, kept for
  provenance
