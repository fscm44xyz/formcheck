# Localization Judge — Contract-vs-Form Rubric

An **auditable rubric** for the semantic step that adjudicates cases the
mechanical operators refuse. (Written for `rewardpatch`, the repair-framed
predecessor of `formcheck`; the rubric itself is unchanged.) Given a
task's issue text and one implementation-coupled assertion found in its graded
tests, it decides whether that assertion pins the task's **contract** (leave it
alone) or an incidental **form** the PR happened to choose (a candidate for
repair). It exists to resolve the cases the cheap static pre-filter cannot.

This document is the artifact. It is written so anyone can run the judgment and
audit each verdict against the cited issue text, **independently of who produced
the ground-truth labels used elsewhere in this project.**

---

## 1. Scope — what this judge is, and is not

- **Is:** an *offline localization* judge. It runs **once per task**, over the
  task's static grading code, before any training. It classifies *assertions*.
- **Is not:** a per-rollout *correctness* judge. It never inspects a solution or a
  trajectory and never decides whether an answer is right. That is the space of
  Prime's `AgenticJudgeEnv`, shipped 2026-08-07 in verifiers 0.3.0 / prime-rl
  0.8.0 (`verifiers/v1/envs/agentic_judge/env.py`), which by default *replaces*
  the deterministic reward with its own verdict — `judge_weight = 1.0`,
  `task_weight = 0.0` (`env.py:261-268`), applied at `env.py:330-333` — on a
  judge that is explicitly told the recorded scores may be wrong (`env.py:92-96`)
  and is not trained (`env.py:320`). This rubric complements that: it runs once,
  offline, before training, and never touches a rollout's reward.
- **Is not:** the witness step. Deciding whether a *correct alternative solution*
  exists to safely repair a FORM assertion is a separate stage (§4.2 of the spec).
  This judge only answers contract-vs-form.

The static pre-filter runs first and settles the obvious cases (URLs, OIDs,
clearly-private symbols, messages plainly absent from the issue). The judge is
invoked **only on what the pre-filter cannot resolve** — so the model is spent on
the genuinely fuzzy minority, not the whole corpus.

---

## 2. Inputs

1. **`issue`** — the full task issue / problem statement. The *full* text: the
   decisive signal is often in a "Proposed Solution" or "Expected Behavior"
   section that a truncated statement drops.
2. **`assertion`** — the exact coupled assertion line(s) from a graded test
   (a test in `FAIL_TO_PASS`/`PASS_TO_PASS`), including the payload: the exact
   string, symbol, endpoint, or call pattern being asserted.
3. *(optional)* **`test_fn`** — the enclosing test function, for context on how
   the payload is used (input vs output, mock target vs return value).

---

## 3. The question

> Does the exact payload asserted here express something the **issue specifies or
> requires** — so that *any* correct solution must reproduce it — or an
> **implementation choice the PR made** that the issue does not dictate, so a
> correct-but-different solution could legitimately differ?

`CONTRACT` = specified/required → **do not flag**.
`FORM` = incidental implementation choice → **flag as a repair candidate**.
`AMBIGUOUS` = the issue describes the intent but does not dictate the exact
payload verbatim → **flag for human policy, do not auto-anything**.

---

## 4. Decision procedure (anchored to the issue text)

Apply in order. Each step cites *where in the issue* the evidence must be found.

1. **Does the issue name the payload AS PART OF THE PUBLIC SURFACE others consume?**
   Search the *full* issue for the payload — a class name, hook/event name,
   endpoint URL, config key, constant, or exact message. The contract signal is
   **not** merely "the issue mentions it" — it is "the issue names it **and** it is
   public surface that something outside the implementation depends on": a hook
   plugins subscribe to, an exception callers catch, an endpoint clients hit, a
   name imported from the public API. When both hold, the payload is public
   contract → **CONTRACT**. Cite the sentence **and name who consumes it**.
   - `mb_track_extract` — the issue names it as a hook *plugins subscribe to*
     (named **and** public) → CONTRACT for the right reason.
   - `ServerlessRepoClientError` — the issue adds it to the *public API for callers
     to catch* (named **and** public) → CONTRACT for the right reason.
   - **"Named in the issue" is a strong PROXY for public contract, not proof.** A
     name a feature request floats for something that ends up **internal** (a
     private helper, an intermediate class no consumer references) is still
     **FORM** — the issue mentioning it does not put it on the consumed surface.
     The test to apply: *does anything outside the implementation depend on this
     exact name?* If not, it is form even if the issue proposed it.

2. **Is the payload absent from the issue entirely?**
   If the issue describes a *capability or behavior* and never mentions this
   symbol/string/structure (a private helper, an internal class discovered by AST
   inspection, an event name the issue doesn't propose, an error message the issue
   never states), the payload is the PR's own choice → **FORM**. Cite the absence:
   name what the issue *does* specify and note the payload is not among it.

3. **Does the issue paraphrase the payload without dictating it verbatim?**
   If the issue states the *content* but not the exact wording (e.g. *"raise an
   error stating that lookupflag must have a value"* vs a test asserting the exact
   string `"lookupflag must have a value"`), then a paraphrase would satisfy the
   issue but fail the assertion. This is **AMBIGUOUS**: it hinges on a *strictness
   policy* ("how verbatim must a stated message be to count as contract?") that the
   issue alone cannot settle. Flag for human policy; never auto-resolve.

4. **Payload-shape backstops** (use only when 1–3 are inconclusive):
   - Leading-underscore symbol (`_helper`, `_extended_rule`) → **FORM** unless the
     issue explicitly requires that internal.
   - Endpoint URL / OID / registered protocol constant the issue or an external
     spec defines → **CONTRACT**.
   - A value that is the function's *deterministic output* for a given input
     (the same literal appears as the test's input/fixture) → **CONTRACT**.

---

## 5. Output schema

```json
{
  "verdict": "CONTRACT | FORM | AMBIGUOUS",
  "confidence": "high | medium | low",
  "evidence": "the exact issue span (quoted) that decides it, or 'not present in issue'; for CONTRACT-by-naming, also name who consumes the payload (the public-surface test)",
  "rationale": "one or two sentences tying the payload to the issue"
}
```

---

## 6. The prompt (verbatim, ready to run)

```
You are an offline localization judge for RL-environment grading code. You are
given a task ISSUE and one ASSERTION from that task's hidden tests. Decide whether
the exact payload the assertion checks is part of the task's CONTRACT (something
the issue specifies or requires, so any correct solution must reproduce it) or
incidental FORM (an implementation choice the PR made that the issue does not
dictate, so a correct-but-different solution could differ).

Rules:
- Read the FULL issue. The deciding evidence is often in a "Proposed Solution" or
  "Expected Behavior" section.
- If the issue names or specifies the payload (class/hook/endpoint/constant/exact
  message) -> CONTRACT. Quote the sentence.
- If the issue describes a capability but never mentions this symbol/string/
  structure -> FORM. Say what the issue specifies instead.
- If the issue states the message CONTENT but not the exact wording (paraphrase)
  -> AMBIGUOUS. Do not guess; it is a strictness-policy call.
- Do NOT judge whether any solution is correct. Only classify the assertion.
- Output the JSON schema: {verdict, confidence, evidence (quoted issue span or
  "not present in issue"), rationale}.

ISSUE:
<full problem statement>

ASSERTION:
<exact coupled line(s) + payload>
```

---

## 7. Worked examples (audit these against the cited issue text)

These five are the frontier cases the static pre-filter over-suppressed or
mis-flagged. Two of them (marked ⚠) **corrected the author's own hand-labels** —
included deliberately, both to show the rubric's value and to be transparent that
the project's ground truth was itself noisy.

| task | payload | verdict | deciding evidence in the issue |
|---|---|---|---|
| aws-serverlessrepo pr25 ⚠ | `ServerlessRepoClientError` | CONTRACT | *"new exception classes to the public API: `ServerlessRepoClientError`"* — named **and** public (callers catch it) |
| beets pr3831 ⚠ | `mb_track_extract` | CONTRACT | *"The proposed hooks are: 1. `mb_track_extract`"* — named **and** public (plugins subscribe to it) |
| preliz pr302 | `MatchDistribution` | FORM | issue only specifies a `references` argument + plot behavior; never mentions a class named `MatchDistribution` (asserted via AST inspection) |
| fonttools pr1540 | `"lookupflag must have a value"` | AMBIGUOUS | *"raise an error stating that `lookupflag` must have a value"* — content stated, exact wording not dictated; a paraphrase satisfies the issue but fails `match=` |
| pyfluent pr139 | `InitializeWorkflow` | CONTRACT | *"use native StateEngine names (CamelCase) … like `InitializeWorkflow`"* — the native name is the issue's whole objective |

The ⚠ cases are the substantive finding: an assertion on an *exact class/hook name*
looks like textbook "form coupling," but when the issue names that exact name **as
public surface consumers depend on** (a hook plugins subscribe to, an exception
callers catch), it is contract, and repairing it would break the task. Only
reading the full issue — and asking *who consumes this name* — separates the two.
The mirror-image case keeps the rule honest: a name the issue proposes for
something that stays **internal** is still form, because nothing outside the
implementation depends on it.

---

## 8. Reliability & limitations (read before trusting any number)

**No validated reliability metric is claimed for this judge, and none should be
inferred from the worked examples.** What this document provides is an *auditable
method*, not a measured accuracy.

- The examples were classified by the same author who produced the project's
  ground-truth labels. That is **contamination**: "the judge corrected the labels"
  is really "the author, reading the issues more carefully, corrected earlier
  hasty labels." Valuable as a demonstration that careful issue-grounded reading
  resolves these cases; **not** independent validation.
- Sample size is tiny (5 frontier cases; 26 hand-classified overall).
- Measuring true reliability requires: (a) **independent multi-sample** model
  calls (not the project author), (b) a **human-audited gold set** built by
  someone other than the label author, (c) inter-rater agreement on the AMBIGUOUS
  boundary. This is **open work**, explicitly not done here.
- The AMBIGUOUS class is not a judge failure — it is a real boundary (message
  paraphrase / specification strictness) that no reader resolves without a stated
  domain policy. The honest output there is "flag for human," not a forced call.

**Bottom line:** this is the method, exposed for audit. The metric is future work.
