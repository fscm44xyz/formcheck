# formcheck at scale — M0 to M4

`formcheck` asks the question a gold check cannot: does a task's reward reject a
*correct* solution written differently? It answers by transforming the reference
solution in ways that preserve behaviour and re-running the graded tests. A
transform that keeps the task's stated contract and still scores 0.0 is a witness
that the reward is coupled to the incidental form of the gold patch.

This report covers the scale work: running that check inside each task's own
epoch-pinned image, on verifiers' own runtime, across all 500 tasks of SWE-bench
Verified.

**The result in one sentence.** 22.2% of *controlled* SWE-bench Verified tasks —
those whose reference solution reproduces its own score inside its own image, 494
of the 500 — have a reward coupled to the form of the gold patch, and in the
median coupled task **every graded test fails** under a rename that changes no
behaviour, because renaming a module-level symbol stops the test module
importing, so the suite does not partially fail: it does not run.

The percentage says how many tasks are affected. The second half says what
happens inside them, and it is the stronger claim: on those tasks the reward
carries no information about whether the solution works.

*Fifteen minutes rather than forty: [README.md](README.md) is the one-page
version.*

---

## Contents

| | |
|---|---|
| [1. The number](#1-the-number) | the rate, both denominators, why one operator |
| [2. The 28, case by case](#2-the-28-case-by-case) | are these reward bugs or interface changes |
| [3. What changes for a customer](#3-what-changes-for-a-customer) | blast radius, encounter rate, what the number is |
| [4. What the number rests on](#4-what-the-number-rests-on) | controls, attribution, the checks that found nothing |
| [5. The ceiling](#5-the-ceiling) | anchor availability, unparsed logs, `on_prime_hub` |
| [6. Routing the border](#6-routing-the-border-and-what-a-judge-would-cost) | the 631 refusals, and what a judge would cost |
| [7. The defect family](#7-the-defect-family) | nine defects, one shape — the result that survives the number |
| [8. Reproducibility](#8-reproducibility-executed-rather-than-argued) | 2 of 4 on the July rig became 494 of 500 |
| [9. What this does not show](#9-what-this-does-not-show) | the limits, and what a hub-side run would close |
| [Appendix A — reproduce it](#appendix-a--reproduce-it) | copy-pasteable, pinned versions |
| [Appendix B — what the run cost](#appendix-b--what-the-run-cost) | 9.15 h, 2.26 TiB, zero leaks |

---

## 1. The number

> **22.2% of controlled SWE-bench Verified tasks — 28 of 126, Wilson 95%
> [15.8%, 30.2%] — reject a behaviour-preserving rename of an internal symbol
> the gold patch touches. In 15 of those 28, *every* graded test fails; the
> median coupled task loses 100% of its suite (§3a).**

The scope belongs in the sentence, so it is written there: `symbol_rename` only,
over tasks whose reference solution reproduced its own score in its own image.

### What the transform is, and why it preserves behaviour

The perturbation is an **alpha-rename**: a module-level definition and every
static reference to it are renamed together, including `from X import name`. No
expression's value changes, no branch is added or removed, no call order moves.
The equivalence argument and the condition that would defeat it are carried by
the operator itself, not asserted here:

| operator | tier | observable | equivalence argument | what breaks it |
|---|---|---|---|---|
| `symbol_rename` | HIGH if `_`-private, else MEDIUM | symbol identity | renaming a definition and every static reference to it is a pure alpha-rename; no expression's value changes | the name is reached by a path the rewrite cannot follow: an `__all__` entry, a `mock.patch` target, `getattr`, an entry point |

**Tier** is the operator's own confidence in that equivalence argument for a given
anchor — HIGH where the argument is strongest, MEDIUM where it rests on a scan
rather than a convention. It is set in code, and the rule shown here has been
fixed since before any result existed, which is what lets it serve as the
sensitivity axis in §2.

Equivalence is **argued and regression-checked, never proven**, and the word
proof is not used. The defeating condition is not left to inspection: the
dynamic-reach precondition scans **the entire production tree** — an `__all__`
entry in a package `__init__` is exactly the case a narrower scan misses — and
refuses the **anchor**, the particular symbol an operator offers to transform on
a task, when it finds one. It refused 130 anchors in this run, so it is not a
vacuous check. Anchors are the unit almost everything downstream counts: the
denominator below, the coverage ceiling in §5 and the routing map in §6. The
other three operators carry their own arguments and tiers in `writeup.md` §3.1.

### What the denominator is

| | |
|---|---|
| witness **rows** | **34** |
| witness **tasks** — a task counts once however many of its rows are witnesses | **28** |
| **denominator: tasks with ≥ 1 *judged* `symbol_rename` case, among the 494 controlled** | **126** |
| judged **rows** (WITNESS + CLEAN + INVALID) | **234** |

**Both rates, because both are defensible and a reader will compute the second
one anyway:**

| unit | rate | Wilson 95% |
|---|---|---|
| **tasks** — the headline | **28 / 126 = 22.2%** | [15.8%, 30.2%] |
| rows | 34 / 234 = **14.5%** | [10.6%, 19.6%] |

The task-level rate leads because `STOPPING_RULE.md` fixed that unit before any
result existed, verbatim: *"W counts **tasks**, not rows: a task with three
witness rows counts once. The extrapolation below is to tasks, so the numerator
must be tasks too."* That is the only reason it leads, and it is checkable in a
commit that predates the data — tag `evidence/stopping-rule` (`78c547b`).

**Why the two differ, since "any-of" rates usually differ for a bad reason.** The
obvious inflation — witness tasks winning by having more anchors to try — is not
present. Witness tasks carry a mean of **1.89** judged anchors against **1.85**
for non-witness judged tasks, and **21 of the 28 have exactly one**, so there is
no multiplicity to harvest. The gap comes from the other end of the distribution:
a few clean tasks carry 16 and 24 judged anchors apiece, which inflates the *row*
denominator without adding a task. Neither rate is wrong; they answer "how many
tasks are affected" and "how often a given anchor is coupled", and the first is
the question this work was scoped to.

The denominator is **not 500** and **not 494**. A task enters it only if
`symbol_rename` found an in-scope anchor *and* the resulting run was judgeable —
not refused by a precondition, not `UNVALIDATED` for an unreadable log. 126 of
the 494 controlled tasks qualify. The 34 → 28 collapse is six extra rows on two
tasks: five symbols in `django/core/validators.py` on `django-13212`, two in
`pylint/pyreverse/utils.py` on `pylint-4551`, and one name defined in two
different modules on `sphinx-7590`.

### Why only this operator, stated before anyone else states it

**This number measures something narrow, and the narrowness is measured, not
hidden.** It covers one perturbation — renaming an internal symbol — out of four
the family implements. The other three contribute nothing to it, and the reason
is not that they were tried and failed: they found no anchor to transform on
96–100% of the corpus (§5). `message_reword` found none on any of 491 tasks.

Two independent constraints select this operator, and both are measured:

1. **Anchor availability.** `symbol_rename` finds an in-scope anchor on 98.4% of
   controlled tasks; the next-best operator manages 3.5%.
2. **Judgeability.** `symbol_rename` is the only operator whose failure mode is
   LOUD, so the task's own suite is a sufficient oracle. The other three fail
   silently and their cases are `UNVALIDATED` without a hand-written contract
   oracle nobody has for 500 tasks.

So the honest reading is: *of the four form-perturbations this work can apply,
one is both widely applicable and self-judging, and on that one the coupling rate
is 22.2%.* It is not a claim about form-coupling in general, and §9 says so
again.

### By sampling stratum

| stratum | tasks | witness / judged | rate | Wilson 95% |
|---|---|---|---|---|
| single-file | 430 | 19 / 96 | 19.8% | [13.1%, 28.9%] |
| multi-file | 70 | 9 / 30 | 30.0% | [16.7%, 47.9%] |

Reported separately and never blended, as specified before M3 ran. **The
intervals overlap across most of their range**, and at these denominators the two
rates are not separable. The difference is not a finding.

### Every operator, by count — never merged into a percentage

```
symbol_rename        WITNESS=34  CLEAN=196  REFUSED=545  UNVALIDATED=25  INVALID=4  NOT_APPLICABLE=8
kwonly_specialize    REFUSED=86  UNVALIDATED=1  NOT_APPLICABLE=475
collection_reverse   UNVALIDATED=6  NOT_APPLICABLE=486
message_reword       NOT_APPLICABLE=491
```

`symbol_rename` is the only operator whose failure mode is LOUD: an incomplete
alpha-rename raises `AttributeError`/`ImportError`/`NameError` *naming the
symbol*, so the task's own PASS_TO_PASS suite is a sufficient oracle for it.
Every other operator fails silently, so on a task with no hand-written contract
oracle its cases are `UNVALIDATED` and cannot enter a rate. Across the whole run
the loud/silent partition is **234 judged cases and 34 witnesses on the loud
side, 0 and 0 on the silent side**, measured from the rows rather than asserted
from the operator table.

That scoping is structural, not conventional. `witness_rate` has no operator-less
arity, and the serializer walks the finished report and refuses to write any
rate-shaped object that does not name its operator. Emitting a family-wide
percentage requires deleting a guard, which shows up in a diff.

`scale/STOPPING_RULE.md` fixes the threshold at W ≥ 3 witness tasks in 50 for
"M4 is worth the weekend, and the number leads"; it was committed at
`evidence/stopping-rule` (`78c547b`) at 14:39 on 2026-09-08, before M3's ids were
frozen at `evidence/ids-frozen` (`fb930c8`) at 16:25 and before M3's results
existed at `evidence/m3-results` (`294ef59`) at 18:24. M3 returned W = 4, with
the rule's validity precondition of at least 40 of 50 controlled met at 50/50.

Those three tags are the durable handles, and the hashes beside them are only
today's values: this repository's history has been rewritten once already, which
killed every hash this paragraph originally cited. Verify the ordering with

```bash
git merge-base --is-ancestor evidence/stopping-rule evidence/ids-frozen \
  && git merge-base --is-ancestor evidence/ids-frozen evidence/m3-results \
  && echo "threshold -> sample -> result: ordering holds"
```

The 34 witness rows share one observable: `symbol identity (module-level name)`.
By repo: django 18, sphinx 4, pylint 3, pytest 3, scikit-learn 2, astropy 1,
requests 1, xarray 1, sympy 1.

---

## 2. The 28, case by case

The objection this table exists to answer: *are these reward bugs, or legitimate
interface incompatibilities?* An alpha-rename of a symbol that is genuinely part
of a public interface would be an interface change, and a grader that catches it
would be doing its job.

**The criterion, applied mechanically to every anchor before it was transformed,
and uniform across all 28:**

1. **No `__all__` entry and no string-literal reach, anywhere in the production
   tree.** The scan root is the whole repository, not the target file, precisely
   so a re-export in a package `__init__` is visible. Any anchor that tripped it
   was `REFUSED` and never renamed — that happened 130 times in this run.
2. **Not named in the task's own issue text.** An anchor the issue names is
   `REFUSED` as a candidate contract and routed to the rubric — 301 times in this
   run. Re-checked independently for this report by searching each task's
   `problem_statement` for its symbol: **0 of 33 witness symbols appear.**

| task | symbol | file | tier | private by name/module | graded tests failing | side |
|---|---|---|---|---|---|---|
| `sphinx-doc/sphinx-7590` | `DefinitionParser` +1 | `sphinx/domains/c.py` | MEDIUM | — | **25/25** = 100% | p2p coupling |
| `sphinx-doc/sphinx-7454` | `_parse_annotation` | `sphinx/domains/python.py` | HIGH | yes | **28/28** = 100% | p2p coupling |
| `scikit-learn/scikit-learn-14983` | `_build_repr` | `sklearn/model_selection/_split.py` | HIGH | yes | **107/107** = 100% | p2p coupling |
| `scikit-learn/scikit-learn-14141` | `_get_deps_info` | `sklearn/utils/_show_versions.py` | HIGH | yes | **3/3** = 100% | p2p coupling |
| `pylint-dev/pylint-4604` | `VariablesChecker` | `pylint/checkers/variables.py` | MEDIUM | — | **21/21** = 100% | f2p only |
| `pylint-dev/pylint-4551` | `get_annotation` +1 | `pylint/pyreverse/utils.py` | MEDIUM | — | **10/10** = 100% | f2p only |
| `psf/requests-1766` | `HTTPDigestAuth` | `requests/auth.py` | MEDIUM | — | **85/85** = 100% | p2p coupling |
| `django/django-15973` | `MigrationAutodetector` | `django/db/migrations/autodetector.py` | MEDIUM | — | **158/158** = 100% | p2p coupling |
| `django/django-15851` | `DatabaseClient` | `django/db/backends/postgresql/client.py` | MEDIUM | — | **9/9** = 100% | p2p coupling |
| `django/django-15380` | `MigrationAutodetector` | `django/db/migrations/autodetector.py` | MEDIUM | — | **134/134** = 100% | p2p coupling |
| `django/django-14376` | `DatabaseClient` | `django/db/backends/mysql/client.py` | MEDIUM | — | **9/9** = 100% | p2p coupling |
| `django/django-12155` | `parse_docstring` | `django/contrib/admindocs/utils.py` | MEDIUM | — | **7/7** = 100% | p2p coupling |
| `django/django-11433` | `construct_instance` | `django/forms/models.py` | MEDIUM | — | **143/143** = 100% | p2p coupling |
| `django/django-11179` | `Collector` | `django/db/models/deletion.py` | MEDIUM | — | **41/41** = 100% | p2p coupling |
| `astropy/astropy-12907` | `_cstack` | `astropy/modeling/separable.py` | HIGH | yes | **15/15** = 100% | p2p coupling |
| `django/django-13121` | `Combinable` | `django/db/models/expressions.py` | MEDIUM | — | **140/169** = 83% | p2p coupling |
| `django/django-14315` | `DatabaseClient` | `django/db/backends/postgresql/client.py` | MEDIUM | — | **9/11** = 82% | f2p only |
| `pytest-dev/pytest-5809` | `create_new_paste` | `src/_pytest/pastebin.py` | MEDIUM | yes | **3/4** = 75% | p2p coupling |
| `django/django-15572` | `get_template_directories` | `django/template/autoreload.py` | MEDIUM | — | **4/11** = 36% | p2p coupling |
| `pydata/xarray-4966` | `UnsignedIntegerCoder` | `xarray/coding/variables.py` | MEDIUM | — | **8/25** = 32% | p2p coupling |
| `django/django-13212` | `RegexValidator` +4 | `django/core/validators.py` | MEDIUM | — | **2/7** = 29% | p2p coupling |
| `sphinx-doc/sphinx-7757` | `signature_from_str` | `sphinx/util/inspect.py` | MEDIUM | — | **7/34** = 21% | p2p coupling |
| `django/django-14771` | `get_child_arguments` | `django/utils/autoreload.py` | MEDIUM | — | **9/61** = 15% | p2p coupling |
| `django/django-14311` | `get_child_arguments` | `django/utils/autoreload.py` | MEDIUM | — | **8/60** = 13% | p2p coupling |
| `sympy/sympy-13031` | `MutableSparseMatrix` | `sympy/matrices/sparse.py` | MEDIUM | — | **1/10** = 10% | f2p only |
| `django/django-13195` | `CookieStorage` | `django/contrib/messages/storage/cookie.py` | MEDIUM | — | **28/387** = 7% | p2p coupling |
| `pytest-dev/pytest-7521` | `FDCaptureBinary` | `src/_pytest/capture.py` | MEDIUM | yes | **2/127** = 2% | p2p coupling |
| `pytest-dev/pytest-10356` | `get_unpacked_marks` | `src/_pytest/mark/structures.py` | MEDIUM | yes | **1/80** = 1% | f2p only |

`+n` marks a task with n further witness symbols; the row shows the widest blast
radius. Sorted by blast radius, which is §3.

**Where this evidence stops, and the limit of the criterion.** The criterion is
"not re-exported and not named in the issue". It does **not** consult the
project's own documentation, and no offline artefact in this repo can.

The limit is sharper than that, and worth naming precisely: **absence from
`__all__` is not evidence of privateness in a project that does not use `__all__`
at all**, and nothing offline tells us which of these twelve projects those are.
The precondition was built to *refuse re-exported symbols* — a soundness guard on
the rename — and it does that job. It was never built to *certify a symbol as
non-public*, which is a stronger claim, and it is being asked for one here.

So a reader who holds that a symbol importable from a non-underscore module is
public interface regardless of `__all__` will contest some of these 28, and the
most likely names are not a mystery: **`HTTPDigestAuth`** in `requests/auth.py`
(`psf/requests-1766`) and **`RegexValidator`** / **`URLValidator`** in
`django/core/validators.py` (`django/django-13212`, which carries three further
`validate_*` symbols from the same module). Those three symbols sit on **two**
tasks, not three.

Striking them costs almost nothing, which is the point:

| | tasks | over 126 | Wilson 95% |
|---|---|---|---|
| as reported | 28 | **22.2%** | [15.8%, 30.2%] |
| less `requests-1766` and `django-13212` | 26 | **20.6%** | [14.5%, 28.5%] |
| less also `Combinable` and `MutableSparseMatrix`, the next most arguable | 24 | **19.0%** | [13.1%, 26.8%] |

That objection is answered with a sensitivity analysis rather than an argument.
The `private by name/module` column applies a deliberately over-strict rule — the
symbol or a component of its path starts with `_` — which no reasonable person
disputes:

| set | tasks | over 126 | Wilson 95% |
|---|---|---|---|
| all witnesses | 28 | **22.2%** | [15.8%, 30.2%] |
| symbol or module `_`-private | 7 | **5.6%** | [2.7%, 11.0%] |
| HIGH tier (`_`-private name) | 4 | **3.2%** | [1.2%, 7.9%] |

The strict rule is too strict — it excludes `MigrationAutodetector` and
`get_child_arguments`, which are internal machinery by any reading — so 5.6% is
not the better estimate. It is what survives the most hostile reading of
"internal" — a floor on *this* rate, under a stricter definition of the same
channel, and not to be confused with the cross-channel floor §3(c) withdraws.
Even there the interval clears zero.

**Two decisions here, recorded as decisions rather than left as absences.**

*Dropping cases was permitted and declined.* The brief for this table allowed any
of the 28 that could not be defended from the records to be dropped from the
count. None was — and not because all 28 are self-evidently internal, but because
the evidence that would adjudicate the contested ones case by case is the
projects' own documentation, which is not in the records and cannot be
reconstructed offline. Dropping a subset would have meant substituting a judgment
call for evidence and then reporting the survivors as though they had been
checked. The sensitivity analysis is what that judgment looks like when it is
made honestly: it hands the reader the range instead of picking a point inside it
and calling the point a measurement.

*The sensitivity axis predates the results.* HIGH/MEDIUM is not a partition
invented for this table. `symbol_rename` has carried "HIGH if `_`-private, else
MEDIUM" in `repro/f2_operators.py` since `evidence/tier-axis` (`a95db58`,
2026-09-07 15:48) — before the first pilot records exist
(`evidence/m1-pilot`, `e8f3c0c`, the following afternoon), and long
before any witness was known. The M4 run reads its tier from that same module
through the hook, so the column is the operator's own pre-committed confidence in
its equivalence argument, not a post-hoc split chosen with the answers visible.

---

## 3. What changes for a customer

### (a) Blast radius, measured — how much of the graded suite a rename destroys

For each of the 28, how many graded tests fail under the equivalent rename, out
of how many graded tests the task has. Both numbers come from the witness row's
own grading report, and the totals reconcile exactly with the dataset's
`FAIL_TO_PASS` + `PASS_TO_PASS` lists on all 28.

| share of the graded suite that fails | tasks |
|---|---|
| **100% — every graded test fails** | **15** |
| 50–99% | 3 |
| 20–49% | 4 |
| 5–19% | 4 |
| < 5% | 2 |

**Median 100%. In 15 of 28 tasks, a rename that changes no behaviour fails the
entire graded suite** — 158 of 158 tests on `django-15973`, 143 of 143 on
`django-11433`, 107 of 107 on `scikit-learn-14983`, 85 of 85 on `requests-1766`.
Across all 28, 1017 of 1781 graded tests fail.

The distribution matters more than the aggregate, and it is bimodal, not smooth.
The mechanism is visible in the logs: renaming a module-level symbol makes the
*test module fail to import*, so the suite does not partially fail — it does not
run. That is why the modal outcome is 100% and not "one test asserts the name".
The tail is the other shape: 1 of 80 on `pytest-10356`, 2 of 127 on
`pytest-7521`, where a single test references the name and the rest are
unaffected.

For a customer this is the difference between a grader that is slightly noisy and
one that returns 0.0 on a fully correct solution because a helper has a different
name. Fifteen of these twenty-eight are the second kind.

### (b) Encounter rate, not measurable here

What this does **not** give is how often a real policy is actually penalised.
That is the product of two things: this coupling, which is measured, and the
**encounter rate** — how often a policy's correct solution differs in form from
the gold in a way that trips it — which is not. A grader can be maximally coupled
to a name and cost nothing if every correct solution happens to choose that name.

The mechanism is established; the magnitude is not, and no number is offered for
it. The experiment that would measure it is specific: run a policy on these 28
tasks, take the solutions that are correct by judgment, and count how many score
0.0. That requires generating rollouts from a model — inference — which this
project deliberately does not use anywhere, so it is named as future work rather
than estimated.

### (c) What 22.2% is, and what it is not

An earlier draft of this section argued that 22.2% is a **floor**: a rename is
the smallest semantic change in the family, a real policy varies structure and
ordering too, so coupling found by the weakest probe must lower-bound the
coupling a policy would meet. **That argument does not hold and is withdrawn
rather than softened.**

Its hidden step is that *smallest semantic change* implies *least test-visible*.
Those are different properties and the second does not follow. **Test suites
reference code by name** — they import symbols. A solution that restructures
helpers, reorders operations or decomposes differently while preserving the
public names and entry points may break **fewer** tests than a rename does,
because the tests still import exactly what they imported before. On that
reading `symbol_rename` is the *most* test-visible operator in the family, not
the least.

**The one piece of evidence in these records bears on the question, and it cuts
against the floor reading.** The mechanism behind §3(a)'s 100% median is
*import failure*: renaming a module-level symbol stops the test module importing.
That is a channel a rename hits squarely and a structural rewrite that preserves
entry points does not hit at all. Fifteen of the twenty-eight coupled tasks fail
by exactly that route. So the dominant mechanism found here is one that is
specific to renaming, which is a reason to expect the name channel to be
*unusually* visible to a test suite rather than representative of the others.

Nothing in this run measures the other channels. The three operators that would
probe them produced **zero judged cases** — not a null result, an absence: they
found no anchor to transform on 96–100% of the corpus (§5). So there is no
measurement here of whether structural coupling is more common, less common or
equally common than name coupling, and **the direction is unknown.**

What the number is, stated without extrapolation:

> **22.2% is a measured rate on one channel** — coupling to the identity of an
> internal symbol — over the tasks where that channel could be probed and judged.
> Its relationship to coupling on structure, ordering or decomposition is
> unmeasured, and this work does not establish whether that relationship runs up
> or down.

That is a smaller claim than a floor. It is the one the records support.

---

## 4. What the number rests on

**Controls.** 494 of 500 reference solutions scored exactly 1.0 in their own
image before any transform ran. A task whose control fails is excluded from the
denominator: it proves nothing in either direction, and counting it as "no
witness found" would convert a broken harness into evidence of a clean reward.

| graded runner | controls passed |
|---|---|
| django `./tests/runtests.py` | 227 / 231 |
| pytest | 148 / 150 |
| sympy `bin/test` | 75 / 75 |
| sphinx `tox` | 44 / 44 |

Twelve repositories, four different test runners, no era-pinning performed by
this work — the pins are in the images. The invocation is not restated here: the
command comes from `MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"]` and the
directives from `get_test_directives`, the same two objects the real SWE-bench
grader uses, so this cannot drift out of agreement with the grader silently.

**Every witness is attributed by failure text.** A failure block that *names* the
renamed symbol is coupling; one that does not is breakage and yields `INVALID`;
a log with no recognisable failure block at all is `unparsed` and yields
`UNVALIDATED`, which does not enter a denominator. The split across all 34
witness rows:

| | rows |
|---|---|
| `p2p_coupling` — coupling located in PASS_TO_PASS | 24 |
| `f2p_only` — coupling in the graded test only | 10 |
| `p2p_unattributed` | **0** |
| `unknown` | **0** |

Nothing is unattributed. Twenty-four of thirty-four witnesses live in
PASS_TO_PASS — the part of a task meant to be stable background, which a
detector inspecting only the graded test would miss entirely. That is
`writeup.md` §6.2's class, now measured at scale rather than argued from three
tasks.

**Can a parser or runner change manufacture a witness?** No, and the strongest
evidence is the worst defect in this project. #18 was exactly that failure — a
parser that understood one test runner out of the corpus's four — and its bias
ran in the **opposite** direction. Failures it could not read were resolved to
`INVALID`, which *suppressed* four real witnesses and reported `W = 0`. Widening
the parser turned `INVALID` into `WITNESS`, never the reverse: in the M3 re-run,
**exactly four rows changed and all four moved `INVALID → WITNESS`**, with 211 of
215 identical.

The direction is now structural rather than incidental. A log the attribution
cannot read is classified `unparsed`, renders `UNVALIDATED`, and **cannot enter a
denominator** — so an unreadable runner costs coverage and can never produce a
witness. And a witness requires a failure block that *names the renamed symbol*:
`p2p_unattributed = 0` and `unknown = 0` mean **no witness in this run rests on a
failure the attribution could not explain.** A future parser change can add
witnesses by reading logs currently unread; it cannot invent one from a failure it
already understands.

**Two checks that looked for a defect and did not find one.** Reported because a
reader wants to know they were run, not only that nothing turned up.

- *Does any witness rest on a failure the attribution could not explain?* **No.**
  `p2p_unattributed = 0` and `unknown = 0` across all 34 witness rows. Every
  witness is carried by a failure block that names the renamed symbol.
- *Is the judged/refused split outcome-dependent — could a task be refused
  because of how its transform turned out?* **No, and it is structurally
  impossible.** Every precondition is evaluated on the anchor *before* the
  transform is applied and before any test runs, so a refusal cannot see the
  outcome it would have produced. What a refusal removes from the denominator is
  decided by the issue text and the shape of the source, never by the reward.

**M3 reproduces inside M4 exactly.** All 50 M3 tasks are in the 500 and were
re-run as part of it. Comparing every `(instance, operator, anchor)` triple:
**zero control disagreements, zero verdict disagreements, zero row-presence
disagreements, and zero differences in the refusal *reason strings***. The
witness set is identical task for task: `astropy-12907`, `django-13195`,
`django-15572`, `pylint-4604`. Reason-string equality is the gate `SCOPE.md`
requires, because a refusal landing on the right verdict for the wrong reason is
a defect this project has already shipped once.

**The check runs on the real path.** `Task.formcheck` executes through verifiers'
own `_run_check(task, cfg, "formcheck")`, on `DockerRuntime`, with the image
resolved through `resolve_runtime_config` from `task.data.image` — the same call
by which a Harbor task reaches its container. What remains not-real is the
taskset, still a local stand-in, because no SWE-bench taskset lives in
`verifiers` any more.

**The M0 gate has never moved.** `pytest-10356` is gated against the July rig on
operator, anchor, verdict and refusal reason string. It was re-run after every
change to the hook and matches field for field.

**The anchor set is narrower than Phase 2's.** Applied mechanically, the rule
`writeup.md` §3.3 states yields `{get_unpacked_marks, store_mark}` on
`pytest-10356`; Phase 2 used a hand-picked set that also contained
`normalize_mark_list` and `MarkDecorator`, neither of which the gold patch
touches. The rule was **not** widened to recover them: widening until
known-interesting rows return is selecting for the outcome, and it would destroy
the only property that makes a null result meaningful. `scale/SCOPE.md` sets both
rules out row by row.

**Records.** All 500 record files were validated rather than counted. Each was
re-serialized in the canonical form `write_record` produces and compared to the
file on disk byte for byte; all 500 match, so none is truncated. All carry
`completed: true`, all share one 25-key schema, the set is exactly
`scale/ids_all.txt`, and no `.partial` file survives. Manifest SHA-256:
`a21338d341c8752d49c87f98923806da5fdbf35c53481e398e697521285fa2c9`.

---

## 5. The ceiling

Coverage is bounded by anchor availability, not by refusals and not by oracle
strength. This is the sharpest form of `writeup.md` §6.5's finding, and at 500
tasks it is not close.

| operator | tasks with an in-scope anchor | availability |
|---|---|---|
| `symbol_rename` | 483 / 491 | **98.4%** |
| `kwonly_specialize` | 17 / 492 | **3.5%** |
| `collection_reverse` | 5 / 491 | **1.0%** |
| `message_reword` | 0 / 491 | **0.0%** |

Three of four operators find nothing to transform on 96–100% of the corpus. The
gold patch rarely introduces the object they need: no invented keyword-only
parameter, no raised message, no returned collection. One operator carries the
entire result.

**The second half of the ceiling: 75 rows across 24 tasks whose test logs the
failure attribution could not parse.** These are `UNVALIDATED`, never `INVALID` —
an unreadable log is reported as unreadable rather than resolved to the nearest
available verdict — so they cannot manufacture a witness, and
`p2p_unattributed` is 0. They break down as:

| | rows |
|---|---|
| `symbol_rename` `UNVALIDATED` | 25 |
| `symbol_rename` `REFUSED` | 4 |
| `collection_reverse` / `message_reword` `NOT_APPLICABLE` | 46 |

**The size of what this leaves on the table, stated so a reader can judge it.**
All 25 of `symbol_rename`'s `UNVALIDATED` rows are unparsed-shape rows — every
one. They sit on 24 tasks, of which **19 are not otherwise in the denominator**.
So a parser that understood every log shape in the corpus would widen THE
NUMBER's denominator from **126 to at most 145 tasks**, about 15%, and could not
narrow it. The other 50 unparsed rows would not move: 46 are `NOT_APPLICABLE` for
want of an anchor and 4 are refusals, neither of which is a judgeability
question.

The parser was **not** widened for this report. Teaching it a fifth shape after
seeing which tasks it excluded is changing the instrument after reading the
results, and the 19 tasks are named in `summary.json` so the choice is auditable.
What can be said without widening it: the witnesses are unaffected, the
denominator is conservative, and the direction of the bias is known.

**`on_prime_hub`: unresolved on 500 of 500.** Every record carries `null` with
one reason — *not resolvable offline; no hub environment index is reachable from
this repo, verifiers or swebench*. This is **unresolved, not negative.** It
supports no claim about which of these tasks exist on the hub, in either
direction, and it is the single largest thing a hub-side run would settle for
free.

**Eligibility, measured from the gold patches with no container running:**

| | |
|---|---|
| tasks with ≥1 production `.py` in the gold patch | **500 / 500 = 100%** |
| gold patches touching exactly one file | **429 / 500 = 85.8%** |
| single-target after the M1 widening | 430 / 500 = 86.0% |
| multi-target | 70 / 500 = 14.0% |

Production `.py` files per gold patch: 1→430, 2→48, 3→12, 4→7, 5→1, 6→1, 21→1.
SWE-bench Verified is overwhelmingly single-file. Multi-file tasks were included
and reported as their own stratum, decided before the run.

---

## 6. Routing the border, and what a judge would cost

Cases the mechanical family declines are routed to `judge_rubric.md`, which stays
a separate artefact: an auditable contract-vs-form judge with a text-anchored
decision procedure and an explicit statement that no reliability metric is
claimed for it. At 500 tasks the routing map is no longer three cases.

**631 refusals across 386 tasks:**

| n | class | where it goes |
|---|---|---|
| 301 | **BORDER** — the issue names the payload | the rubric |
| 130 | G4 dynamic reach — the name appears in a string literal or `__all__` | settled mechanically |
| 58 | G4 multi-line import — the rewrite is not provably total | settled mechanically |
| 56 | G4 attribute access — reached as `obj.NAME`, not by import | settled mechanically |
| 38 | `kwonly` P1 — not a keyword-only parameter | settled mechanically |
| 29 | `kwonly` P4 — read outside a param-only branch | settled mechanically |
| 19 | source file could not be parsed | neither; a gap |

Only the first class is a question a judge can settle. The other 311 are decided
by the code and need no adjudication; the 19 unparseable sources are a coverage
gap, not a border. The 301 border cases name 247 distinct symbols, the commonest
being `Query` (13), then `Field`, `Model`, `QuerySet`, `Dataset`,
`violation_error_message` and `roc_curve` at 4 apiece.

**Cost.** One adjudication was run end to end (`writeup.md` §8): 419 in / 240 out
tokens on `gpt-5.6-luna`, **$0.00037**, verdict CONTRACT with a quoted span from
the issue.

| assumption | value |
|---|---|
| border cases to adjudicate | 301 |
| per-case cost, measured at n=1 | $0.00037 |
| **total, same model** | **$0.11** |
| total at a stronger tier (~$0.003/case) | $0.90 |

**Three assumptions, named:** that the one measured case is representative in
prompt and reply length; that each border case is one call with no retry; that
§6's prompt stays self-contained, so the rubric document does not enter the
context. The third is where the earlier estimates went wrong — ~$0.04 per case,
then ~$0.001, against a measured $0.00037.

The judge's accuracy is not measured. n = 1, and that one case reached the right
label partly by the weaker of the rubric's two roads.

---

## 7. The defect family

This is the result that survives the number. Nine defects in this work share one
shape:

> **A check that reports a verdict for a reason invisible in its own output.**

That is the exact failure `formcheck` was built to detect in other people's
graders. It kept appearing in `formcheck`. **Every one was found by inspecting
the machinery, never by a suspicious number** — because none of them produced a
suspicious number. That is what makes them a class rather than a list.

| # | what it reported | what was actually true |
|---|---|---|
| 13 | `CLEAN`/`INVALID` verdicts | the P2P coupling partition had been silently reintroduced as collapsed, turning the project's most novel finding into an "invalid transform" count |
| 16 (D2) | `CLEAN reward 1.0` | the graded memo answered from a digest that could collapse, serving the *control's* grading for a tree it never graded |
| 17 | `IDENTICAL` on the M0 gate | the gate's own reference file was regenerated by the test suite that ran against it |
| 18 | `INVALID` on four tasks | the failure attribution understood one test runner; those four were coupling, i.e. **witnesses** |
| 19 | `7/7 passed` | six tests appended below a module-level collector were never run — including the ones pinning #18 |
| 21 | every guard green | the run had burned 330 tasks in 32 minutes against a refusing registry; the disk budget passed because nothing was pulled, the control passed vacuously because it never ran |
| 22 | `remaining: 100` | the governor probed the pull quota while the block was on token issuance — a measurement that looks right and means nothing, in the code written to prevent #21 |
| 23 | **nothing at all** | two individually correct guards cancelled at their seam; the liveness check was silently disabled by the refusal-handling written to complement it |
| 24 | `abort: run-wide disk did not return to baseline` | the guard measured whole-filesystem free space; 100 MiB of the 325 was an unrelated `npm` cache write |

### #18, because it inverted the headline

`failure_sections` parsed pytest's per-test failure blocks and nothing else.
Phase 4 ran only pytest repos, so that was sufficient and looked complete. M3 ran
ten repos and found two more shapes: pytest **collection errors**, which is
precisely what an alpha-rename produces when a test imports the renamed symbol
by name, and **unittest/django**'s `ERROR: name (mod.Class)` format, which has no
underscore rules for the parser to find. Every failure in those logs came back
"no failure section found" → unexplained → the oracle concluded the transform
broke behaviour → `INVALID`. All four such rows name their symbol:

```
astropy-12907   ImportError: cannot import name '_cstack' from 'astropy.modeling.separable'
django-13195    ImportError: cannot import name 'CookieStorage'
django-15572    AttributeError: module 'django.template.autoreload' has no attribute 'get_template_directories'
pylint-4604     AttributeError: module 'pylint.checkers.variables' has no attribute 'VariablesChecker'
```

An alpha-rename changes no expression's value. A test that fails on those
messages is asserting the *name*. All four are witnesses.

**What would have been reported had it not been found.** `W = 0` witnesses over
50 tasks, with **50/50 controls passing, zero errors, zero aborts, zero digest
anomalies, and a clean 46-minute run.** Under this project's own pre-committed
stopping rule that is the branch where M4 is optional and the deliverable stops
being the number. And `0/50` is exactly what a reasonable person expects from a
curated, heavily-reviewed benchmark — the number would have confirmed a prior,
which is the worst property a wrong number can have.

It is closed rather than patched: "cannot parse" is now a third classification
alongside "coupled" and "broke", it renders `UNVALIDATED`, it cannot enter a
denominator, and `aggregate` reports it as a loud number with the offending tasks
named. §5 above is that mechanism reporting 75 rows on itself.

### #23, because correctness of parts did not compose

Two requirements, both right: *an infrastructure refusal is not a task result*,
and *assert something causally necessary — a real task cannot be fast*. The first
was implemented as an early `return`; it sat before the line feeding the second.
The refusal path skipped the liveness check entirely, and **107 tasks were cycled
in 41 seconds with nothing watching.** The run was stopped by hand.

No review of either requirement alone would have found it. A safety mechanism was
silently disabled by another safety mechanism, with no warning, no degraded mode
and no event. It was found by a person noticing that an event was *absent* —
nothing in the machinery can observe its own silence.

It was also nearly recorded backwards. From a dead process and a frozen log the
natural reading was that the invariant had fired on a cause it was not written
for. It had not: zero burn events, no `BurnDetected`, the run ends mid-queue
because a human killed it. Writing that down would have entered a guard's success
into the permanent record on the strength of a clean-looking outcome whose cause
nobody asked about — this project's own failure mode, committed about this
project's own safety mechanism.

### #24, because a guard finally fired and was wrong

M4's last task completed valid and the run aborted on the line after it: *"run-wide
disk did not return to baseline, residual 325.0 MiB"*. The arithmetic was exact.
The quantity was not a property of the run. `free_bytes()` is statvfs on the
filesystem holding the docker root, which on this host also holds `$HOME`; 100.2
MiB of the shortfall was `~/.npm` caching a registry document for an editor's
update check, 97 MB of it in one blob, and ~4 MB was the run's own records — which
the run must write and can never give back, so the guarded quantity could not
reach zero by construction.

Docker was clean and the per-task guard proved it: across 393 logged tasks,
**1,956,741,070,109 bytes pulled and 1,956,741,070,109 removed — a difference of
zero**, no image pulled and not removed, `leaked_image` false and
`leaked_containers` empty every time. The structural per-task check — *is MY
image gone, are MY containers gone* — was right 500 times and reconciles to the
byte. **It is the guard that works.**

The run-wide guard had a second defect that a threshold could not touch: gated on
`not leases.live_refs()`, and a lease is held from the start of a pull, it could
only be evaluated once the run drained. Free space was below threshold at every
quiet moment for the last three hours and it never fired, because another worker
always held a lease. A guard written to catch mid-run accumulation could fire only
on the last task.

So it was replaced rather than retuned. `unowned_footprint` asks the run-wide
question the way the per-task one is already asked: which images and containers
belonging to this harness are resident with no live lease accounting for them.
A co-tenant is in neither namespace; the run's own records are neither images nor
containers; a worker's held image is owned rather than residue, so the check is
evaluable at any moment. `CHANGES.md` 10 is not reopened — docker's own space
accounting is still not usable as a budget and orphan layers are still reclaimed
against a `df` delta. Only what may **abort** a run changed.

The abort cost nothing: `write_record` completes before the raise, so all 500
records are intact and the abort landed on the last task in the queue. Fired
eighty tasks earlier — which the arithmetic permitted and only the lease gate
prevented — it would have killed a run that was working perfectly.

### The rule, and what enforces it

> **A guard that has never fired in production is indistinguishable from a guard
> that cannot fire.**

Both present as silence. `scale/test_guards_fire.py` now proves, for every
invariant, that it is *capable* of firing: the burn detector on fast completions
and on a refusal storm, that it emits its abort event when it does, the cleanup
guard on a leaked image and on a leaked container, the run-footprint guard on an
unowned image and an unowned container, the frozen-baseline pin, the headroom
guard, the merged-rate guard, the digest guard. Seventeen tests, all asserting a
failure path.

Guards were extracted into callable functions (`check_progress`,
`check_task_cleanup`, `check_run_footprint`) to make that possible: an invariant
inlined in a loop cannot be driven to its raise, and one that cannot be tested
cannot be proven capable of firing. A test that checks only the predicate proves
arithmetic, not that anything happens.

#24 adds a corollary the first eight did not force. Two of its five new tests
assert that the guard **stays silent** — while another worker's lease holds an
image, and when `free_bytes()` returns zero. A guard proven able to fire still
needs proof it does not fire on the thing that fooled its predecessor, or the
next false positive gets retuned rather than diagnosed.

---

## 8. Reproducibility, executed rather than argued

`writeup.md` §7 concluded from five tasks that `formcheck` must run inside the
task's own image, because outside it half the corpus cannot reproduce its own
gold. That was an argument. This is the measurement.

| | July rig, outside the image | M4, inside the image |
|---|---|---|
| mounted | 4 / 5 | **500 / 500** |
| reached a valid control | **2 / 4 mounted** | **494 / 500** |

The three tasks §7 names as unreachable are all in SWE-bench Verified and all
reach a valid control in M4 on the first attempt with no pins:

- `psf/requests-1142` — did not mount at all; its 2013 `setup.py` imports the
  package to read its version, and `requests/utils.py` does not import on
  Python 3.11.
- `pytest-dev/pytest-7571` — needed pytest 6.0, which cannot run on Python 3.11.
- `pylint-dev/pylint-6903` — stalled at P2P 4/8 after three era-pins; recorded as
  `unchecked` and abandoned.

Every era-pin §7 had to discover by hand — `pytest==7.4.4`, `werkzeug==2.3.7`,
`numpy==1.26.4`, `astroid==2.11.7` — is already encoded in the image. That list
was a description of what a Docker image is for, and running inside one turns a
detector that abstains on half the corpus into one that abstains on 1.2% of it.

Every one of the 500 mounted: each has a control verdict, and a control cannot be
graded in a container that did not start. **The `mountable` field in the records
should not be read as that claim.** It is derived as *the last formcheck row
exists and carries no `error_type`*, so it reads `false` on the three tasks that
produced no row at all — `matplotlib-25775` and `matplotlib-26466`, which found
no anchor for any operator, and `matplotlib-25479`, whose only row is a refusal.
All three passed their control. The field answers a narrower question than its
name suggests; the six genuine abstentions are the control failures below.

### The six control failures

| instance | repo | F2P | P2P | first failing | control log kept |
|---|---|---|---|---|---|
| `astropy-7606` | astropy 1.3 | 1/1 | 240/241 | `test_units.py::test_compose_roundtrip[]` | no |
| `django-10097` | django 2.2 | 431/438 | 1427/1432 | `test_PasswordChangeDoneView` | no |
| `django-10880` | django 3.0 | 0/1 | 0/55 | `test_count_distinct_expression` | no |
| `django-10914` | django 3.0 | 0/1 | 0/98 | `test_override_file_upload_permissions` | no |
| `django-11276` | django 3.0 | 26/26 | 546/548 | `test_strip_tags_files` | no |
| `pylint-4661` | pylint 2.10 | 0/1 | 0/0 | `unittest_lint.py::test_pylint_home` | yes |

All six: `error: null`, `mountable: true`, verdict `HARNESS_UNPROVEN`, zero rows
emitted. They are excluded from the denominator and contribute nothing in either
direction. Two signatures are visible: **partial failure**, where the suite very
nearly passes (astropy-7606, django-10097, django-11276), and **total collapse**
at P2P 0/N, which is environmental (django-10880, django-10914, pylint-4661).
`pylint-4661`'s captured log shows a `ConftestImportFailure`.

**A schema split, recorded because it looks like corruption to anyone who finds
it themselves.** 46 of the 500 records carry a two-key `control` object
(`passed`, `reason`); the other 454 carry four keys, adding `graded` and `log`.
The split is clean in time — all 46 written between 16:26 and 16:53, all 454
from 17:19 on, no interleaving. The commit that records a failed control's own
log landed mid-run. Five of the six control failures fall in the earlier group,
which is why their triage stops at the reason string. This is a fact about the
run, not a defect, and it was not papered over by re-running them: re-running
them after seeing which ones failed is the same error as widening the parser.

---

## 9. What this does not show

- **Nothing about the other three operators.** Their combined judged-case count
  is zero. `message_reword` found no anchor on any of 491 tasks. The result is
  one operator's.
- **Nothing about how often the rubric judge is right.** n=1. The routing works;
  the discrimination is untested.
- **Nothing about hub presence.** `on_prime_hub` is unresolved on 500 of 500,
  and unresolved is not negative.
- **Nothing about tasks outside SWE-bench Verified**, and nothing about whether
  the rate would hold on a corpus that was not curated for cleanliness.
- **Nothing about the 19 tasks excluded by unparsed log shapes**, which are named
  rather than counted, and whose inclusion could only widen the denominator.
- **Nothing about the encounter rate**, which is the other half of any claim
  about cost to a customer. A witness shows a reward rejects a
  behaviour-preserving rewrite; it does not show how often a real policy would
  write that rewrite. §3(b) names the experiment that would measure it and why
  this project does not run it.
- **Nothing about coupling on any channel but the name.** Structure, ordering
  and decomposition are unprobed here — the operators that would reach them
  found no anchors — so whether coupling on those channels is more or less
  common than the 22.2% measured on names is **unknown in both directions**.
  §3(c) withdraws the argument that made 22.2% a floor, and says why.

### What a hub-side run would close

Running this inside Harbor rather than against a local mirror of the images would
settle four things this run could not:

1. **`on_prime_hub` on all 500**, from the hub's own environment index — the one
   field here that is null for an infrastructural reason rather than a
   methodological one.
2. **The image question.** 2.26 TiB was pulled and discarded to run 500 tasks,
   and 5.77 hours of a 9.15-hour run were spent asleep against an anonymous
   registry quota. Inside Harbor the image is already there. That is not a
   performance note; the pull path is where three of the nine defects lived.
3. **The taskset.** The only remaining stand-in is the local taskset object.
   Inside Harbor the real one exists, and the last gap between this and a
   production check closes.
4. **Whether the rate holds on Harbor's own tasks**, which is the question the
   500-task number is a proxy for and cannot answer.

---

## Appendix A — reproduce it

Copy-pasteable, from a clone of this repository.

```bash
git clone https://github.com/fscm44xyz/formcheck.git
cd formcheck
git checkout evidence/m4-run   # the 500 records + summary.json, tagged

python3.12 -m venv ~/.venv-fc
~/.venv-fc/bin/pip install "swebench==4.0.3" "datasets==5.0.1" "docker==7.2.0"
# verifiers 0.3.2.dev67 with the formcheck hook applied:
#   git -C <verifiers-checkout> apply verifiers-formcheck.patch
~/.venv-fc/bin/pip install -e <verifiers-checkout>

# --- no containers: the aggregate, the guards, the #18 partition, eligibility ---
~/.venv-fc/bin/python scale/aggregate.py --results scale/records_m4 -o /tmp/agg.json
~/.venv-fc/bin/python scale/test_guards_fire.py     # 17/17 -- every guard fires
~/.venv-fc/bin/python scale/test_partition.py       # 20/20 -- the #18 partition
~/.venv-fc/bin/python scale/eligibility.py          # the 500/429/430 split

# --- one task, ~2 min, needs docker + ~4.5 GiB of pull ---
~/.venv-fc/bin/python scale/run.py --instance-id django__django-13195

# --- all 500: ~9 h at 4 workers, ~2.3 TiB pulled and discarded ---
~/.venv-fc/bin/python scale/run.py --workers 4 --timeout 2700
```

The first three need no network. `eligibility.py` reads SWE-bench Verified from
the `datasets` cache, downloading it once if absent; nothing else does.

Versions this run used: Python 3.12.3, `swebench` 4.0.3, `verifiers`
0.3.2.dev67, `datasets` 5.0.1, `docker` (SDK) 7.2.0, Docker Engine 29.8.0.
Resolution is decided by upstream `swebench`; no grading logic is reimplemented.

`/tmp/agg.json` reproduces `scale/summary.json` on every key except the three
blocks the reporting pass adds (`integrity`, `run`, `eligibility`), which are
provenance rather than results:

```bash
~/.venv-fc/bin/python -c "import json; a=json.load(open('/tmp/agg.json')); b=json.load(open('scale/summary.json')); print(a == {k:v for k,v in b.items() if k not in ('integrity','run','eligibility')})"
# True
```

Per-task evidence for any single result is the record itself —
`scale/records_m4/<instance_id>.json` carries the transformed tree's digest, the
full graded log, the failure analysis and the equivalence tier for every row.

---

## Appendix B — what the run cost

| | |
|---|---|
| tasks | 500, in two segments (107 + 393 after a resume) |
| wall clock | 1.55 h + 7.60 h = **9.15 h** |
| worker-time (Σ per-task elapsed) | 34.45 h at 4 workers |
| mean per task | 248 s |
| images pulled and discarded | 393 logged at 1822.4 GiB; **~2.26 TiB** over all 500 |
| net image bytes retained | **0** |
| registry rate-limit sleep | 5.77 h across 577 waits |
| tasks leaking an image or container | **0 / 500** |
| orphan bytes reclaimed | 0 |
| records written / intact | 500 / 500 |

The M3-based projection said ~8.5 h and ~2.2 TiB. Wall clock and transfer both
landed; what the projection did not model was the registry, which contributed
5.77 hours of sleep and, upstream, defects 21, 22 and 23.

---

Related: `writeup.md` §3.3, §4.1, §4.2, §6.2, §6.5, §7, §8; `CHANGES.md` 10, 12,
13, 16, 17, 18, 19, 21, 22, 23, 24; `scale/SCOPE.md`; `scale/STOPPING_RULE.md`;
`scale/summary.json`; `scale/test_guards_fire.py`.
