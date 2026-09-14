# judge-variance — result

Milestone **judge-variance**, branch `judge`. Protocol: `judge/PROTOCOL.md`,
written and committed before any model call was made. This document reports
what was observed; it does not amend the protocol, and no rule below was
written after the number it governs.

---

## The question

From `PROTOCOL.md` §0. `formcheck` probes a task's reward by transforming the
reference solution in a behaviour-preserving way and re-running the graded
tests. That reward is a test suite: it returns the same value every time it is
run on the same tree, so a change in it is attributable to the transform and to
nothing else.

**Does the same probe work when the test suite is replaced by a semantic
judge** — a model scoring a patch against the issue text?

A judge differs from a suite in the one way that decides whether the probe is
meaningful: the judge's score moves on its own. The probe's resolution is
therefore bounded by the judge's spread on identical input. A transform that
shifts the mean by less than that spread is undetectable however real it is.
Step 1 was to measure that spread, before any probe result could be read.

## The answer

**Not with this judge, under this protocol.** The measurement never reached the
gate, because a single observation on clean, uncensored data already exceeds it:

> On byte-identical input, five calls, the same gold patch on
> `astropy__astropy-12907` scored **10, 10, 10, 10, 0**.

A per-task range of **10 points on a 0–10 scale** — the entire scale — against a
maximum-range gate of **4**, fixed in §2.1 before any number from this milestone
existed.

That single task is enough to settle the gate's maximum criterion, and it is
worth being precise about why, because the run it sits in is void (below). A
maximum is monotone: admitting more tasks, or recovering data lost elsewhere in
the run, can only raise it. The astropy figure comes from a task that was fully
admitted under §2.1a(a) — n = 5 of 5, zero parse failures — on an arm where the
output cap never fired on any of its 50 calls. No data that the void withheld
could bring that maximum back under 4. The gate is not *evaluated* here; the
observation that would fail it does not depend on the part of the run that is
unusable.

The five calls are identical by assertion, not by assumption. §1.6 requires the
runner to `sha256` the serialised request body and abort if the five digests
within an arm differ; all five astropy calls carry
`request_sha256 = 08a33a59514e63ea…`. What differs between them is wall-clock
time, position in the request sequence, and the server-assigned response id.
Nothing else: no timestamp, nonce, counter, or ordering enters the payload.

## The mechanism — the interesting part

The spread is not sampling jitter around a stable read of the patch. Four of the
five calls read the diff one way and one read it another way, and the odd one
out is not a hedge or a near-miss — it is a confident, internally coherent
extreme built on a different understanding of what the patch does.

The four that scored 10, in the words of the first of them:

> "The patch preserves the recursively computed separability matrix for a nested
> right-hand CompoundModel instead of replacing its block with all ones. This
> directly fixes the reported nested `&` case while retaining the existing
> behavior for non-compound models."

The fifth call, scoring 0, on the same bytes:

> "The patch replaces a numeric block assignment with the `right` model object
> itself, which is not a separability matrix and will generally raise a
> type/conversion error even for the basic `Linear1D & Linear1D` case. It
> therefore does not fix nested compound separability and likely breaks existing
> compound-model handling."

These are not two gradings of one reading. They are two readings: whether the
right-hand side of the changed assignment is an already-computed matrix or a
model object. Both cannot be true of the same diff. Given the wrong reading, 0
is the *correct* score under the prompt's own anchors — "does not address the
issue at all, or makes it worse" — which is what makes the failure mode
dangerous rather than noisy. The judge is not uncertain. It is confidently
grading a patch it has misread, and its rationale is coherent enough that the
number looks earned.

The count across the whole milestone on this task: **nine of ten calls** read
this diff the first way and returned 10; one did not. All ten are usable — this
is the one task where both arms are clean, n = 5 of 5 in each, zero cap hits and
zero parse failures — and since the two arms are one condition run twice (below),
ten is the right denominator. A judge that is wrong 10% of the time in a way that
costs the full scale cannot resolve a transform effect of a few points, and
averaging does not rescue it — the outlier moves the arm's mean by 2 points on
its own, which is the size of the effect the probe is looking for.

The other nine tasks on the same arm, for context, and **not** offered as the
floor §2.1 would have been evaluated on (the run is void; see below):

| task | scores | range |
|---|---|---|
| `astropy__astropy-12907` | 10, 10, 10, 10, 0 | **10** |
| `sympy__sympy-13031` | 5, 2, 2, 2, 3 | 3 |
| `django__django-11433` | 10, 10, 10, 10, 8 | 2 |
| `pydata__xarray-4966` | 10, 8, 9, 10, 8 | 2 |
| `pytest-dev__pytest-10356` | 9, 8, 8, 10, 8 | 2 |
| `django__django-11179` | 10, 10, 10, 10, 10 | 0 |
| `psf__requests-1766` | 10, 10, 10, 10, 10 | 0 |
| `pylint-dev__pylint-4551` | 8, 8, 8, 8, 8 | 0 |
| `scikit-learn__scikit-learn-14141` | 10, 10, 10, 10, 10 | 0 |
| `sphinx-doc__sphinx-7454` | 10, 10, 10, 10, 10 | 0 |

Five tasks at range 0 is the shape that makes this hard to catch: the judge
looks stable on half the sample, and the instability is concentrated in
occasional total misreads rather than spread evenly as jitter. A floor reported
as a median would have said 1 point and been badly misleading.

## Temperature: both arms ran at the provider default

**An argument was made here and it did not survive contact with the artifact.**
It was mine, and it is recorded the way this repository records the others,
because a milestone document that quietly drops a claim it once rested on is
worth less than one that says where it was wrong.

**What was claimed.** That the finding was strengthened by sitting on the T = 0
arm: §1.5 calls T = 0 "the narrowest floor a deployment could aim for", so a
judge that spreads across the whole scale *there* spreads worse anywhere a
deployment would actually run it. Failing in the best case, therefore failing.

**Why it is wrong.** There is no T = 0 arm. The endpoint rejects the parameter
for this model:

    Error code: 400 - Unsupported parameter: 'temperature' is not supported
    with this model.

recorded verbatim in `temperature_rejected`. §1.5 anticipated this and specified
the handling — record the error, report the arm as "provider default, not
T=0/T=1 as requested", never drop the requested value quietly — and the runner
did exactly that. **All 50 records of the arm keyed `"0.0"` carry the note**

> `temperature rejected by the endpoint; sent at the provider default. This arm
> is NOT T=0.0.`

The failure was not in the apparatus, which behaved as written and said so in
every record. It was in reading the arm by its key.

**The argument is withdrawn, not weakened.** No claim about the best case, the
narrowest floor, the optimistic bound, or any other privileged status for this
arm appears anywhere in this document. Nor is a softer substitute offered — the
observation is not given standing by §2.1's "the T = 1 arm governs" either,
since that clause reasons about a temperature distinction this run does not
contain. Every such move is unavailable for the same reason, and swapping one
for another would be the same error in a quieter voice.

### What the finding rests on instead

Four facts, none of them about temperature:

1. **50 calls with the instrument clean.** On the arm quoted here, the output
   cap fired **zero times in 50 calls** and every call parsed. The one cap hit
   and both parse failures in the milestone are in the other arm.
2. **Byte-identical input, by assertion.** §1.6 requires the runner to `sha256`
   the serialised request body and abort if the five digests within an arm
   differ. All five astropy calls carry
   `request_sha256 = 08a33a59514e63ea…`.
3. **Full coverage.** All 10 tasks contributed n = 5 of 5 usable scores on this
   arm — `counting_tasks: 10`, `parse_failures: 0`. Nothing was lost and no task
   entered on a partial sample, so §2.1a(a) admits every one of them.
4. **0 and 10 on the same gold patch, on the same task.**

That is the whole basis, and it holds whatever the temperature was.

### The two arms are one condition run twice

The arm keyed `"0.0"` sent no `temperature` field. The arm keyed `"1.0"` sent
`temperature: 1.0` and was accepted — the ordinary shape of an endpoint that
permits only its default value. **On that reading the provider default is 1.0
and the two arms are the same sampling condition, run twice.** It is an
inference from the accept/reject pattern, not something the provider stated, and
it is marked as one.

Two consequences, both worth stating plainly:

**§1.5's reason for running two arms is not served.** It required both because
"either alone is unreadable" — a T = 0 arm alone says nothing about a sampled
judge, a T = 1 arm alone cannot separate sampling from provider
nondeterminism. Neither separation is available from a design that ran one
condition twice. The two-arm structure survives in the artifact's keys and
nowhere in its data.

**N is 10 calls per task at one setting, not two settings of 5.** That is the
honest description of the sample. It is not used here to pool the per-task table
into ten-call ranges, because the second arm is censored — one call at the cap,
two parse failures — and pooling would pull censored draws into a figure the
void already excludes. The one place the pooled count is used is the astropy
task specifically, where **both** arms are clean: n = 5 of 5 usable in each,
zero cap hits, zero parse failures. Ten calls saw that diff, nine returned 10
and one returned 0. The two sets of five are byte-identical *within* each set;
across the sets the payloads differ by the presence of the `temperature` field,
so they are ten calls at one setting, not ten byte-identical calls.

### A note for anyone reading the artifact rather than this file

The top-level `arms: [0.0, 1.0]` and the `aggregate` / `per_task` keys `"0.0"`
and `"1.0"` name a parameter that neither arm is known to have run at and that
one of them demonstrably did not. The disclaiming note is per-record, in
`records`, where a reader working from the summary will never meet it. That is
the CHANGES 19–36 family — an artifact labelled for a condition it did not hold,
with the evidence present but not where the verdict is read — and it is the
proximate cause of the withdrawn argument above. It is flagged here rather than
fixed, because fixing it means editing the run that produced it.

## The void, stated separately

**Step 1b is VOID under §1.11.3.** This is stated on its own, and it is not
used as evidence for anything above.

§1.11.3 registered the rule before the run: every record carries
`output_cap_hit`, and **step 1b is void if `output_cap_hits > 0` — even one**,
because a single call at the cap means the cap is still shaping the output
distribution and any floor computed beside it is computed on censored draws.

    calls              : 100
    output cap         : 4000
    output_cap_hits    : 1      -> VOID (§1.11.3)
    parse rate         : 0.98   (min 0.95) -> the §1.11.4 stopping rule did not fire

One call hit it: `sympy__sympy-13031`, call 3, `output_tokens` exactly 4000,
empty response. It is in the arm that sent `temperature: 1.0`, as are both of
the run's two parse failures.

Consequences, applied strictly:

- **No floor is reported from step 1b.** Not a median, not a maximum, not a
  pooled standard deviation. §2.1 and §2.1a were not evaluated;
  `step2_gate.evaluated` is `false` in the artifact.
- **The numbers from the arm that sent `temperature: 1.0` are not quoted here**
  — not its ranges, not its aggregates. That arm carried the cap hit and both
  parse failures; it is the contaminated one, and nothing in this document rests
  on it.
- **Step 2 did not run.**

What is quoted above is a single uncensored observation on an admitted task, on
the arm where the cap fired zero times in 50 calls and every call parsed. The
distinction being drawn is the one §1.10 draws: an instrument parameter
determined part of this run's output, so that part cannot be read as a fact
about the judge — but the astropy calls are not that part, and a maximum they
already exceed cannot be brought back under the gate by data that is missing
elsewhere.

Step 1b did **not** fail on parse rate. At 0.98 it cleared §1.11.4's 95%
threshold, so the "no third configuration" clause did not fire. The void is on
the cap audit, on one call in a hundred.

## Step 1 was void too, on the output cap

Recorded in `PROTOCOL.md` §1.10 and CHANGES.md 37. Step 1 ran with
`max_output_tokens = 400` against a reasoning model that spends output tokens
before emitting visible text. 85 of 100 calls were parse failures; **82 returned
zero visible characters**; 84 of the 85 sat exactly at 400 while all 15 parsed
calls came in strictly under it. The cap, not the judge, determined the output.

The reporting defect that hid it: the artifact printed
`"truncation": "none -- no cap fired"`, computed from the §1.2 *input* caps
alone, while an output cap the document never named as a cap fired on 84 of 100
calls.

And the gate defect found in the same reading: §2.1 constrained the *value* of
each per-task range and said nothing about the sample size behind it. `opens:
true` had been computed off three tasks, one of them at n = 1 — where the range
is 0 by construction, for any judge, on any task. The gate's most permissive
input was its least informative sample.

**The rule step 1 produced**, from CHANGES.md 37:

> *A run whose output was determined by an instrument parameter rather than by
> its subject is void, and a void run is never reported as a measurement of its
> subject — including when the null it appears to support is the conservative or
> self-critical one.*

That rule is why step 1's 15 scores — all 10 — appear nowhere as evidence of a
stable judge, and it is the same rule being applied to step 1b's floor above.
Its companion:

> *A check on the value of a statistic states the minimum sample that statistic
> is admitted on, in the same clause, or it is a check on its own sample size.*

which became §2.1a: a range is admitted only at n = 5, and an arm's aggregates
are computed only if at least 8 of the 10 tasks contribute one. Both conditions
were carried into step 1b unchanged and are visible in its artifact — two tasks
in the contaminated arm are reported `unmeasured (n = 4 of 5)` rather than
entering the aggregate at the range of their survivors.

## What this does NOT establish

Stated at the same volume as the result, because the result is a single
observation and its scope is narrow.

- **One judge.** `gpt-5.6-luna`, chosen in §1.5 for continuity with
  `repro/f4_adjudicate.py`, not because it is representative of anything. A
  different model may be steadier, and nothing here predicts which.
- **One prompt.** A single template, `sha256 798ed4c9…`, unchanged across the
  milestone. The rationale field is required by §1.4, and §1.4's own reasoning
  is that sampling the reasoning is where most of the movement comes from — so
  this design is deliberately measuring a judge that reasons aloud.
- **One scale.** Integer 0–10 with the anchors in §1.3. §1.3 already notes the
  scale bounds the floor from below: the smallest nonzero spread showable is 1
  point, or 10% of the scale.
- **Ten tasks**, and **all of them coupled tasks** — drawn from the 28 witness
  tasks, which as `step1b_result.json` records is "not a random draw from the
  500". This says nothing about the judge's behaviour on the wider set.
- **The judge could not be run at a lower temperature.** The endpoint rejects
  the parameter for this model, so every call in this milestone ran at the
  provider default and no narrower setting was reachable. Whether a steadier
  configuration of this judge exists is therefore **unmeasured — not ruled
  out.** Nothing here licenses the claim that lowering the temperature would not
  help; it licenses only the claim that it was not tried, because it could not
  be.
- **No rubric with anchored per-criterion scoring was tried.** The observed
  failure is a misread of a diff, not an inability to map a correct read onto a
  number, so a rubric that forces the judge to state what the patch changes
  before scoring it is a plausible way to get a steadier read. That is a
  conjecture, and it is untested here.

**This is not a claim about semantic judges in general.** It is not even a
measured floor for this judge: the run that would have produced one is void. It
is one observation, on one task, that a judge of this kind can return 0 and 10
on the same bytes — which is enough to stop the `formcheck` probe from being
pointed at *this* judge under *this* protocol, and is not enough to say anything
about the next one.

## Where this stops

Here, deliberately.

A step 1c, a second judge, and a rubric variant are each **new measurements**.
§1.10's correct-next-move column and §2.2's separate-registration clause both
point the same way: they require their own registered section, written before
they run, in their own commit — not an appendix to this document written after
its numbers exist. None of them is performed here, and this document does not
pre-commit to any of them.

---

## Provenance

    milestone        judge-variance
    step             1b
    status           VOID (PROTOCOL.md 1.11.3, output_cap_hits = 1)
    supersedes       nothing -- step 1 is void (1.10); 1b is a new measurement
    model            gpt-5.6-luna (provider: openai)
    tasks            10, from 28 witness tasks -- coupled, not a random draw
    N                5 per task per arm; 10 per task at one setting (see above)
    arms             2 by key, one sampling condition -- temperature rejected
                     by the endpoint, both arms at the provider default
    calls            100   usable 98   parse rate 0.98
    output cap       4000  hits 1
    input caps       did not fire
    prompt sha256    798ed4c9f3997ade69b14e2090969dd9caea43c1bad660d9ee612cecbe5761fd
    cost             $0.16
    artifact         judge/step1b_result.json (retained unedited)
