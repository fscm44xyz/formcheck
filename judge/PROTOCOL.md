# judge-variance — protocol

Milestone **judge-variance**, branch `judge`. This document is written and
committed **before any model call is made**, and is not edited after results are
seen. If a later step needs a rule this document does not contain, that rule is
added in a new section with its own commit, dated, and the run it governs is
re-run from scratch.

This is a **measurement, not a detector**. Nothing here repairs anything, and
nothing here claims a judge is coupled or uncoupled. It measures one quantity.

---

## 0. The question, and why this step comes first

`formcheck` probes a task's reward by transforming the reference solution in a
behaviour-preserving way and re-running the task's graded tests. The reward is a
test suite: it returns 1.0 or 0.0, and it returns the same value every time it is
run on the same tree. A change in that number is therefore attributable to the
transform and to nothing else.

The open question is whether the same probe can be pointed at a **semantic
judge** — a model scoring a solution against the issue text — in place of the
test suite. A judge differs from a suite in one way that decides whether the
probe is meaningful at all: **the judge's score moves on its own.** Run it twice
on identical input and it may not return the same number.

So the probe's resolution is bounded by the judge's own variance. A transform
that shifts the mean score by less than the judge's spread on identical input is
not detectable, however real it is. **Step 1 measures that spread.** Until it is
measured, no result from a judge-based probe can be read.

---

## 1. Step 1 — the variance floor

No transforms are involved. The judge scores the **unmodified gold patch** of
each task against that task's issue text, N times, on identical input.

### 1.1 Task selection

Fixed before the run, by a rule that uses no result.

The population is the **28 tasks of the 500 that carry at least one `WITNESS`
verdict** in `scale/records_m4/`. The population is restricted to these because
step 2 needs a renamed gold for the same task, and the M4 witness rows are where
those renames are recorded. This restriction is a property of the sample and is
stated wherever the floor is quoted: **the floor is measured on coupled tasks,
not on a random draw from the 500.**

Selection rule: sort the 28 instance ids lexicographically; group by repository
prefix, preserving the order in which repositories first appear; take one task
from each group in turn, in sorted order within the group, until 10 are held.
This maximises repository diversity at fixed size — 9 of the 10 come from
distinct repositories — rather than taking the lexicographic first 10, which
would be 9 tasks from one repository.

The resulting 10, frozen:

```
astropy__astropy-12907
django__django-11179
psf__requests-1766
pydata__xarray-4966
pylint-dev__pylint-4551
pytest-dev__pytest-10356
scikit-learn__scikit-learn-14141
sphinx-doc__sphinx-7454
sympy__sympy-13031
django__django-11433
```

### 1.2 What the judge is shown

Two fields from the SWE-bench Verified row, and nothing else:

- `problem_statement` — the issue text, in full.
- `patch` — the gold patch, in full, as a unified diff.

The judge is **not** shown the task's tests, its `FAIL_TO_PASS` /
`PASS_TO_PASS` lists, the repository, the instance id, or any `formcheck`
output. Showing the tests would let the judge grade against the oracle instead
of against the issue, which is the thing being replaced.

**Truncation:** the issue is capped at 12,000 characters and the patch at
20,000. Measured before the run, the largest of the 10 is 5,278 characters of
issue and 6,862 of patch, so **no truncation occurs on any of the 10**, and the
cap never fires. It is stated because a cap that silently fires is exactly the
defect family this project keeps finding.

### 1.3 The scale

Integer, 0 to 10 inclusive, with the anchors written into the prompt (§1.4).

The scale's granularity **bounds the floor from below**: a judge cannot show a
spread smaller than 0, and the smallest nonzero spread it can show is 1 point,
or 10% of the scale. A coarser scale would compress the floor without making
the judge more stable, which is why a 0–10 integer scale is used rather than a
1–5. This is a measurement artefact of the design and is reported as such.

### 1.4 The prompt

The single source of truth is `judge/prompt_template.txt`, committed alongside
this document. The runner reads that file; the prompt is not duplicated in
Python. Its digest is recorded in every output record.

```
sha256(judge/prompt_template.txt)
  = 798ed4c9f3997ade69b14e2090969dd9caea43c1bad660d9ee612cecbe5761fd
```

The template is substituted by replacing the two literal tokens `{issue}` and
`{patch}` with the corresponding field. `str.format` is **not** used: the
template contains JSON braces in the required-output block, and `str.format`
would misread them. Verbatim:

```
You are grading a proposed code change against the bug report it claims to fix.

Below is an issue reported against a Python project, followed by a patch in
unified diff format that is proposed as the fix.

Score how well the patch resolves the issue, as an integer from 0 to 10:

  0   The patch does not address the issue at all, or makes it worse.
  2   The patch touches relevant code but does not resolve the reported problem.
  5   The patch partially resolves the issue: the main case is handled, but the
      fix is incomplete, or it introduces a plausible regression.
  8   The patch resolves the issue, with a minor shortcoming in completeness or
      robustness.
  10  The patch fully and correctly resolves the issue as reported.

Use the whole scale. Intermediate values (1, 3, 4, 6, 7, 9) are available and
you should use them when the change sits between two anchors.

Judge only whether the change resolves the reported issue. Do not reward or
penalise formatting, naming style, or the absence of tests.

Respond with a single JSON object and nothing else:

{"rationale": "<at most two sentences>", "score": <integer 0-10>}

=== ISSUE ===
{issue}

=== PROPOSED PATCH ===
{patch}
```

**The rationale field is deliberate.** A score-only output would understate the
variance of any judge anyone would actually deploy, because in a judge that
emits reasoning the reasoning drives the number, and sampling the reasoning is
where most of the movement comes from. Suppressing it would measure a floor
that no real judge stands on. The rationale is recorded and never parsed for
anything but the record.

### 1.5 Model, temperature, N

- **Model:** `gpt-5.6-luna`, the model the repository's existing adjudication
  artifact (`repro/f4_adjudicate.py`) already uses. Chosen for continuity with
  that artifact, not because it is the cheapest available.
- **N = 5** calls per task per arm.
- **Two temperature arms**, both run, reported separately:
  - **T = 0** — the narrowest floor a deployment could aim for. Whatever spread
    appears here is the provider's own nondeterminism, not sampling.
  - **T = 1** — the floor a judge sampled in the ordinary way actually stands
    on.

Both arms are run because either alone is unreadable. A T=0 arm at zero spread
would be a lower bound that says nothing about a judge at any nonzero
temperature; a T=1 arm alone could not separate sampling from provider
nondeterminism. Cost is not a reason to drop one: the two arms together are
estimated at roughly $0.04.

If the endpoint **rejects the `temperature` parameter** for this model, that is
recorded verbatim in the output, the arm is reported as "provider default, not
T=0/T=1 as requested", and the requested value is not quietly dropped.

### 1.6 What "the same input" means, exactly

The five calls of an arm send a **byte-identical request payload**: the same
model, the same temperature, the same maximum output tokens, and the same
prompt string. The runner computes `sha256` over the serialised request body
and asserts all five digests within an arm are equal; the digest is written into
the output. If the assertion fails the run aborts rather than reporting a
spread that a payload difference could explain.

Named in full, what **does** differ between the five calls:

1. **Wall-clock time** of the request. Nothing derived from it enters the
   payload — there is no timestamp, date, nonce, or counter in the prompt.
2. **The call index** (1..5). It is used to label the record and is not sent.
3. **The server-assigned response id**, returned not sent.
4. **Position in the request sequence.** Calls are issued sequentially, one
   arm-task at a time, so provider-side batching may differ between them. This
   is not controllable from the client and is part of what the floor measures.

Nothing else. No ordering within the prompt varies, no truncation varies, no
field is shuffled.

### 1.7 Parse failures

The response must contain one JSON object with an integer `score` in 0..10. If
it does not, the call is recorded as a **parse failure** and the raw text is
kept. **It is not retried.** A retry would be a sixth call, which breaks the
"N=5 on identical input" claim and would bias the sample toward responses that
happen to parse. Parse failures are reported as a count alongside the scores,
and a task with any parse failure has its spread computed over the calls that
did parse, with n stated.

### 1.8 What is reported

Per task, per arm: the ordered list of 5 scores, the range (max − min), the
standard deviation, and the parse-failure count.

Aggregate, per arm: the distribution of per-task ranges, the median and maximum
range, the count of tasks with range 0, and the pooled standard deviation.

And the **total cost of the run in USD**, from the token counts the provider
returns, priced by the table in the runner.

### 1.9 Cost ceiling

If the projected cost of a run exceeds **$2**, the run stops before issuing
calls and reports the projection. The projection for step 1 is roughly $0.04
across both arms; the ceiling is not expected to bind, and the check exists so
that a mistake in the estimate stops the run rather than spending through it.

---

## 2. Step 2 — the same 10, gold versus renamed gold

**Not run until step 1 is reported.**

Same 10 tasks, same prompt, same scale, same model, same arms, same N. The
judge scores the gold patch and the **renamed gold** — the same change with one
internal symbol alpha-renamed, the transform that produced the M4 witness. Same
behaviour, different identifiers. The reported quantity is the per-task score
difference, set against the step-1 floor.

The exact construction of the renamed patch is specified in a later section of
this document, committed before step 2 runs. It is not specified now because
step 1 may make step 2 unnecessary, and specifying it now would invite tuning it
once step 1's numbers are visible.

### 2.1 The gate — fixed now, before step 1's numbers exist

Step 2 runs only if **both** hold on the **T = 1** arm:

- median per-task range **≤ 2** points on the 0–10 scale, and
- maximum per-task range **≤ 4** points.

The T=1 arm governs because it is the floor a deployed judge stands on; a T=0
arm that is tighter does not create room that a sampled judge would have.

Rationale for these values, stated before seeing any: the step-2 effect is a
shift in mean score between gold and renamed gold. The renamed gold is
behaviour-preserving, so an uncoupled judge should move ~0 points and any
systematic drop is the signal. At N=5, a shift smaller than the per-task range
is not resolvable. A median range of 2 on a 10-point scale already means the
probe cannot see a coupling effect below roughly a fifth of the scale — which
is a weak instrument, but not a useless one. A median range above that, or a
single task swinging more than 4 points, means the floor is wider than any
coupling effect worth calling a signal.

### 2.1a Amendment — the sufficiency condition the gate did not have

**Added 2026-09-14, after step 1 ran, in its own commit, per this document's
preamble. It tightens the gate; it does not loosen it.** §2.2 forbids amending
the protocol to *produce* a signal. This amendment moves only in the direction
that makes opening harder, so it cannot manufacture one. It is written before
the amended gate is evaluated.

**Disclosed, because it bears on the discipline:** the per-task usable-call
counts from step 1 were already visible when this was written — they were the
first thing step 1 was asked for. What follows is therefore derived from this
document's own text and from a property of the range statistic, and the
threshold is *not* selected by checking which value opens the gate. The
derivation is given in full so that substitution of any other value is visible
as a change of argument, not of taste.

#### The defect

§2.1 as written constrains only the **value** of each per-task range. It says
nothing about how many calls that range was computed over. §1.7 permits a range
to be computed over the calls that parsed, "with n stated" — stated, but not
required to be anything. The two are composable into a gate that opens on
almost no data:

- The range is **monotone non-decreasing in n**. A range over n calls is a
  downward-biased estimate of the range over N, for every n < N.
- A gate of the form `range ≤ threshold` is therefore biased **toward opening**
  whenever n < N, and the bias grows as n falls.
- At **n = 1 the range is 0 identically**, for any judge, at any temperature,
  on any task. Not as a measurement — as an arithmetic property of a
  one-element set.

So the gate's most permissive possible input is produced by its least
informative possible sample. A task on which the judge produced one usable score
and four unusable ones enters the aggregate as `range = 0`, indistinguishable
from a task on which the judge returned the same score five times. §1.8 reports
`n` beside the range, which makes the two *inspectable* but not *separable by
the gate* — the gate reads the range and not the `n`. That is the same shape as
CHANGES.md 19–36: a check that reports a verdict for a reason invisible in its
own output.

§2.1's rationale also presumes the full sample in its own words — "At N=5, a
shift smaller than the per-task range is not resolvable". The quantity it
reasons about is the range over five calls. A range over fewer is a different
quantity, and substituting it silently is what the clauses below forbid.

#### The condition

Both clauses are additional necessary conditions. Neither replaces the value
thresholds in §2.1; all four must hold.

**(a) Per task — a range counts only at full N.** A task's per-task range is
admitted to the aggregate for an arm only if that task produced **n = 5 usable
scores** in that arm, i.e. zero parse failures. A task with n < 5 contributes
**no range**: it is not counted as `range = 0`, not counted at the range of its
survivors, and not dropped silently — it is reported as **`range: unmeasured
(n = k of 5)`**.

*Why n = N and not n ≥ 2.* n ≥ 2 is the bare threshold at which a range stops
being 0 by construction, and it is not enough: at n = 2 the range is still a
strongly downward-biased estimate of the spread over 5, and the gate stays
biased toward opening. n = N is the only value at which the admitted statistic
is the statistic §2.1 reasoned about. It is also the conservative direction,
which is the only direction an after-the-fact amendment may take.

**(b) Per arm — the aggregate must be over the fixed sample.** The median and
maximum of §2.1 are computed only if **at least 8 of the 10 tasks** of §1.1
contribute a counting range in that arm. Below 8, both aggregates are reported
as **`floor: not measured`** and the gate **does not open**, whatever the
surviving ranges say.

*Why 8.* The gate's inputs are a median and a maximum over the 10-task sample
§1.1 froze for repository diversity. A median over a survivor subset is not the
median of that sample, and a maximum over half of it is not a maximum. 8 rather
than 10 leaves room for the parse-failure loss §1.7 already anticipated; 8
rather than 6 keeps both aggregates over a clear majority of the frozen sample,
so that neither is set by one or two tasks. The gate is a conjunction, so (b)
binds independently of (a).

#### What this amendment does not do

It does not make the failures **observable**, and it must not be read as having
repaired them. A task reported `unmeasured (n = k of 5)` still says nothing
about *why* the other 5 − k calls were unusable — whether the judge disagreed,
emitted an unparseable score, or never emitted a visible character at all.
Those are different facts with the same recorded shape, and this document's
reported `truncation` line does not separate them: `truncation` is computed from
the **input** caps of §1.2 only (issue 12,000 / patch 20,000), and reports
`"none -- no cap fired"` without consulting the **output** cap
(`max_output_tokens`) at all. The output cap is a cap this document never named
as one, never bounded, and does not report when it fires.

That gap is recorded as a finding in CHANGES.md, not closed here. Closing it
means changing what the runner records, which changes the run, and no amendment
made after seeing a result may do that to the run that produced it. Any step-1
figure quoted from a run whose records cannot distinguish these cases is quoted
with that limitation attached.

### 2.2 If the gate does not open

The result is reported as: **the formcheck probe does not transfer to a semantic
judge at this budget**, with the measured floor as the evidence. The protocol is
**not** tightened afterwards to produce a signal — not by lowering the
temperature, not by constraining the output format, not by raising N, not by
re-picking tasks, not by coarsening the scale. Any of those would be choosing
the measurement after seeing the result.

Raising N is the only one of those that is legitimate as a *separate, newly
registered* experiment, because it changes the estimator's precision rather than
the quantity being estimated. If it is done, it is registered in a new section
with its own commit and reported as a second measurement, never as a correction
of the first.
