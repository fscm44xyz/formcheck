"""Phase 2 gate: grade every transform case and classify it. Runs under .venv.

The classification is deliberately conservative, and the two conservative
outcomes are the ones that matter:

  WITNESS      contract satisfied, graded reward 0.0, the failure IS the graded
               F2P test and nothing else. The task's reward rejects a correct
               solution, exhibited mechanically.
  CLEAN        contract satisfied, graded reward 1.0. The test tolerates this
               transform; no coupling exposed by it.
  INVALID      the oracle says the contract BROKE. The transform was not
               behaviour-preserving. Discarded, and counted -- the invalid rate
               is the honest measure of how far "preserves behaviour" can be
               trusted.
  UNVALIDATED  the transform can perturb an observable class the oracle cannot
               see, so the oracle's pass is uninformative. Never a witness.
               An oracle that cannot disconfirm a transform must not confirm it.
  BROKEN_OTHER contract satisfied and reward 0.0, but P2P tests failed too --
               the transform broke something the oracle does not watch. Not a
               witness; a weaker instance of UNVALIDATED.
  REFUSED      a precondition failed. Routed, not forced.
  ROUTED       tier BORDER: the issue names the object. G4 says contract.
  NOT_APPLICABLE  the operator has no anchor in the gold-touched region.
"""
import os
import sys
import json
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from m4_grader import grade_file

META = json.load(open(os.path.join(HERE, "meta.json")))
F2P = META["FAIL_TO_PASS"] if isinstance(META["FAIL_TO_PASS"], list) else eval(
    META["FAIL_TO_PASS"])
CONTRACT = {"foo", "bar"}


def classify(case, covers):
    if case["outcome"] != "RAN":
        return case["outcome"], None, {}
    markers = set(case["oracle_markers"])
    r = grade_file(os.path.join(HERE, f"log_f2_{case['name']}.txt"), META)
    if markers != CONTRACT:
        return "INVALID", r, {"why": f"oracle markers {sorted(markers)} != contract"}
    if not covers.get(case["report"]["observable"], False):
        return "UNVALIDATED", r, {
            "why": "the oracle does not observe "
                   f"\"{case['report']['observable']}\", so its pass cannot "
                   "confirm equivalence for this operator"}
    if r["reward"] == 1.0:
        return "CLEAN", r, {}
    if r["p2p_fail"] > 0:
        return "BROKEN_OTHER", r, {
            "why": f"{r['p2p_fail']} P2P test(s) also failed"}
    if sorted(r["f2p_failing"]) != sorted(F2P):
        return "BROKEN_OTHER", r, {"why": "failing F2P set does not match the task's"}
    return "WITNESS", r, {}


def _column(text, width=44):
    """Fixed-width label column, cut at a word boundary. A note truncated
    mid-token reads as a rendering bug rather than as an elision."""
    if len(text) <= width:
        return text
    cut = text[:width].rsplit(" ", 1)[0] or text[:width]
    return cut.rstrip(" ([,") + " ..."


def _detail(text):
    """A wrapped, hanging-indented explanation line under a verdict row."""
    return textwrap.fill(text, width=96,
                         initial_indent="                 -> ",
                         subsequent_indent="                    ")


def main():
    data = json.load(open(os.path.join(HERE, "f2_cases.json")))
    covers = data["oracle_covers"]
    print("Phase 2 verdict -- equivalence-preserving family on "
          f"{META['instance_id']}\n")
    print(f"  oracle observes: {data['oracle_observes']}\n")

    rows, counts = [], {}
    for case in data["cases"]:
        verdict, r, extra = classify(case, covers)
        counts[verdict] = counts.get(verdict, 0) + 1
        tier = case.get("tier", "-")
        label = _column(case.get("anchor", case.get("note", "")))
        reward = "-" if r is None else r["reward"]
        print(f"  {verdict:14s} {case['operator']:20s} {str(tier):6s} "
              f"reward={reward!s:5s} {label}")
        if extra.get("why"):
            print(_detail(extra["why"]))
        if case.get("reason"):
            # Print the reason in FULL. It is the audit trail for a refusal, and
            # the deciding clause tends to sit at the end: which file the name
            # was reached from, and whether that reach is an `__all__` entry.
            # Truncating lost exactly that clause. Wrapped, not cut.
            print(_detail(case["reason"]))
        rows.append({**case, "verdict": verdict,
                     "grading": r, "explanation": extra.get("why")})

    ran = [x for x in rows if x["outcome"] == "RAN"]
    unjudgeable = [x for x in rows if x["verdict"] == "UNVALIDATED"]
    judged = [x for x in ran if x["verdict"] != "UNVALIDATED"]
    invalid = counts.get("INVALID", 0)
    print("\n" + "=" * 78)
    print("Counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if judged:
        print(f"\nInvalid-transform rate, among transforms this oracle can JUDGE: "
              f"{invalid}/{len(judged)} ({invalid / len(judged):.0%}).")
        print("  Read this against its own interest, not as a clean bill of health:")
        print(f"  * {len(unjudgeable)} further transform(s) were applied and could not "
              "be judged at all,")
        print("    because they perturb an observable the oracle does not watch. "
              "The rate\n    excludes them; it does not clear them.")
        print("  * The rate is bounded by the oracle's reach, not by the operators' "
              "quality.\n    A stronger oracle finds MORE invalid transforms, never "
              "fewer. Here the oracle\n    watches a SET of marker names, so it is "
              "blind to order and to duplication\n    (the same blindness recorded "
              "in July as the H_dup boundary).")
        print("  * One task, one oracle. This is a mechanism demonstration, not a "
              "rate.")
    witnesses = [x for x in rows if x["verdict"] == "WITNESS"]
    print(f"\nMechanical witnesses: {len(witnesses)}")
    for w in witnesses:
        print(f"  - {w['operator']} on {w['anchor']}  (tier {w['tier']})")
    json.dump(rows, open(os.path.join(HERE, "f2_verdicts.json"), "w"), indent=2)
    print("\n-> f2_verdicts.json")


if __name__ == "__main__":
    main()
