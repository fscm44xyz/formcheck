"""Phase 0 verdict: grade the mechanical witness and decide, binary.

Runs under .venv (swebench + shim). Reads log_f0_witness.txt and f0_result.json
produced by f0_witness.py, and the M0 baseline logs for comparison.

The witness is REAL iff:
  (a) the transformed gold satisfies the issue contract (oracle: both markers)
  (b) the transformed gold scores 0.0 on the graded tests
  (c) the failure is the graded F2P test itself, not collateral damage --
      otherwise the transform broke something else and (b) proves nothing.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from m4_grader import grade_file

META = json.load(open(os.path.join(HERE, "meta.json")))


def row(label, path):
    r = grade_file(os.path.join(HERE, path), META)
    print(f"  {label:34s} reward={r['reward']}  "
          f"F2P {r['f2p_pass']}/{r['f2p_pass'] + r['f2p_fail']}  "
          f"P2P {r['p2p_pass']}/{r['p2p_pass'] + r['p2p_fail']}")
    return r


def main():
    result = json.load(open(os.path.join(HERE, "f0_result.json")))
    markers = result["oracle_markers"]

    print("Phase 0 verdict -- mechanical witness on pytest-dev__pytest-10356\n")
    print("Reward table (real swebench grading path):")
    gold = row("gold patch (control)", "log_gold.txt")
    alt = row("hand-written alt (July, control)", "log_alt.txt")
    mech = row("gold + kwonly_specialize (NEW)", "log_f0_witness.txt")

    a = set(markers) == {"foo", "bar"}
    b = mech["reward"] == 0.0
    c = mech["f2p_failing"] == META["FAIL_TO_PASS"] if isinstance(
        META["FAIL_TO_PASS"], list) else sorted(mech["f2p_failing"]) == sorted(
        eval(META["FAIL_TO_PASS"]))
    clean = mech["p2p_fail"] == 0

    print("\nConditions:")
    print(f"  (a) contract satisfied (oracle both markers) : {a}   markers={markers}")
    print(f"  (b) graded reward is 0.0                     : {b}")
    print(f"  (c) the failure IS the graded F2P test       : {c}   "
          f"failing F2P={mech['f2p_failing']}")
    print(f"  (c') no collateral P2P damage                : {clean}   "
          f"P2P failures={mech['p2p_fail']}")

    print("\n" + "=" * 74)
    if a and b and c and clean:
        print("VERDICT: the mechanical witness is REAL.")
        print("  A behaviour-preserving transform of the gold patch, generated with no")
        print("  LLM and no hand-authored anchor, reproduces July's false negative:")
        print("  it satisfies the issue's observable contract and still scores 0.0,")
        print("  failing exactly the graded test and nothing else.")
        print("  => D4 has an executable basis. Proceed to Phase 1.")
        return 0
    print("VERDICT: the mechanical witness did NOT reproduce.")
    print("  D4 dies here, for 0 EUR. Nothing further is built.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
