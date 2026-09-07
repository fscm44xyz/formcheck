# rewardpatch — a measured map of reward-signal fragility, and a method for repairing only the part you can verify

*Offline analysis of implementation-coupled tests in uncurated RL environments,
built on Prime Intellect's `verifiers` stack. This is a research writeup, not a
product pitch. Every number is labeled by how it was obtained; where the data is
too thin to quantify, it says so.*

---

## Summary

Prime has stated that tasks mined from merged PRs inherit tests that assert
implementation details rather than behavior — an exact error string, a private
helper, a precise return shape — so that a correct-but-different solution fails
them and the reward becomes a false negative. This is a real and large problem in
uncurated corpora: **we measured an implementation-coupling signal in 35% of
graded tasks in a Scale-SWE sample, versus ~2–4% in curated SWE-bench Verified —
roughly an order of magnitude more.**

The obvious response — automatically repair the coupled tests — is worse than
doing nothing, for a reason the raw prevalence hides and which is the central
finding of this work:

> **The dominant coupling types are the least repairable, and much of what looks
> repairable is contract in disguise.** Of coupled tasks, 69% mock an internal
> symbol and 58% assert exact call arguments; in both, the intended behavior is
> observable *only through the mock*, so there is no independent witness to repair
> against safely. The safely-repairable fraction — where the issue states an
> observable behavior and the test merely pins an incidental error message — lives
> in the *minority* message-coupling type (22% of coupled tasks). And a large part
> of even that turns out to be contract the issue specifies: an exact class or
> hook name that consumers depend on. A naive repairer that chases the volume
> (mock/call) would loosen tests it cannot witness and break contract it should
> never touch.

So the deliverable is not a coverage-maximizing repair tool. It is three things:

1. **A measured map** of where a corpus's reward signal is fragile and of what kind.
2. **A demonstrated method** for repairing the high-confidence fraction with
   regression evidence and without loosening a test on faith — shown end-to-end,
   through four validation gates, on one real task.
3. **An honest routing** of everything else to semantic judgment — which tells
   Prime where its Agentic Judging budget is needed and where it is not — now a
   measurable question against a shipped env rather than an announced direction.

The relationship to Agentic Judging (shipped 2026-08-07, verifiers 0.3.0 /
prime-rl 0.8.0) is a division of labour, not an overlap. `AgenticJudgeEnv`
replaces the deterministic reward per rollout, on the judge's own execution, with
no calibration measured (`env.py:261-268`, `330-333`, `92-96`, `320`; §1). This
work is an **offline admission filter**: it runs once per task, before training,
and decides mechanically whether a task's reward can reject a correct solution at
all. One is a per-rollout substitution whose error rate is currently unknown; the
other is a per-task check whose output is an executable witness. The cheaper
filter reduces how often the expensive judge has to be right.

---

## 1. The problem, in Prime's terms

Per Prime's July 2026 post on scaling agentic RL to 365k+ tasks: tasks mined from
merged PRs inherit that PR's tests, and those tests "often assert implementation
details rather than behavior." An agent that fixes the underlying issue in a
different but equally correct way still fails them, and the reward reads as a
false negative. Gold-patch validation is blind to this by construction — the
original patch passes its own tests. At RL scale these near-misses are noise in
the training signal. Prime's answer to this shipped on **2026-08-07** (verifiers
0.3.0 / prime-rl 0.8.0): **Agentic Judging** — `AgenticJudgeEnv`, at
`verifiers/v1/envs/agentic_judge/env.py`. It is worth being precise about what it
does, because the shipped default is stronger than "a judge that can overrule a
test". Its scoring config defaults to `task_weight = 0.0`, `judge_weight = 1.0`
(`env.py:261-268`), and `finalize` applies that weight to the taskset's own
rewards (`env.py:330-333`) — so by default the deterministic tests are multiplied
by zero and **the judge's verdict is the entire reward**. The judge is told
explicitly that "recorded scores can be wrong and references can be narrower than
the task… Your verdict is what YOU verified by execution" (`env.py:92-96`), and
it is not trained (`agents.judge.trainable = False`, `env.py:320`), so whatever
bias it has is static and reaches every rollout. The integrity of the verdict
*channel* is defended — `setup` removes any pre-seeded verdict file and names the
planted-symlink attack (`env.py:185-193`) — but there is no calibration, no
ground truth, and no adjudication anywhere against a verdict that is simply
**wrong**: nothing distinguishes a judge that correctly rescues a
correct-but-different solution from one that rescues incorrect code, or that
overrules an assertion the issue actually specifies.

The problem is not ours alone to assert. **DeepSWE** (arXiv 2607.07946) measures
**19–28% verifier false negatives on SWE-Bench Pro** — an independent estimate,
on a different corpus and by a different method, of the same failure this work
addresses. We cite it as corroboration of the phenomenon's scale, not as a
substitute for our own numbers: it measures false negatives of a verifier, while
§2 measures implementation-coupling signals in graded tests, and the two are
related but not the same quantity.

It is also worth recording what Prime has *already* closed, because it bounds
what is left to build. Verdict-integrity and grading isolation are done:
`IsolatedVerifierEnv` (`verifiers/v1/envs/isolated_verifier/env.py`) reruns a
task's ordinary metrics and rewards in a **fresh** runtime after the solver's box
is destroyed, so a solver can no longer tamper with its own grading. That closes
the "grade in a box the agent controlled" gap as a shipped feature. It does not
touch the gap this work is about: a test that rejects a correct solution rejects
it just as reliably in a pristine container.

Detecting a false negative leaves you where you started: knowing the signal is
noisy. This work asks the next question — *how much of it can you safely repair
offline, once, before training, and how do you know which part?*

## 2. What we measured — and the shape that matters

### 2.1 Prevalence (measured)

We compared curated and uncurated corpora using an offline SWE-bench-format
grader: upstream `swebench` 4.0.3 (`get_eval_tests_report` /
`get_resolution_status`) called the way `verifiers` called it at tag **v0.2.1**
(2026-07-20), when this work was done. It is a pure function of the pytest log —
so it runs offline, CPU-only, no Docker. That `verifiers` path has since been
deleted (see the provenance note at the end of this document); the grading
semantics it wrapped are upstream `swebench`'s and are unchanged.

| corpus | coupling in graded tests | how measured |
|---|---|---|
| SWE-bench Verified (curated) | ~2% message-coupled; ~3.6% coupled-to-an-internal-in-a-graded-test | full scan of all 500 tasks |
| Scale-SWE (uncurated) | **35%** (316 of 907 graded tasks with ≥1 coupling signal) | 972-row prefix sample |

**Measured caveat, stated plainly:** the Scale-SWE figure is a broad signal set
(mock / call / message / private-symbol); the Verified figures are narrower
slices. The metrics are not identical, so read this as *roughly an order of
magnitude*, ~10–17×, not a precise multiple. The Scale-SWE sample is an
HTTP-Range prefix of a 937 MB JSONL, Python-only, and repo-clustered (one repo
dominates) — it is **not** a uniform random sample. The direction (uncurated ≫
curated) is robust; the exact rate is a sample estimate.

The low Verified rate is expected and instructive: Verified is the hand-curated
subset, filtered precisely to remove unfair tests. It is the wrong place to study
this problem. The uncurated corpora are where the reward signal actually frays.

### 2.2 What kind of coupling (measured), and where it lands (qualitative)

Among the 316 coupled tasks, the distribution of coupling signals is **measured**
(rows can carry more than one signal):

| coupling signal | rows | share of coupled |
|---|---|---|
| mock an internal symbol | 218 | 69% |
| exact `call_args` / `assert_called` | 182 | 58% |
| exact message `==` | 68 | 22% |
| private-symbol reference | 46 | 15% |
| `match=` / `assertRaisesMessage` | 21 | 7% |
| `str(exc) ==` | 3 | 1% |

Now the seam, drawn explicitly so it cannot be misread. The table above is a
**measured count of signals**. The mapping from signal type to *repairability
bucket* below is **qualitative** — grounded in 26 hand-classified cases, which is
far too thin to attach a percentage to. We present the shape, not a number.

- **mock-internal + exact call_args (the dominant types).** *Qualitative.* These
  land in two places: **contract** (the call is to a documented API — an endpoint
  URL, a named hook — that the issue specifies) or **flag-only / unwitnessed**
  (the assertion pins the exact shape of an *internal* interaction, e.g. the
  precise arguments to a log call). What they almost never are is *safely
  auto-repairable*: when the intended behavior is observable only through the
  mock, there is no independent oracle to repair the grader against.
- **exact message / `match=` (a minority).** *Qualitative.* This is where the
  safely-repairable cases concentrate: the issue states an observable behavior
  ("raise `ValueError` when X"), and the test additionally pins an incidental
  message string the PR chose. A bare `raises(ValueError)` already witnesses
  correctness independently of the wording. But this type also carries heavy
  **contract** (the issue specifies the message) and a genuinely **ambiguous**
  strictness zone (below).
- **private symbol (minority).** *Qualitative.* Form, split by whether a public
  behavioral witness exists — repairable when it does, flag-only when it doesn't.

**The finding that matters:** the *dominant* coupling types are the *least*
safely-repairable, and the repairable slice lives in a *minority* type. A tool
built to attack the volume would be aimed at exactly the wrong part of the corpus.

### 2.3 The safely-repairable fraction is small — and shrinks under scrutiny (direction, not a number)

We deliberately do not report a population percentage for the auto-repairable
("Mode A": coupled, and an independent correctness witness is obtainable without
fabricating it) fraction. The honest artifact is a **direction**, because every
attempt to pin the number moved it the same way — down.

```
message-enriched hand sample (n=26):   12 looked auto-repairable   (an UPPER bound;
                                                                    the sample was
                                                                    picked to favor
                                                                    the repairable kind)
after a static re-audit:               ~3 labels were noisy         (a "coupled" message
                                                                    was Python's own
                                                                    stdlib text; or the
                                                                    graded asserts were
                                                                    actually behavioral)
after semantic re-audit of the issue:  2 more collapsed to contract (the "invented" class
                                                                    /hook name was named
                                                                    in the issue as public
                                                                    API consumers depend on)
------------------------------------------------------------------
auto-repairable roughly halved under audit: 12 -> ~8 of 26
```

Read this as: the auto-repairable fraction is a **single-digit percentage of all
graded tasks and shrinks as labels are audited** — not as a specific number. The
sample is small, non-random, message-enriched, and its labels needed correcting.
Any single population figure here would be false precision. The *direction* is the
result.

## 3. The safe-repair method, demonstrated end-to-end (n=1)

Whatever the size of the repairable fraction, a repair is only worth shipping if
it is *regression-validated, not merely plausible*. We built and ran the full
four-gate contract on one real task, **`pytest-dev/pytest#10356`** ("Consider MRO
when obtaining marks for classes"), start to finish, with the offline
SWE-bench-format grader described in §2.1. This is a single worked case (n=1),
presented as a worked demonstration
of the method, not as a validated repair rate.

The task's sole `FAIL_TO_PASS` test asserts three implementation details the issue
never mentions: it imports a private symbol (`_pytest.mark.structures`), calls an
invented keyword (`get_unpacked_marks(C, consider_mro=False)`), and pins an exact
list order. The issue's actual contract is one behavioral sentence: a test
inheriting from two marked base classes should carry *both* marks. A hand-written
alternative fix that satisfies the behavior without inventing `consider_mro`
scores **0.0** on the inherited test — a real false negative, reproduced.

We repaired the test to assert the observable contract through pytest's public API
(`{m.name for m in item.iter_markers()} == {"a","b","c"}`), then ran four gates:

| gate | what it checks | result on `pytest#10356` |
|---|---|---|
| **G1** positive preservation | the gold patch still scores 1.0 | 1.0 ✓ |
| **G3** false-negative recovery | the witnessed correct alternative now scores 1.0 | 0.0 → 1.0 ✓ |
| **G2** negative preservation | known-bad solutions still score 0.0, split into a *training* battery and an independently-generated *held-out* set | training 0/4 survive; held-out 1/3 survive |
| **G4** contract grounding | the changed assertion is justified by the issue's stated contract, stored as auditable evidence | recorded (see overlay) |

The repair is emitted as a **versioned overlay** — `patch.diff`, `evidence.json`,
`mutants/` with verdicts, `validation.json` — that never modifies the upstream
grader in place, preserving historical comparability.

### 3.1 G4 is the pillar; mutation is a check, not a co-equal gate

The most useful thing we learned building the gates is which one carries the
safety. The held-out mutant set includes, by design, a **duplication mutant**
(`H_dup`): a fix that considers MRO but merges marks incorrectly so `iter_markers`
yields a marker twice. It **survives** the repaired test — measured:
`iter_markers()` returns `['a','b','c','a','b']`, but the *set* of names is still
`{'a','b','c'}`, so the assertion passes.

This is not a hole we hid. The issue's contract is silent on marker *duplication*,
so a behavioral test grounded in that contract correctly does not forbid it. We
record `H_dup` in the overlay as the repair's **documented boundary** — "this
repair does not distinguish marker duplication; the issue does not specify it" —
rather than pretending it is covered.

The consequence for the architecture is precise, and we state its scope narrowly:
**in this case, with clean contract-grounding, the train/held-out split changed no
accept verdict.** The mutant that survives survives whether it is held-out or
pooled; the repair was anchored to the *contract* (G4), not fitted to the mutants,
so there was no overfitting for a held-out set to catch. Therefore, *here*, G4 is
the load-bearing pillar and the mutation gate is a secondary check — it verifies
operationally that the loosened test still rejects concrete wrong programs (a
thing G4's semantic reasoning cannot do), and its anti-overfitting role becomes
load-bearing only when repairs are *automatically proposed* (a model proposing
reformulations that could be tuned to pass the exact mutants shown). We do **not**
generalize this to "held-out mutation is ceremony." One clean case does not show
that, and this is our cleanest case by construction. Whether held-out adds rigor
under weaker or ambiguous contract-grounding is left open.

## 4. Why localization needs semantic judgment

To scale the map beyond hand classification, the locator must decide, per coupled
assertion, whether it pins *contract* (leave it) or *form* (a repair candidate).
We built a static, no-LLM discriminant first — symbol privacy, known-constant
patterns (URLs, OIDs, paths), a round-trip signal (the asserted value also appears
as test input), and "is the string present in the issue." On the clear cases it
works: it correctly suppressed 8 of 9 of the hand-labeled contract false-positives
that a naive coupling filter would have flagged.

But swept over the full 26, the two signals we added to catch harder cases
**overfit**. "Round-trip" and "identifier-shaped constant" over-suppressed *real*
coupling that happened to also appear in test scaffolding (`'mb_track_extract'`
appears where a listener subscribes) or was identifier-shaped but PR-invented
(`'ServerlessRepoClientError'`). This is itself a measured finding: static
signals for contract-vs-form are brittle at exactly the boundary that matters.

The boundary is semantic, and it has two distinct sub-zones — a distinction worth
drawing because it decides what is fixable:

- **Invented-name vs spec-constant is resolvable by reading the issue.** Whether
  `ServerlessRepoClientError` is a PR-invented internal (form) or a specified
  public class (contract) is answered by the issue text: it names the class *as a
  public-API exception callers catch*. A judge that reads the full issue resolves
  this cleanly. This sub-zone needs a semantic reader, but it is *decidable*.
- **The strictness sub-zone is irreducible.** When the issue *paraphrases* a
  message without dictating it verbatim — "raise an error stating that lookupflag
  must have a value" versus a test pinning that exact string — no reader resolves
  it, because it hinges on a policy ("how verbatim must a stated message be to
  count as contract?") the issue alone does not settle. This is undecidable even
  with the full issue, absent an explicit domain policy. The honest output is
  "flag for human," not a forced call.

The semantic step is packaged as an **auditable rubric** (`judge_rubric.md`) — a
concrete prompt and a text-anchored decision procedure anyone can run and check
against the cited issue span, independent of who produced our labels. Critically:
**we claim no reliability metric for it.** The examples were judged by the same
author who produced the ground truth (contamination), n is tiny, and there is no
independent gold set. Measuring reliability requires independent multi-sample
calls and a human-audited gold — explicitly open work. What we provide is the
method, exposed for audit; not a validated accuracy.

## 5. Radical honesty: measured, estimated, open

- **Measured.** Coupling prevalence (35% vs ~2–4%); the signal-type distribution
  (218/182/68/46/21/3); the full four-gate result and `H_dup`'s survival on
  `pytest#10356`; the static discriminant's 8/9 contract-suppression on the hand
  set.
- **Estimated / qualitative.** The type→bucket mapping; the auto-repairable
  fraction. These rest on 26 non-random, message-enriched, hand-classified cases
  whose labels we corrected during the analysis. We give shape and direction, not
  percentages.
- **Open.** Independent reliability of the semantic judge; a human-audited gold
  set; whether held-out mutation adds rigor under weak contract-grounding; the map
  on a uniform random sample and on non-Python corpora.

Two honesty points we want a reader to hold onto. First, the auto-repairable
fraction shrank three times under scrutiny — because reading issues carefully
reveals that more of the asserted "form" is actually API the issue specifies. We
report that against our own interest; the map is valuable for being true, not for
a high repair number. Second, the end-to-end repair is validated on **one** task.
It is a worked demonstration of a method, not evidence of a repair rate. We are
careful never to let a measured signal count read as a quantified bucket, and
never to let n=1 read as coverage.

We use "regression-validated" throughout, never "provably safe": passing a
known-bad battery shows those programs fail, not that every incorrect program
fails. That is strong adversarial evidence against loosening — not a proof of
absence, and we do not call it one.

## 6. What this gives Prime, concretely

- **A map.** Where a corpus's reward signal is fragile, and of what kind — with
  the non-obvious shape that the dominant coupling (mock/call) is the least
  repairable and much apparent "form" is contract. This is decision-support for
  *where not to spend effort*.
- **A method.** A four-gate, overlay-based procedure to repair the
  high-confidence fraction with regression evidence and provenance, without
  modifying upstream and without loosening a test on faith — demonstrated
  end-to-end on a real task, with its boundary (`H_dup`) documented rather than
  hidden.
- **A routing.** An auditable contract-vs-form judge that suppresses the obvious
  cases cheaply and hands the fragile, semantic middle onward — telling
  `AgenticJudgeEnv` *where* the expensive per-rollout judgment is actually needed,
  and where a test is contract that needs no judge at all. Since that env
  currently substitutes for the deterministic reward with `judge_weight = 1.0`
  and `task_weight = 0.0` by default (`env.py:261-268`, `330-333`), knowing which
  tasks genuinely need it is not a cost optimisation only — it also bounds how
  much reward surface is handed to an uncalibrated verdict.

This is offline environment maintenance, run once per environment, deterministic
thereafter. It reduces how often the expensive online judge must run; it is not a
second copy of it. That is the complementarity, and it is why the honest,
narrow-scoped version of this work — *repair with evidence the small high-confidence
fraction, diagnose and route the rest* — is more useful to Prime than a repairer
that maximizes coverage by loosening tests it cannot witness.

---

## Appendix — reproduction & artifacts

This appendix is run-it-yourself, not trust-me. Every quantitative claim about
`pytest#10356` has a script and an exact command.

**Artifacts (in this repo):**

- `judge_rubric.md` — the auditable contract-vs-form judge (prompt, decision
  procedure, worked examples, limitations).
- `repro/` — reproduction scripts + the task's `gold.diff`, `tests.diff`,
  `meta.json`, and `repro/README.md` with prerequisites and every command.
- `overlays/pytest-dev__pytest-10356@rewardpatch-1/` — the versioned overlay:
  `patch.diff`, `evidence.json`, `mutants/` (training + held-out with verdicts),
  `validation.json` (G1–G4 + mutation survival rates). Upstream grader untouched.

**Reproduce the false negative and the four gates** (`PYT` = the pytest venv,
`PYG` = the grader venv; setup in `repro/README.md`), from `repro/`:

```bash
# false negative on the ORIGINAL inherited test
$PYT run_case.py gold  && $PYG grade.py log_gold.txt   # -> REWARD = 1.0
$PYT run_case.py alt   && $PYG grade.py log_alt.txt    # -> REWARD = 0.0  (correct alt, TypeError on consider_mro)

# the alt is genuinely correct, independent of the graded assertion
$PYT oracle.py         # base loses a marker ['foo'] ; alt carries both ['bar','foo']

# the repaired test + four gates (train/held-out split)
$PYG m4_heldout_gate.py   # G1 gold 1.0 ; G3 alt 0.0->1.0 ; G2 train 0/4 ; held-out 1/3 (H_dup survives)

# H_dup survives by the predicted mechanism
$PYT m4_mechanism.py      # iter_markers ['a','b','c','a','b'] ; name set {a,b,c} -> passes
```

**Provenance of every number in this document:**

- **Grading and its provenance.** Resolution is decided by upstream `swebench`
  4.0.3 (`get_eval_tests_report` / `get_resolution_status`); no grading logic was
  reimplemented. Our caller reproduces `SWEBenchTaskSet._calculate_reward` and
  `_get_logs_eval` as they stood at `verifiers` **v0.2.1** (2026-07-20), at
  `verifiers/envs/experimental/composable/tasksets/swe/swe_bench/taskset.py`.
  That file no longer exists: the entire v0 stack was removed on **2026-08-31**
  (commit `66a6064`, "feat!: remove the legacy (v0) stack"), and no SWE-bench
  taskset lives in `verifiers` today — SWE-like tasks route through Harbor, whose
  reward is produced by a verifier *inside the task image* and read back from
  `/logs/verifier/reward.json` (`verifiers/v1/tasksets/harbor/taskset.py:284-324`).
  There is therefore no in-repo grading path left to diff against. What we did
  instead: `repro/f1_grader_provenance.py` transcribes the v0.2.1 implementation
  literally (recovered with `git show v0.2.1:<path>`) and runs it beside ours on
  every captured log — **agreement on all 12**. We describe our grader as an
  offline SWE-bench-format grader, not as "the verifiers grader".
- Corpus figures (§2) are from a Scale-SWE prefix sample — non-random,
  Python-only, repo-clustered. The four-gate result (§3) is from **one** task.
  Both caveats are load-bearing and are stated wherever the numbers appear.
