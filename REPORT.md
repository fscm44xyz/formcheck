# formcheck at scale — M0 to M4

`formcheck` asks the question a gold check cannot: does a task's reward reject a
*correct* solution written differently? It answers by transforming the reference
solution in ways that preserve behaviour and re-running the graded tests. A
transform that keeps the task's stated contract and still scores 0.0 is a witness
that the reward is coupled to the incidental form of the gold patch.

This report covers the scale work: running that check inside each task's own
epoch-pinned image, on verifiers' own runtime, across all 500 tasks of SWE-bench
Verified.

---

## 1. The number

> **22.2% of controlled SWE-bench Verified tasks — 28 of 126, Wilson 95%
> [15.8%, 30.2%] — reject a behaviour-preserving rename of an internal symbol
> the gold patch touches.**

The scope belongs in the sentence, so it is written there: `symbol_rename` only,
over tasks whose reference solution reproduced its own score in its own image,
counting a task once however many of its rows are witnesses.

Denominator: tasks with at least one judged `symbol_rename` case, among the 494
tasks whose control passed. 126 of the 494 have one.

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
"M4 is worth the weekend, and the number leads"; it was committed in `0d6e786`
at 14:39 on 2026-09-08, before M3's ids were frozen in `664a3ab` at 16:25 and
before M3's results existed in `18d22b5` at 18:24. M3 returned W = 4, with the
rule's validity precondition of at least 40 of 50 controlled met at 50/50.

The 34 witness rows share one observable: `symbol identity (module-level name)`.
By repo: django 18, sphinx 4, pylint 3, pytest 3, scikit-learn 2, astropy 1,
requests 1, xarray 1, sympy 1.

---

## 2. What the number rests on

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

## 3. The ceiling

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

## 4. Routing the border, and what a judge would cost

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

## 5. The defect family

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
named. §3 above is that mechanism reporting 75 rows on itself.

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

## 6. Reproducibility, executed rather than argued

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

## 7. What this does not show

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
- **Nothing about severity.** A witness shows a reward rejects a
  behaviour-preserving rewrite. It does not show how often a real model would
  write that rewrite, and this work does not measure that.

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

## Appendix — what the run cost

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
