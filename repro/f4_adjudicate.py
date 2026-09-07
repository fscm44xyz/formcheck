"""Phase 4.3 -- route one BORDER case to `judge_rubric.md`. One case, n=1.

This demonstrates that the pipeline reaches the rubric. It measures NOTHING: one
adjudication is not a reliability figure, and the rubric's own section 8 says no
reliability metric is claimed for it.

The case: `pallets__flask-5014`. `symbol_rename` refused the only anchor because
the issue names `Blueprint` (the mechanised G4 check). The question the rubric
exists to answer is whether being named makes it CONTRACT, or whether it is
merely the subject of the sentence.

PROVIDER: OpenAI. The rubric prompt itself is provider-independent -- it is
extracted verbatim from `judge_rubric.md` section 6 and not reworded here, so the
same prompt can be pointed at any model.

MODEL CHOICE (a judgement call, not a measurement -- see `--model`):
`gpt-5.6-luna` at $0.20 / $1.20 per 1M tokens. It is the cheapest model of the
current generation, and this task is short-context reading comprehension against
an explicit decision procedure rather than code synthesis.

We did NOT take the cheapest model available (`gpt-5-nano`, $0.05 / $0.40). The
rubric turns on a distinction a weak judge collapses: "named in the issue" is a
strong PROXY for contract, not proof, and the deciding condition is whether the
payload is public surface consumers depend on. A model that answers CONTRACT for
the wrong reason is worse than useless here, because the point of routing to a
rubric is the audit trail, not the label.

And price is not the real constraint at this size. MEASURED on the run of
2026-09-06: 419 input tokens, 240 output, **$0.00037**. Across the whole range
from `gpt-5-nano` to `gpt-5.1` one case costs roughly $0.0001 to $0.003. If a
verdict looks shaky, re-run it on a stronger model with `--model` rather than
trusting the cheap one; that decision costs a fraction of a cent.

RESULT of that run (`adjudication_result.json`, archived beside this script under
`../overlays/pallets__flask-5014@formcheck-1/`): verdict CONTRACT. Read the
rationale before trusting the label -- it leads with the naming rule, not with
the public-surface condition that the rubric's prose says should decide. Right
answer, weaker reason; see section 8 of the writeup.

Usage:
    python f4_adjudicate.py --dry-run             # render the prompt, spend nothing
    python f4_adjudicate.py                       # one API call

Needs `OPENAI_API_KEY` in the environment, and `pip install openai`. With no key,
`--dry-run` still writes the exact prompt that would be sent.
"""
import os
import re
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
F4 = os.path.abspath(os.path.join(HERE, "..", "..", "f4"))
RUBRIC = os.path.abspath(os.path.join(HERE, "..", "judge_rubric.md"))
# The committed copy of this case's inputs and result. `f4/` holds ~540 MB of
# mounted repos and is meant to be deleted; the archive is what survives, so the
# script reads from it and writes to it when `f4/` is gone.
ARCHIVE = os.path.abspath(os.path.join(
    HERE, "..", "overlays", "pallets__flask-5014@formcheck-1"))


def case_dir(instance_id):
    live = os.path.join(F4, instance_id)
    return live if os.path.isdir(live) else ARCHIVE


def out_dir():
    return F4 if os.path.isdir(F4) else ARCHIVE

DEFAULT_MODEL = "gpt-5.6-luna"

# USD per 1M tokens (input, output), from the OpenAI pricing page, 2026-09-06.
# Used only to report the real cost of a run; an unlisted model reports tokens
# and leaves the cost null rather than inventing a rate.
PRICES = {
    "gpt-6-astra":   (10.00, 50.00),
    "gpt-5.6-sol":   (4.00, 20.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna":  (0.20, 1.20),
    "gpt-5.5":       (5.00, 30.00),
    "gpt-5.4":       (2.50, 15.00),
    "gpt-5.4-mini":  (0.75, 4.50),
    "gpt-5.4-nano":  (0.20, 1.25),
    "gpt-5.2":       (1.75, 14.00),
    "gpt-5.1":       (1.25, 10.00),
    "gpt-5":         (1.25, 10.00),
    "gpt-5-mini":    (0.25, 2.00),
    "gpt-5-nano":    (0.05, 0.40),
    "o3":            (2.00, 8.00),
    "o4-mini":       (1.10, 4.40),
}

CASE = {
    "instance_id": "pallets__flask-5014",
    "assertion_file": "tests/test_blueprints.py",
    "assertion": (
        "def test_empty_name_not_allowed(app, client):\n"
        "    with pytest.raises(ValueError):\n"
        '        flask.Blueprint("", __name__)'),
    "payload": (
        "the module-level symbol `Blueprint` in `src/flask/blueprints.py`, "
        "reached by the graded test as `flask.Blueprint`. A behaviour-preserving "
        "alpha-rename of that symbol would make this test fail, so the question "
        "is whether the symbol's NAME is part of the task's contract."),
}


def extract_prompt(rubric_text):
    """The verbatim prompt from section 6 of the rubric. Not reworded here: if the
    rubric changes, this changes with it, and nothing else does."""
    m = re.search(r"## 6\. The prompt \(verbatim, ready to run\)\s*```(.+?)```",
                  rubric_text, re.S)
    if not m:
        raise SystemExit("could not find the verbatim prompt in judge_rubric.md")
    return m.group(1).strip()


def build(case):
    with open(RUBRIC, encoding="utf-8") as f:
        template = extract_prompt(f.read())
    with open(os.path.join(case_dir(case["instance_id"]), "issue.txt"),
              encoding="utf-8") as f:
        issue = f.read().strip()
    body = template.split("ISSUE:")[0].strip()
    return (f"{body}\n\nISSUE:\n{issue}\n\nASSERTION:\n"
            f"{case['assertion_file']}\n{case['assertion']}\n\n"
            f"PAYLOAD UNDER TEST:\n{case['payload']}\n")


def token_counts(usage):
    """The Responses API reports `input_tokens` / `output_tokens`; older surfaces
    use `prompt_tokens` / `completion_tokens`. Read whichever is present rather
    than assuming, so a cost line is never silently wrong."""
    def pick(*names):
        for name in names:
            value = getattr(usage, name, None)
            if value is not None:
                return int(value)
        return None
    return pick("input_tokens", "prompt_tokens"), \
        pick("output_tokens", "completion_tokens")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="render the prompt and exit without calling the API")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    prompt = build(CASE)
    out = os.path.join(out_dir(), "adjudication_prompt.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"prompt rendered -> {out}  ({len(prompt)} chars)")
    print(f"model            : {args.model}")
    rate = PRICES.get(args.model)
    if rate:
        print(f"rate             : ${rate[0]:.2f} in / ${rate[1]:.2f} out per 1M tokens")
    if args.dry_run:
        print()
        print(prompt)
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set; nothing was sent. "
                         "Use --dry-run to inspect the prompt.")
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("pip install openai")

    client = OpenAI()
    resp = client.responses.create(model=args.model, input=prompt)
    text = resp.output_text
    print()
    print(text)

    tin, tout = token_counts(getattr(resp, "usage", None) or object())
    cost = None
    if rate and tin is not None and tout is not None:
        cost = tin * rate[0] / 1e6 + tout * rate[1] / 1e6
        print(f"\n[usage] in={tin} out={tout} cost=${cost:.5f}")
    else:
        print(f"\n[usage] in={tin} out={tout} cost=unknown "
              f"(model not in the local price table)")

    record = {
        "case": CASE["instance_id"],
        "provider": "openai",
        "model": args.model,
        "reply": text,
        "input_tokens": tin,
        "output_tokens": tout,
        "cost_usd": round(cost, 5) if cost is not None else None,
        "n": 1,
        "caveat": "n=1; demonstrates routing, measures no rate",
    }
    result_path = os.path.join(out_dir(), "adjudication_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print(f"-> {result_path}")


if __name__ == "__main__":
    main()
