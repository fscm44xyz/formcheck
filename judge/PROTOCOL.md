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

## 1.10 Step 1 is VOID on a harness defect, not closed on a measurement

**Added 2026-09-14, in its own commit, after step 1 ran.**

Step 1 produced 15 usable scores of 100 calls. 82 responses contained zero
visible characters; 84 of the 85 parse failures had `output_tokens` exactly
equal to `max_output_tokens = 400`, while all 15 parsed calls came in strictly
under it. `gpt-5.6-luna` is a reasoning model — the same endpoint rejected the
`temperature` parameter outright (§1.5) — and it spends output tokens on
reasoning before emitting visible text. At 400 the budget was exhausted before
the response began.

**The cap, not the judge, determined the output.** Step 1 therefore did not
measure the judge's variance floor. It measured an instrument parameter of this
protocol's own runner.

### The distinction this section exists to fix

These two outcomes are not interchangeable, and §2.2 applies to exactly one of
them:

| | *Closed on a measurement* | *Void on a harness defect* |
|---|---|---|
| the quantity was | measured; threshold not met | never measured |
| what determined the output | the subject | an instrument parameter |
| reportable as a result about the judge | yes | **no** |
| §2.2 (no retuning) | **binds** | does not bind — there is no result to protect |
| correct next move | report it; do not retune | fix the instrument, re-register |

**§2.2 does not license reporting a void run as a null result.** Its purpose is
to stop this protocol from being loosened until it yields a signal. Invoking it
to certify a no-signal outcome that the apparatus produced inverts it: the
clause guarding against a manufactured positive would be manufacturing a
negative. The direction of the error is not a defence. *"We observed no
variance" is as much a claim about the judge as "we observed variance," and both
require an instrument that could have observed it.* Step 1 could not have: a
judge returning five different scores per task would have produced the same 82
empty strings.

### What step 1 may and may not be quoted for

- **May:** the defect itself — the cap, the token distribution, the 85% parse
  rate, and the §2.1 gate reporting `opens: true` off three tasks, one at n = 1.
  Those are facts about this repository's apparatus and are recorded in
  CHANGES.md 37.
- **May not:** any statement about judge variance, any variance floor, any claim
  that the `formcheck` probe does or does not transfer to a semantic judge, and
  any answer to §0. **No judge variance was observed, so none is reported.** The
  15 scores are all 10, on a censored sample of 3 tasks of 10; that is not a
  distribution and no spread is computed from it anywhere.

`judge/step1_result.json` is retained unedited, and its `step2_gate.opens: true`
stands in the file as the defect's evidence. Nothing reads it as a verdict.

---

## 1.11 Step 1b — the registered re-measurement, cap set from the observed distribution

**Registered 2026-09-14 in its own commit, before any step 1b call is made.**
This is a **new measurement**, not a re-run and not a correction of step 1.
Step 1 is void (§1.10); there is no step 1 number for this to replace, and
step 1b's result is never reported as an amendment to one.

### 1.11.1 What is frozen, and what changes

Frozen, carried over **unchanged and not re-derived**:

- **The 10 tasks of §1.1.** Not re-picked. Re-picking after seeing which tasks
  survived would select on the outcome, and 7 of the 10 produced nothing, so a
  re-pick would be the most consequential possible tuning.
- **The prompt**, by digest: `sha256(judge/prompt_template.txt)` must equal
  `798ed4c9f3997ade69b14e2090969dd9caea43c1bad660d9ee612cecbe5761fd`. The runner
  asserts this and aborts on mismatch.
- **The scale** (§1.3), **the parse rule** (§1.7 — still never retried), **the
  two arms and N = 5** (§1.5), the **input caps** (§1.2), the **cost ceiling**
  (§1.9), and **§2.1 + §2.1a in full**, including the n = 5 per-task and 8-of-10
  per-arm sufficiency conditions.

**The only change to the sampled quantity is the output cap.** One further
change is made to *reporting only*, declared here rather than made quietly
(§1.11.3); it does not alter what is sent or sampled.

### 1.11.2 The cap, and where the number comes from

`MAX_OUTPUT_TOKENS = 4000`.

The derivation, stated before the run:

1. Step 1's 15 parsed calls consumed **115 to 351** output tokens in total
   (the Responses API counts reasoning and visible tokens together, so these are
   totals, not visible-text lengths). Observed maximum of a *successful* call:
   **351**.
2. 84 calls were **censored at 400**. Censoring gives a **lower bound only**:
   those calls needed more than 400 and the data cannot say how much more. The
   tail of the requirement distribution is unobserved.
3. So the observed distribution cannot be used to pick a *tight* cap — only to
   establish that a tight one is wrong. 351 is the maximum of the uncensored
   part, which is precisely the part that was cheap; setting the cap near it
   would re-create the defect while looking data-driven.
4. **4000** is 10× the cap that failed and ≈11× the largest successful step-1
   call. It is chosen to make the cap **not plausibly binding**, not to fit the
   observed points.
5. Cost: worst case is all 100 calls running to the cap — 400,000 output tokens
   at the §1.9 table's $1.20/1M for `gpt-5.6-luna`, ≈ **$0.48**, plus ≈$0.02 of
   input. That is under the $2 ceiling by roughly 4×, so the ceiling does not
   bind and cost is not a reason to choose a tighter cap.

### 1.11.3 The cap is verified non-binding, not assumed to be

Step 1's defect was not only that the cap was too low; it was that **the run
could not report that the cap had fired.** `truncation` was computed from the
§1.2 input caps alone and printed `"none -- no cap fired"` while the output cap
fired on 84 of 100 calls.

The reporting change, registered here: every step-1b record carries
`output_cap_hit` (`output_tokens >= max_output_tokens`), and the summary reports
`output_cap_hits` as a count over all calls, separately from the input-cap
`input_truncation` field. This changes no request payload and no sampled value.

**Step 1b is VOID, by this section and on the same grounds as §1.10, if
`output_cap_hits > 0`** — even one. A single call at the cap means the cap is
still shaping the output distribution, and a floor computed alongside it is
computed on censored draws.

### 1.11.4 The stopping rule — fixed now, before step 1b runs

Registered so that a third configuration attempt is not available as a choice
once step 1b's numbers exist:

- **Parse rate is reported before any spread, range, median or gate verdict is
  computed or read.** Ordering matters: a parse rate inspected after a favourable
  floor is a parse rate nobody would have acted on.
- **If step 1b's parse rate is below 95%**, step 1b is reported as **a second
  failure to instrument the judge**, and **no third configuration is attempted
  under this protocol.** Not a higher cap, not a different model, not a
  constrained output format, not a re-pick, not a raised N. Two attempts is the
  budget; a third would be tuning the apparatus until the subject appears, and
  the honest report at that point is that this repository could not instrument
  this judge — a statement about the apparatus, which is all a failed
  instrumentation ever licenses (§1.10).
- **If the parse rate is at or above 95%**, the floor is computed and §2.1 +
  §2.1a are evaluated on it, and *that* result — opening or closing — is a
  measurement and falls under §2.2.

95% is set here, before the run, as the rate at which the surviving sample can
satisfy §2.1a's 8-of-10-at-n=5 condition with room to spare; it is not adjusted
afterwards.

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
