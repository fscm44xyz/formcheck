"""Phase 2 overlay: emit the transform family's evidence in the overlay format.

One directory per task, alongside the July repair overlay. Upstream is never
modified. Each applied transform contributes its own patch.diff (the transform,
gold -> transformed), its equivalence argument, its tier, its checked
preconditions, and its graded outcome.

Writes ./overlay_f2/<instance_id>@formcheck-1/.
"""
import os
import sys
import json
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

META = json.load(open(os.path.join(HERE, "meta.json")))
OUT = os.path.join(HERE, "overlay_f2", f"{META['instance_id']}@formcheck-1")


def main():
    rows = json.load(open(os.path.join(HERE, "f2_verdicts.json")))
    cases = json.load(open(os.path.join(HERE, "f2_cases.json")))
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "transforms"), exist_ok=True)

    witnesses, entries = [], []
    for row in rows:
        entry = {"operator": row["operator"], "tier": row.get("tier"),
                 "anchor": row.get("anchor"), "verdict": row["verdict"],
                 "explanation": row.get("explanation")}
        if row.get("report"):
            rep = row["report"]
            entry.update({
                "equivalence_argument": rep["argument"],
                "breaks_if": rep["breaks_if"],
                "observable_perturbed": rep["observable"],
                "preconditions_checked": rep["preconditions"],
                "evidence": rep.get("evidence"),
                "detail": rep.get("detail"),
            })
        if row.get("grading"):
            g = row["grading"]
            entry["graded"] = {"reward": g["reward"],
                               "f2p": f"{g['f2p_pass']}/{g['f2p_pass'] + g['f2p_fail']}",
                               "p2p": f"{g['p2p_pass']}/{g['p2p_pass'] + g['p2p_fail']}",
                               "f2p_failing": g["f2p_failing"]}
        if row.get("oracle_markers") is not None:
            entry["oracle_markers"] = row["oracle_markers"]
        if row.get("name"):
            src = os.path.join(HERE, f"f2_{row['name']}.diff")
            if os.path.exists(src):
                dst = f"transforms/{row['name']}.diff"
                shutil.copyfile(src, os.path.join(OUT, dst))
                entry["patch"] = dst
            log = os.path.join(HERE, f"log_f2_{row['name']}.txt")
            if os.path.exists(log):
                dst = f"transforms/{row['name']}.log.txt"
                shutil.copyfile(log, os.path.join(OUT, dst))
                entry["log"] = dst
        entries.append(entry)
        if row["verdict"] == "WITNESS":
            witnesses.append(entry)

    evidence = {
        "instance_id": META["instance_id"],
        "kind": "form-coupling check by equivalence-preserving transformation",
        "issue": "pytest-dev/pytest#7792 (issue.txt) -- a test inheriting from two "
                 "marked base classes must carry BOTH marks",
        "oracle": {
            "observes": cases["oracle_observes"],
            "covers": cases["oracle_covers"],
            "limitation": "a SET of marker names is blind to element ORDER and to "
                          "DUPLICATION; transforms perturbing those cannot be "
                          "validated by it and are reported UNVALIDATED, never as "
                          "witnesses",
        },
        "scope": {
            "anchors_restricted_to": "module-level symbols touched by the gold patch",
            "touched_symbols": cases["touched_symbols"],
        },
        "result": {
            "witnesses": len(witnesses),
            "verdict_counts": {v: sum(1 for e in entries if e["verdict"] == v)
                               for v in sorted({e["verdict"] for e in entries})},
            "conclusion": (
                "the task's graded reward rejects at least one behaviour-preserving "
                "variant of its own gold patch" if witnesses else
                "no form coupling exhibited by this operator family"),
        },
        "language": {
            "claim_strength": "ARGUED equivalence, regression-checked against one "
                              "oracle. Not a proof, and not called one.",
            "banned": ["provably safe", "proof"],
        },
        "transforms": entries,
    }
    json.dump(evidence, open(os.path.join(OUT, "evidence.json"), "w"), indent=2)
    print(f"wrote {OUT}")
    print(f"  evidence.json  ({len(entries)} transform entries, "
          f"{len(witnesses)} witness(es))")
    print(f"  transforms/    ({len(os.listdir(os.path.join(OUT, 'transforms')))} files)")


if __name__ == "__main__":
    main()
