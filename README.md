# formcheck — does a task's reward reject a correct solution written differently?

**Across all 500 tasks of SWE-bench Verified, 22.2% of controlled tasks — 28 of
126, Wilson 95% [15.8%, 30.2%] — reject a behaviour-preserving rename of an
internal symbol the gold patch touches.** In 15 of those 28 *every* graded test
fails, and the median coupled task loses 100% of its suite: renaming a
module-level symbol stops the test module importing, so the suite does not
partially fail — it does not run, and the reward carries no information about
whether the solution works.

That figure measures **reward damage** — how much graded signal a rename
destroys. It is not a measurement of how many of a suite's tests actually
reference the symbol, and it should not be read as one; at module scope a single
import line can take down tests that never mention the name. Measured once, on
`astropy-12907`: 14 of its 15 failures were attributable to one import line, and
the reward is 0.0 either way. n = 1 for the mechanism, unmeasured on the other 14
— see [REPORT.md §3a](REPORT.md#3-what-changes-for-a-customer).

Full report: **[REPORT.md](REPORT.md)**.

## What formcheck does

It transforms the reference solution in ways that preserve behaviour, such as an
alpha-rename of a symbol, and re-runs the task's own graded tests. Each transform
is offered an **anchor**, the particular symbol it proposes to change, and only
symbols the gold patch actually touches are offered; a transform that still
satisfies the issue's contract and still scores 0.0 is a **witness** that the
reward is coupled to the incidental form of the gold patch. Every rate is scoped
to **controlled** tasks, those whose untransformed reference solution reproduces
its own 1.0 inside its own image, because a task that cannot reproduce its own
gold proves nothing in either direction.

## How it was measured

All 500 tasks of SWE-bench Verified, across 12 repositories and 4 test runners,
each inside its own epoch-pinned image. The check runs on verifiers' own
`DockerRuntime` through `validate._run_check`, which is the same call by which a
Harbor task reaches its container.

494 of the 500 reference solutions reproduced their own score before any
transform ran; the 6 that did not are excluded from every rate and named in the
report. Every witness is attributed by failure text, meaning a failure block that
names the renamed symbol: `p2p_unattributed = 0`, so no witness rests on a
failure the attribution could not explain. No model produces a witness, and the
number involves no inference at any point.

The run took 9.15 hours and pulled 2.26 TiB of images, discarding all of them and
leaking none.

## What it does not show

**One channel only.** The rate measures coupling to a symbol's *identity*.
Coupling to structure, ordering or decomposition is unprobed, because the
operators that would reach those found anchors on 0–3.5% of the corpus, and the
direction is unknown. An earlier claim that 22.2% is a floor has been withdrawn:
tests import by name, so a restructuring that preserves entry points may break
fewer tests rather than more.

**The encounter rate is unmeasured.** How often a real policy is actually
penalised depends on how often its correct solution differs in form from the
gold. Measuring that needs rollouts from a model, and this project uses none.

**`on_prime_hub` is unresolved on 500 of 500.** Unresolved, not negative.

## The result that survives the number

Nine defects found in this work share one shape: **a check that reports a verdict
for a reason invisible in its own output**. That is the exact failure `formcheck`
was built to detect in other people's graders, appearing repeatedly in
`formcheck` itself.
Every one was found by inspecting the machinery, never by a suspicious number,
because none of them produced a suspicious number: one had a parser that
understood a single test runner and silently converted four real witnesses into
"invalid transform", which would have reported `W = 0` over 50 tasks with clean
controls, zero errors and a 46-minute run. Two others are worth the read on their
own: two individually correct guards that cancelled at their seam and disabled a
liveness check without emitting anything, and a disk guard whose first firing in
production was a false positive.

→ **[REPORT.md §7, The defect family](REPORT.md#7-the-defect-family)**

## Where to look

| | |
|---|---|
| [REPORT.md §1](REPORT.md#1-the-number) | the number, both denominators, why one operator |
| [REPORT.md §3](REPORT.md#3-what-changes-for-a-customer) | blast radius, encounter rate, what the number is |
| [REPORT.md §7](REPORT.md#7-the-defect-family) | nine defects, one shape |
| [writeup.md](writeup.md) | method, the transform family, retractions |
| [judge_rubric.md](judge_rubric.md) | the contract-vs-form rubric for refused cases |

## Reproduce

```bash
python3.12 -m venv ~/.venv-fc
~/.venv-fc/bin/pip install "swebench==4.0.3" "datasets==5.0.1" "docker==7.2.0"

# recompute every number, from records on disk -- no containers
~/.venv-fc/bin/python scale/aggregate.py --results scale/records_m4 -o /tmp/agg.json
~/.venv-fc/bin/python scale/test_guards_fire.py     # 17/17 -- every guard fires

# one task, ~2 min, needs docker
~/.venv-fc/bin/python scale/run.py --instance-id django__django-13195
```

Full setup, pinned versions and the 500-task command:
[REPORT.md Appendix A](REPORT.md#appendix-a--reproduce-it).
