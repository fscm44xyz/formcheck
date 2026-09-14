"""judge-variance step 1 -- the variance floor of a semantic judge.

Measures ONE quantity: how much a judge's score on IDENTICAL input moves on its
own. No transforms are involved; the judge scores the unmodified gold patch of
each task against that task's issue text, N times per temperature arm.

The protocol is `judge/PROTOCOL.md`, committed before this script was ever run.
Everything this script decides -- task selection, prompt, scale, N, the two
temperature arms, the parse rule, the cost ceiling -- is fixed there. If a
number here disagrees with that document, the document is right and this script
is a defect.

The prompt is NOT in this file. It is `judge/prompt_template.txt`, read at run
time and digested into every record, so there is exactly one copy and no way for
a committed prompt and a running prompt to drift apart.

Usage:
    python judge/variance.py --dry-run          # projection + prompt, no calls
    python judge/variance.py                    # both arms, writes records
"""
import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "prompt_template.txt")

DEFAULT_MODEL = "gpt-5.6-luna"
N_CALLS = 5
ARMS = (0.0, 1.0)

# PROTOCOL.md 1.11.2 -- step 1b. 400 is what voided step 1: it is a reasoning
# model, and at 400 the budget was spent on reasoning before any visible text.
# 4000 is 10x that and ~11x the largest SUCCESSFUL step-1 call (351 tokens).
# Deliberately NOT fitted to the observed 115..351: those are the uncensored
# tail of a distribution censored at 400, so they bound the requirement from
# below only, and a cap fitted to them would re-create the defect while looking
# data-driven.
MAX_OUTPUT_TOKENS = 4_000

# PROTOCOL.md 1.11.1 -- the prompt is frozen by digest across step 1 and 1b.
FROZEN_PROMPT_SHA256 = (
    "798ed4c9f3997ade69b14e2090969dd9caea43c1bad660d9ee612cecbe5761fd")

# PROTOCOL.md 2.1a -- the sufficiency condition. A per-task range is admitted
# only at full N; an arm needs this many admitted tasks for its aggregate.
MIN_USABLE_PER_TASK = N_CALLS
MIN_COUNTING_TASKS = 8

# PROTOCOL.md 1.11.4 -- fixed before the run. Below this, step 1b is a second
# failure to instrument the judge and NO third configuration is attempted.
MIN_PARSE_RATE = 0.95

ISSUE_CAP = 12_000
PATCH_CAP = 20_000

COST_CEILING_USD = 2.00

# USD per 1M tokens (input, output). Same table and same provenance as
# `repro/f4_adjudicate.py`: the OpenAI pricing page, 2026-09-06. An unlisted
# model reports tokens and leaves the cost null rather than inventing a rate.
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

# PROTOCOL.md 1.1 -- frozen before the run. Recomputed by `select()` below and
# asserted equal, so a change to the selection rule cannot pass silently.
FROZEN_10 = [
    "astropy__astropy-12907",
    "django__django-11179",
    "psf__requests-1766",
    "pydata__xarray-4966",
    "pylint-dev__pylint-4551",
    "pytest-dev__pytest-10356",
    "scikit-learn__scikit-learn-14141",
    "sphinx-doc__sphinx-7454",
    "sympy__sympy-13031",
    "django__django-11433",
]


def witness_tasks():
    """The 28 instance ids carrying at least one WITNESS verdict in M4."""
    import glob
    ids = []
    for path in sorted(glob.glob(os.path.join(ROOT, "scale", "records_m4", "*.json"))):
        with open(path) as fh:
            rec = json.load(fh)
        if any(w.get("verdict") == "WITNESS" for w in (rec.get("witnesses") or [])):
            ids.append(rec["instance_id"])
    return sorted(ids)


def select(ids, k=10):
    """PROTOCOL.md 1.1: group by repository prefix in first-appearance order,
    take one from each group in turn until k are held."""
    groups = {}
    for i in ids:
        groups.setdefault(i.split("__")[0], []).append(i)
    out, rank = [], 0
    while len(out) < k:
        progressed = False
        for members in groups.values():
            if rank < len(members):
                out.append(members[rank])
                progressed = True
                if len(out) == k:
                    return out
        if not progressed:
            break
        rank += 1
    return out


def load_rows(ids):
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from datasets import load_dataset
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    by_id = {r["instance_id"]: r for r in ds}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise SystemExit(f"not in the dataset: {missing}")
    return {i: by_id[i] for i in ids}


def build_prompt(template, issue, patch):
    """PROTOCOL.md 1.4 -- literal token replacement, never `str.format`: the
    template contains JSON braces in its required-output block."""
    truncated = []
    if len(issue) > ISSUE_CAP:
        issue, _ = issue[:ISSUE_CAP], truncated.append("issue")
    if len(patch) > PATCH_CAP:
        patch, _ = patch[:PATCH_CAP], truncated.append("patch")
    return template.replace("{issue}", issue).replace("{patch}", patch), truncated


SCORE_RE = re.compile(r'"score"\s*:\s*(-?\d+)')


def parse(text):
    """PROTOCOL.md 1.7 -- one JSON object with an integer score in 0..10, or a
    parse failure. Never retried."""
    if not text:
        return None, None, "empty response"
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            score = obj.get("score")
            if isinstance(score, bool) or not isinstance(score, int):
                return None, obj.get("rationale"), f"score is not an integer: {score!r}"
            if not 0 <= score <= 10:
                return None, obj.get("rationale"), f"score out of range: {score}"
            return score, obj.get("rationale"), None
        except json.JSONDecodeError as exc:
            return None, None, f"json decode error: {exc}"
    m = SCORE_RE.search(text)
    if m:
        return None, None, f"no JSON object; a bare score field was present ({m.group(1)})"
    return None, None, "no JSON object in response"


def digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def usage_counts(usage):
    tin = getattr(usage, "input_tokens", None)
    tout = getattr(usage, "output_tokens", None)
    if tin is None:
        tin = getattr(usage, "prompt_tokens", None)
    if tout is None:
        tout = getattr(usage, "completion_tokens", None)
    cached = None
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
    return tin, tout, cached


def spread(scores, n_required=MIN_USABLE_PER_TASK):
    """PROTOCOL.md 2.1a(a). A range is ADMITTED only at n = N.

    Below that the task reports `range: None` with `admitted: False` and an
    explicit reason -- never `range: 0`, which is what a one-element set yields
    by construction and which is the permissive end of the 2.1 threshold. The
    range is monotone non-decreasing in n, so admitting n < N biases the gate
    toward opening. `observed_range` is kept for the record and is NOT what the
    gate reads."""
    out = {"n": len(scores), "admitted": False, "range": None,
           "stdev": None, "mean": None}
    if scores:
        out.update({
            "min": min(scores), "max": max(scores),
            "observed_range": max(scores) - min(scores),
            "mean": round(statistics.fmean(scores), 3),
            "stdev": round(statistics.stdev(scores), 3) if len(scores) > 1 else 0.0,
        })
    if len(scores) < n_required:
        out["unadmitted_reason"] = (
            f"unmeasured (n = {len(scores)} of {n_required}); PROTOCOL.md 2.1a(a)")
        return out
    out["admitted"] = True
    out["range"] = max(scores) - min(scores)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=N_CALLS)
    ap.add_argument("--dry-run", action="store_true",
                    help="projection and one rendered prompt; sends nothing")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "step1b_result.json"))
    args = ap.parse_args()

    with open(TEMPLATE) as fh:
        template = fh.read()
    template_sha = hashlib.sha256(template.encode()).hexdigest()
    # PROTOCOL.md 1.11.1 -- same prompt as step 1, asserted, not assumed.
    if template_sha != FROZEN_PROMPT_SHA256:
        raise SystemExit(
            "prompt digest does not match the value frozen in PROTOCOL.md 1.11.1.\n"
            f"  computed: {template_sha}\n  frozen  : {FROZEN_PROMPT_SHA256}\n"
            "Step 1b changes the output cap and nothing else. Aborting.")

    population = witness_tasks()
    chosen = select(population, 10)
    if chosen != FROZEN_10:
        raise SystemExit(
            "selection does not reproduce PROTOCOL.md 1.1.\n"
            f"  computed: {chosen}\n  frozen  : {FROZEN_10}")

    rows = load_rows(chosen)

    prompts, any_truncated = {}, []
    for iid in chosen:
        text, trunc = build_prompt(template, rows[iid]["problem_statement"], rows[iid]["patch"])
        prompts[iid] = text
        if trunc:
            any_truncated.append((iid, trunc))

    rate = PRICES.get(args.model)
    chars = sum(len(p) for p in prompts.values())
    est_in = chars / 4 * args.n * len(ARMS)
    # worst case is every call running to the cap (PROTOCOL.md 1.11.2 step 5)
    est_out = MAX_OUTPUT_TOKENS * args.n * len(ARMS) * len(chosen)
    est_cost = (est_in * rate[0] / 1e6 + est_out * rate[1] / 1e6) if rate else None

    print("judge-variance -- step 1b, the variance floor "
          "(step 1 is VOID, PROTOCOL.md 1.10)")
    print(f"  protocol       : judge/PROTOCOL.md")
    print(f"  prompt sha256  : {template_sha}")
    print(f"  model          : {args.model}")
    print(f"  tasks          : {len(chosen)}   population: {len(population)} witness tasks")
    print(f"  arms           : {', '.join('T=' + str(t) for t in ARMS)}")
    print(f"  N per arm      : {args.n}")
    print(f"  total calls    : {len(chosen) * args.n * len(ARMS)}")
    print(f"  output cap     : {MAX_OUTPUT_TOKENS} tokens (PROTOCOL.md 1.11.2)")
    print(f"  input caps     : issue {ISSUE_CAP}, patch {PATCH_CAP} chars -- fired: "
          f"{any_truncated or 'none'}")
    if rate:
        print(f"  rate           : ${rate[0]:.2f} in / ${rate[1]:.2f} out per 1M")
        print(f"  projected cost : ${est_cost:.4f}   (ceiling ${COST_CEILING_USD:.2f})")
    else:
        print(f"  rate           : unknown -- {args.model} is not in the local price table")

    if est_cost is not None and est_cost > COST_CEILING_USD:
        raise SystemExit(
            f"\nPROTOCOL.md 1.9: projected ${est_cost:.2f} exceeds the ${COST_CEILING_USD:.2f} "
            "ceiling. Nothing was sent.")

    if args.dry_run:
        print("\n--- rendered prompt, " + chosen[0] + " ---\n")
        print(prompts[chosen[0]])
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("\nOPENAI_API_KEY is not set; nothing was sent. "
                         "Use --dry-run to inspect the projection and the prompt.")
    from openai import OpenAI
    client = OpenAI()

    records, tin_total, tout_total, cached_total = [], 0, 0, 0
    temp_rejected = {}

    for temp in ARMS:
        for iid in chosen:
            body = {"model": args.model, "input": prompts[iid],
                    "temperature": temp, "max_output_tokens": MAX_OUTPUT_TOKENS}
            body_sha = digest(body)
            seen_sha = set()
            for call in range(1, args.n + 1):
                t0 = time.time()
                sent = dict(body)
                note = None
                try:
                    resp = client.responses.create(**sent)
                except Exception as exc:
                    msg = str(exc)
                    if "temperature" in msg.lower():
                        # PROTOCOL.md 1.5 -- record it, never drop it quietly.
                        temp_rejected[temp] = msg
                        sent = {k: v for k, v in body.items() if k != "temperature"}
                        note = ("temperature rejected by the endpoint; sent at the "
                                "provider default. This arm is NOT T=%s." % temp)
                        try:
                            resp = client.responses.create(**sent)
                        except Exception as exc2:
                            records.append({"instance_id": iid, "temperature": temp,
                                            "call": call, "error": str(exc2),
                                            "score": None, "parse_error": "request failed"})
                            continue
                    else:
                        records.append({"instance_id": iid, "temperature": temp,
                                        "call": call, "error": msg,
                                        "score": None, "parse_error": "request failed"})
                        continue
                seen_sha.add(digest(sent))
                text = resp.output_text
                score, rationale, perr = parse(text)
                tin, tout, cached = usage_counts(getattr(resp, "usage", None) or object())
                tin_total += tin or 0
                tout_total += tout or 0
                cached_total += cached or 0
                records.append({
                    "instance_id": iid, "temperature": temp, "call": call,
                    "score": score, "rationale": rationale, "parse_error": perr,
                    "raw": text if perr else None,
                    "request_sha256": digest(sent), "note": note,
                    "response_id": getattr(resp, "id", None),
                    "input_tokens": tin, "output_tokens": tout, "cached_tokens": cached,
                    # PROTOCOL.md 1.11.3 -- the cap's firing is RECORDED, not
                    # inferred. Step 1 could not report the cap it died on.
                    "output_cap_hit": bool(tout is not None and tout >= MAX_OUTPUT_TOKENS),
                    "elapsed": round(time.time() - t0, 2),
                })
                print(f"    T={temp} {iid:34s} call {call}/{args.n}  "
                      f"score={score if score is not None else 'PARSE-FAIL'}"
                      f"{'  [OUTPUT CAP HIT]' if records[-1]['output_cap_hit'] else ''}")
            # PROTOCOL.md 1.6 -- identical input, asserted, not assumed.
            if len(seen_sha) > 1:
                raise SystemExit(
                    f"request payload differed across calls for {iid} at T={temp}: "
                    f"{sorted(seen_sha)}. Aborting rather than reporting a spread "
                    "a payload difference could explain.")
            if seen_sha and body_sha not in seen_sha and not temp_rejected:
                raise SystemExit(f"payload digest drifted for {iid} at T={temp}")

    cost = None
    if rate:
        cost = tin_total * rate[0] / 1e6 + tout_total * rate[1] / 1e6

    # ---- PROTOCOL.md 1.11.4: the parse rate and the cap audit are computed and
    # printed BEFORE any spread, range, median or gate verdict exists. A parse
    # rate inspected after a favourable floor is one nobody would have acted on.
    n_calls_made = len(records)
    n_usable = sum(1 for r in records if r.get("score") is not None)
    parse_rate = (n_usable / n_calls_made) if n_calls_made else 0.0
    cap_hits = sum(1 for r in records if r.get("output_cap_hit"))
    instrument = {
        "calls": n_calls_made,
        "usable": n_usable,
        "parse_rate": round(parse_rate, 4),
        "min_parse_rate": MIN_PARSE_RATE,
        "parse_rate_ok": parse_rate >= MIN_PARSE_RATE,
        "output_cap": MAX_OUTPUT_TOKENS,
        "output_cap_hits": cap_hits,
        # PROTOCOL.md 1.11.3 -- one call at the cap voids the run.
        "void_on_cap": cap_hits > 0,
        "input_truncation": any_truncated or "none -- input caps did not fire",
    }
    if cap_hits:
        instrument["void_reason"] = (
            f"PROTOCOL.md 1.11.3: {cap_hits} of {n_calls_made} calls sat at the "
            f"{MAX_OUTPUT_TOKENS}-token output cap. The cap is still shaping the "
            "output distribution, so any floor computed here is computed on "
            "censored draws. VOID on a harness defect (1.10), not a measurement.")
    elif not instrument["parse_rate_ok"]:
        instrument["stop_reason"] = (
            f"PROTOCOL.md 1.11.4: parse rate {parse_rate:.1%} is below "
            f"{MIN_PARSE_RATE:.0%}. This is a SECOND failure to instrument the "
            "judge. No third configuration is attempted: not a higher cap, not a "
            "different model, not a constrained output format, not a re-pick, not "
            "a raised N. Reportable only as a statement about the apparatus.")

    print("\n--- PROTOCOL.md 1.11.4: instrument check, read before any floor ---")
    print(f"  usable scores  : {n_usable}/{n_calls_made}  "
          f"parse rate {parse_rate:.1%}  (threshold {MIN_PARSE_RATE:.0%}) "
          f"-> {'OK' if instrument['parse_rate_ok'] else 'BELOW THRESHOLD'}")
    print(f"  output cap hits: {cap_hits}/{n_calls_made} at {MAX_OUTPUT_TOKENS} "
          f"-> {'VOID (1.11.3)' if cap_hits else 'cap did not bind'}")
    tw = [r["output_tokens"] for r in records if r.get("output_tokens")]
    if tw:
        print(f"  output tokens  : min={min(tw)} max={max(tw)} "
              f"median={statistics.median(tw):.0f}")

    per_task = {}
    for temp in ARMS:
        arm = {}
        for iid in chosen:
            rs = [r for r in records if r["instance_id"] == iid and r["temperature"] == temp]
            scores = [r["score"] for r in rs if r["score"] is not None]
            arm[iid] = {"scores": [r["score"] for r in rs],
                        "parse_failures": sum(1 for r in rs if r["score"] is None),
                        **spread(scores)}
        per_task[str(temp)] = arm

    aggregate = {}
    for temp in ARMS:
        arm = per_task[str(temp)]
        # PROTOCOL.md 2.1a(a) -- only ADMITTED ranges enter the aggregate.
        ranges = [v["range"] for v in arm.values() if v.get("admitted")]
        unmeasured = {k: v["n"] for k, v in arm.items() if not v.get("admitted")}
        pooled = [s for v in arm.values() for s in v["scores"] if s is not None]
        # PROTOCOL.md 2.1a(b) -- a median over a survivor subset is not the
        # median of the sample 1.1 froze, and a max over half of it is not a max.
        covered = len(ranges) >= MIN_COUNTING_TASKS
        aggregate[str(temp)] = {
            "counting_tasks": len(ranges),
            "min_counting_tasks": MIN_COUNTING_TASKS,
            "unmeasured_tasks": unmeasured,
            "coverage_ok": covered,
            "ranges": sorted(ranges),
            "median_range": statistics.median(ranges) if covered else None,
            "max_range": max(ranges) if covered else None,
            "tasks_with_range_0": sum(1 for r in ranges if r == 0),
            "pooled_stdev": round(statistics.stdev(pooled), 3) if len(pooled) > 1 else None,
            "parse_failures": sum(v["parse_failures"] for v in arm.values()),
        }
        if not covered:
            aggregate[str(temp)]["floor"] = (
                f"not measured -- {len(ranges)} of {len(arm)} tasks reached "
                f"n = {MIN_USABLE_PER_TASK} (PROTOCOL.md 2.1a(b) requires "
                f"{MIN_COUNTING_TASKS})")

    # PROTOCOL.md 2.1 + 2.1a. The gate is evaluated ONLY on a non-void run whose
    # parse rate cleared 1.11.4; otherwise there is no floor for it to read.
    gate = {"evaluated": False}
    t1 = aggregate.get("1.0")
    if instrument["void_on_cap"]:
        gate["reason"] = instrument["void_reason"]
    elif not instrument["parse_rate_ok"]:
        gate["reason"] = instrument["stop_reason"]
    elif not t1["coverage_ok"]:
        gate.update({"evaluated": True, "opens": False,
                     "coverage_ok": False, "reason": t1["floor"]})
    else:
        gate = {"evaluated": True,
                "coverage_ok": True,
                "counting_tasks": t1["counting_tasks"],
                "median_range_le_2": t1["median_range"] <= 2,
                "max_range_le_4": t1["max_range"] <= 4}
        gate["opens"] = gate["median_range_le_2"] and gate["max_range_le_4"]

    out = {
        "milestone": "judge-variance", "step": "1b",
        "supersedes": None,
        "step1_status": ("VOID on a harness defect (PROTOCOL.md 1.10): a "
                         "400-token output cap against a reasoning model. No "
                         "judge variance was observed in step 1, so none is "
                         "reported from it. Step 1b is a new measurement, not a "
                         "correction of a step-1 number."),
        "protocol": "judge/PROTOCOL.md",
        "prompt_sha256": template_sha,
        "provider": "openai", "model": args.model,
        "n_per_arm": args.n, "arms": list(ARMS),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature_rejected": temp_rejected or None,
        "tasks": chosen,
        "population": {"witness_tasks": len(population),
                       "note": "the floor is measured on coupled tasks, not a random draw from the 500"},
        # NOT named `truncation`: it consults the 1.2 INPUT caps only. The
        # output cap is reported separately, under `instrument`. Step 1 printed
        # "no cap fired" here while the output cap fired on 84 of 100 calls.
        "input_truncation": any_truncated or "none -- input caps did not fire",
        "instrument": instrument,
        "per_task": per_task, "aggregate": aggregate,
        "step2_gate": gate,
        "input_tokens": tin_total, "output_tokens": tout_total,
        "cached_input_tokens": cached_total,
        "cost_usd": round(cost, 5) if cost is not None else None,
        "records": records,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)

    print(f"\n[usage] in={tin_total} out={tout_total} cached={cached_total} "
          f"cost={'$%.5f' % cost if cost is not None else 'unknown'}")
    print(f"[wrote] {args.out}")
    for temp in ARMS:
        a = aggregate[str(temp)]
        print(f"  T={temp}: counting={a['counting_tasks']}/{len(chosen)} "
              f"ranges={a['ranges']} median={a['median_range']} max={a['max_range']} "
              f"parse_fail={a['parse_failures']}")
        if not a["coverage_ok"]:
            print(f"         {a['floor']}")

    if instrument["void_on_cap"]:
        print("\n  STEP 1B IS VOID -- " + instrument["void_reason"])
    elif not instrument["parse_rate_ok"]:
        print("\n  STOP -- " + instrument["stop_reason"])
    else:
        print(f"\n  step-2 gate (PROTOCOL.md 2.1 + 2.1a): "
              f"{'OPENS' if gate['opens'] else 'DOES NOT OPEN'}")


if __name__ == "__main__":
    main()
