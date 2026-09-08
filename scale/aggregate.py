"""Aggregate the per-task records. A separate pass, on purpose.

Computing rates inside the run would mean the number and the evidence share a
code path and a moment: a task that errors halfway leaves a half-updated counter,
and nothing can be recomputed without re-running containers. Here every input is
a finished record on disk, so the aggregate is a pure function of them and can be
recomputed, diffed and argued with.

WHY A COMBINED OPERATOR PERCENTAGE CANNOT BE EMITTED FROM HERE.
`writeup.md` 6.5 and `CHANGES.md` 2 both record the same conclusion: the four
operators answer different questions with different strengths of evidence, and
one percentage over all of them would be meaningless -- `symbol_rename` is the
only operator whose failure mode is LOUD, so it is the only one whose verdicts
rest on the task's own suite rather than on an oracle nobody wrote. A convention
saying "report them separately" is something a person can forget while writing a
summary at 2am. So this module makes it structural instead:

  * `witness_rate` REQUIRES an operator id. There is no arity of it that
    computes a rate across operators.
  * `_forbid_merged` walks the finished report before it is written and raises if
    any rate-shaped object in it does not name the operator it belongs to.

To emit a merged percentage you would have to delete a guard, which is a visible
edit in a diff, rather than forget a convention, which is invisible.

Usage:
    ~/.venv-fc/bin/python scale/aggregate.py [-o scale/aggregate.json]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "repro"))

RESULTS = os.path.join(HERE, "records")

# The operator THE NUMBER is scoped to, and the reason, kept together so the
# scoping travels with the claim.
THE_NUMBER_OPERATOR = "symbol_rename"
THE_NUMBER_JUSTIFICATION = (
    "symbol_rename is the only operator in the family whose failure mode is "
    "LOUD: an incomplete alpha-rename raises AttributeError/ImportError/"
    "NameError naming the symbol on first use, so the task's own PASS_TO_PASS "
    "suite is a sufficient oracle for it. Every other operator fails silently, "
    "so on a task with no independently written contract oracle its cases are "
    "UNVALIDATED and cannot contribute to a rate."
)

JUDGED = ("WITNESS", "CLEAN", "INVALID")


def wilson(successes: int, trials: int, z: float = 1.96):
    """Wilson score interval -- the honest one at small n.

    The normal approximation is wrong exactly where this project lives: at
    0/12 it gives the interval [0, 0], which would report "no coupling exists"
    from twelve observations. Wilson does not collapse at the boundary, so a
    zero numerator still returns an upper bound worth quoting, and that upper
    bound is the whole content of a null result here.
    """
    if not trials:
        return None
    import math
    p = successes / trials
    d = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / d
    half = z * math.sqrt(p * (1 - p) / trials
                         + z * z / (4 * trials * trials)) / d
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


class MergedRateError(RuntimeError):
    """Raised when a rate would be reported without naming its operator."""


def load_records(directory=RESULTS):
    records = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json") or name.endswith(".partial"):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            records.append(json.load(f))
    return records


def controlled(records):
    """Tasks whose untransformed reference solution scored 1.0 in its own image.

    This is the only legitimate denominator for a witness rate. A task whose
    control failed proves nothing in either direction, and counting it as "no
    witness found" would quietly convert a broken harness into evidence of a
    clean reward -- the inversion 4.1 exists to prevent.
    """
    return [r for r in records if r["control"]["passed"]]


def witness_rate(records, operator):
    """Witness rate for ONE named operator over CONTROLLED tasks.

    `operator` is required and has no default. That is the structural half of
    the no-merged-percentage rule: there is no way to call this function that
    produces a number spanning the family.
    """
    if not operator or not isinstance(operator, str):
        raise MergedRateError(
            "witness_rate requires a single operator id. A rate across "
            "operators is not a meaningful quantity -- see the module "
            "docstring and writeup.md 6.5.")
    pool = controlled(records)
    denom, num = 0, 0
    for record in pool:
        rows = [r for r in record["rows"] if r["operator"] == operator]
        if not any(r["verdict"] in JUDGED for r in rows):
            continue  # nothing judgeable on this task for this operator
        denom += 1
        if any(r["verdict"] == "WITNESS" for r in rows):
            num += 1
    return {
        "operator": operator,
        "witness_tasks": num,
        "judged_tasks": denom,
        "rate": round(num / denom, 4) if denom else None,
        "wilson95": wilson(num, denom),
        "denominator": "tasks with >=1 judged case for this operator, "
                       "among tasks whose control passed",
    }


def anchor_availability(records):
    """Per operator: on how many controlled tasks did an in-scope anchor exist.

    This is the ceiling `writeup.md` 6.5 identifies -- coverage is bounded by
    anchor availability, not by refusals and not by oracle strength -- so it is
    reported beside every rate rather than left to be inferred.
    """
    pool = controlled(records)
    out = {}
    for record in pool:
        for row in record["rows"]:
            entry = out.setdefault(row["operator"],
                                   {"operator": row["operator"],
                                    "tasks_with_anchor": 0, "tasks": 0})
    for op in out:
        tasks = [r for r in pool if any(x["operator"] == op for x in r["rows"])]
        out[op]["tasks"] = len(tasks)
        out[op]["tasks_with_anchor"] = sum(
            1 for r in tasks
            if any(x["operator"] == op and x["verdict"] != "NOT_APPLICABLE"
                   for x in r["rows"]))
        out[op]["availability"] = (
            round(out[op]["tasks_with_anchor"] / len(tasks), 4) if tasks else None)
    return out


def verdict_counts(records):
    """Per operator, the full verdict distribution -- counts, never a rate.

    Counts are how the three non-loud operators are reported. They are not
    percentages because a percentage would invite averaging them with
    `symbol_rename`'s, which is the thing this module refuses to make possible.
    """
    out = {}
    for record in controlled(records):
        for row in record["rows"]:
            bucket = out.setdefault(row["operator"], {})
            bucket[row["verdict"]] = bucket.get(row["verdict"], 0) + 1
    return out


def loud_silent_partition(records):
    """How many judged cases came from a loud operator versus a silent one.

    The partition is the justification for THE NUMBER's scope, so it is measured
    from the rows rather than asserted from the operator table.
    """
    loud = {"judged": 0, "witnesses": 0, "operators": set()}
    silent = {"judged": 0, "witnesses": 0, "operators": set()}
    for record in controlled(records):
        for row in record["rows"]:
            bucket = loud if row["loud_failure"] else silent
            bucket["operators"].add(row["operator"])
            if row["verdict"] in JUDGED:
                bucket["judged"] += 1
            if row["verdict"] == "WITNESS":
                bucket["witnesses"] += 1
    for bucket in (loud, silent):
        bucket["operators"] = sorted(bucket["operators"])
    return {"loud": loud, "silent": silent}


def witness_split(records):
    """F2P-only versus P2P-involved, across every witness.

    A witness whose PASS_TO_PASS tests also fail is not evidence of form
    coupling; it is a transform that broke something, and the oracle should have
    caught it upstream. Reporting the split is what lets that be checked instead
    of assumed.
    """
    out = {"f2p_only": 0, "p2p_coupling": 0, "p2p_unattributed": 0,
           "unknown": 0, "witnesses": []}
    for record in records:
        for w in record["witnesses"]:
            side = w.get("witness_side") or "unknown"
            out[side] = out.get(side, 0) + 1
            out["witnesses"].append({
                "instance_id": record["instance_id"],
                "operator": w["operator"], "anchor": w["anchor"],
                "file": w["file"], "side": side,
                "f2p_fail": w.get("f2p_fail"), "p2p_fail": w.get("p2p_fail"),
                "p2p_coupled_tests": w.get("p2p_coupled_tests"),
            })
    return out


def coupling_types(records):
    """Which observable each witness perturbed -- a share by count, per operator.

    Deliberately keyed by operator as well as observable: a share over all
    witnesses regardless of operator would be a merged number wearing a
    different name.
    """
    out = {}
    for record in records:
        for w in record["witnesses"]:
            key = f"{w['operator']}::{w['observable']}"
            out[key] = out.get(key, 0) + 1
    return out


def _forbid_merged(report):
    """Refuse to write a report containing an unattributed rate.

    Anything shaped like a rate -- a mapping with a `rate` key -- must also name
    the `operator` it belongs to. Adding a family-wide percentage therefore
    requires deleting this function, which shows up in a diff.
    """
    def walk(node, path):
        if isinstance(node, dict):
            if "rate" in node and node.get("rate") is not None:
                if not node.get("operator"):
                    raise MergedRateError(
                        f"{path}: a rate with no operator. Operators are never "
                        "aggregated into a single percentage (writeup.md 6.5).")
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(report, "report")
    return report


def build(records):
    pool = controlled(records)
    the_number = witness_rate(records, THE_NUMBER_OPERATOR)
    the_number["justification"] = THE_NUMBER_JUSTIFICATION
    return _forbid_merged({
        "n_records": len(records),
        "n_controlled": len(pool),
        "n_control_failed": len(records) - len(pool),
        "control_failures": [
            {"instance_id": r["instance_id"],
             "reason": r["control"]["reason"], "error": r["error"]}
            for r in records if not r["control"]["passed"]
        ],
        "n_multi_target": sum(1 for r in pool if r["multi_target"]),
        # M3 samples single- and multi-file tasks as separate strata, so an
        # anomaly in the newer multi-file path stays visible instead of being
        # blended into the headline.
        "by_target_group": {
            group: {
                "operator": THE_NUMBER_OPERATOR,
                "tasks": len(sub),
                **{k: v for k, v in witness_rate(sub, THE_NUMBER_OPERATOR).items()
                   if k != "operator"},
            }
            for group, sub in (
                ("single_file", [r for r in records if not r["multi_target"]]),
                ("multi_file", [r for r in records if r["multi_target"]]),
            )
        },
        "the_number": the_number,
        "by_operator_rate": {
            op: witness_rate(records, op)
            for op in sorted({row["operator"] for r in pool for row in r["rows"]})
        },
        "by_operator_counts": verdict_counts(records),
        "anchor_availability": anchor_availability(records),
        "loud_silent": loud_silent_partition(records),
        "witness_split": witness_split(records),
        "coupling_types": coupling_types(records),
        # An unrecognised log shape is a REPORTED NUMBER, not a silent bucket.
        # CHANGES.md 18 was invisible precisely because unattributable failures
        # had nowhere to show up except as INVALID verdicts that looked like
        # findings.
        "unparsed_log_shapes": {
            "operator": THE_NUMBER_OPERATOR,
            "rows": sum(1 for r in records for x in r["rows"]
                        if (x.get("failure_analysis") or {}).get("unparsed")),
            "tasks": sorted({r["instance_id"] for r in records for x in r["rows"]
                             if (x.get("failure_analysis") or {}).get("unparsed")}),
        },
        "on_prime_hub_resolved": sum(
            1 for r in records if r["on_prime_hub"] is not None),
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "aggregate.json"))
    ap.add_argument("--results", default=RESULTS)
    args = ap.parse_args()

    records = load_records(args.results)
    if not records:
        raise SystemExit(f"no records in {args.results}")
    report = build(records)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    n, c = report["n_records"], report["n_controlled"]
    print(f"records {n}   controlled {c}   control failed "
          f"{report['n_control_failed']}\n")
    tn = report["the_number"]
    print(f"THE NUMBER ({tn['operator']} only)")
    print(f"  {tn['witness_tasks']}/{tn['judged_tasks']} tasks = "
          f"{'n/a' if tn['rate'] is None else format(tn['rate'], '.1%')}"
          + (f"   Wilson 95%: [{tn['wilson95'][0]:.1%}, {tn['wilson95'][1]:.1%}]"
             if tn.get ("wilson95") else ""))
    print(f"  denominator: {tn['denominator']}\n")
    print("Every operator, by count -- never merged into one percentage:")
    for op, counts in sorted(report["by_operator_counts"].items()):
        parts = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {op:20s} {parts}")
    print("\nAnchor availability (the coverage ceiling):")
    for op, a in sorted(report["anchor_availability"].items()):
        av = "n/a" if a["availability"] is None else format(a["availability"], ".1%")
        print(f"  {op:20s} {a['tasks_with_anchor']:>3}/{a['tasks']:<3} = {av}")
    ls = report["loud_silent"]
    print(f"\nLoud/silent: loud judged={ls['loud']['judged']} "
          f"witnesses={ls['loud']['witnesses']} {ls['loud']['operators']}")
    print(f"             silent judged={ls['silent']['judged']} "
          f"witnesses={ls['silent']['witnesses']} {ls['silent']['operators']}")
    print("\nBy target group (sampling strata, never blended):")
    for group, g in sorted(report["by_target_group"].items()):
        r = "n/a" if g["rate"] is None else format(g["rate"], ".1%")
        ci = (f"  Wilson 95% [{g['wilson95'][0]:.1%}, {g['wilson95'][1]:.1%}]"
              if g.get("wilson95") else "")
        print(f"  {group:12s} tasks={g['tasks']:<3} "
              f"witness {g['witness_tasks']}/{g['judged_tasks']} = {r}{ci}")
    up = report["unparsed_log_shapes"]
    if up["rows"]:
        print(f"\n!! UNPARSED LOG SHAPES: {up['rows']} row(s) across "
              f"{len(up['tasks'])} task(s) -- a runner the attribution does not "
              f"understand.\n   These are UNVALIDATED, never INVALID. "
              f"{', '.join(up['tasks'][:5])}")
    ws = report["witness_split"]
    print(f"\nWitness split: f2p_only={ws['f2p_only']} "
          f"p2p_coupling={ws['p2p_coupling']} "
          f"p2p_unattributed={ws['p2p_unattributed']} unknown={ws['unknown']}")
    print(f"\n  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
