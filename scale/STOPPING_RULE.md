# The M3 decision rule, fixed before M3 runs

M4 is a weekend of compute. This file exists so that whether it is worth spending
is decided by a threshold written down in advance, not by looking at M3's results
and deciding afterwards what they were enough for. Committed before M3 starts;
the commit date is the proof of that ordering.

## The measurement

M3 runs 50 tasks sampled from `scale/eligible.jsonl` with a recorded seed. The
quantity that decides is:

> **W = the number of CONTROLLED tasks with at least one WITNESS row.**

Controlled means the untransformed reference solution scored 1.0 inside the
task's own image. A task whose control failed is excluded from the denominator
and cannot contribute to W — it proves nothing in either direction
(`writeup.md` §4.1).

W counts *tasks*, not rows: a task with three witness rows counts once. The
extrapolation below is to tasks, so the numerator must be tasks too.

## The thresholds

| W over 50 | what M4 is | what the deliverable leads with |
|---|---|---|
| **0 or 1** | optional | the routing map + the reproducibility result |
| **2** | judgment call, CI stated | decided at M3, in writing, with the interval |
| **3 or more** | worth the weekend | the number |

### W = 0 or 1 → M4 becomes optional, and the headline changes

Scaled to the 429 single-file eligible tasks, W ≤ 1 in 50 is a single-digit
projection. A headline of the form "N of 429 rewards are form-coupled" where N is
somewhere between 0 and 20, with an interval spanning most of that range, is not
a finding worth a weekend of compute to tighten — the interval would still span
it afterwards.

In that case the deliverable is **not** "the number". It becomes:

1. **The routing map** — anchor availability per operator, the REFUSED reasons
   and what they establish, the BORDER routing, the loud/silent partition. This
   is a description of where in SWE-bench a reward *could* be form-coupled and
   what it would take to check, which is useful independently of how many
   actually are.
2. **The reproducibility result** — that reference solutions reproduce their own
   scores inside their own images, across repos with different test runners,
   where the July rig managed 2 of 4. That is `writeup.md` §7's finding turned
   from an argument into a measurement.

Report to the requester at M3 and re-decide the headline together. Do not start
M4 on the assumption that more tasks will produce more witnesses; if the rate is
that low, 429 tasks buys a tighter bound on a small number, not a different
answer.

### W ≥ 3 → M4 is worth the weekend, and the number leads

Three or more in 50 projects to roughly 25+ over the eligible set, with an
interval that stays clear of zero. At that point the extrapolation is worth
replacing with a census, and the number is the deliverable.

### W = 2 → judgment, with the interval stated

Report the Wilson 95% interval for 2/50 alongside the recommendation, and say
which way it points and why. The rule here is not a number but a requirement:
**the interval is stated before the recommendation**, so the recommendation can
be argued with.

## What does NOT move the threshold

- **A high REFUSED count.** Refusals are the preconditions working. They bound
  what could be checked, not what was found, and they are already reported
  separately.
- **A high UNVALIDATED count.** That is the oracle rule of §4.2 doing its job on
  tasks with no hand-written contract oracle. It is expected to dominate for
  every operator except `symbol_rename`, and it is why THE NUMBER is
  `symbol_rename`-only.
- **A high NOT_APPLICABLE count.** That is the coverage ceiling, already the
  headline metric of anchor availability.
- **Interesting individual witnesses.** A single compelling case is worth
  reporting and is not worth a weekend. The threshold is about whether a *rate*
  is worth measuring precisely.

## What invalidates the run rather than moving the threshold

If controlled < 40 of 50, the rule does not apply and M3 is not a valid sample:
the finding is about the harness, not about the rate. Fix the controls and re-run
M3 before consulting the table above.

Related: `writeup.md` §4.1, §4.2, §6.5; `CHANGES.md` 2; `scale/aggregate.py`.
