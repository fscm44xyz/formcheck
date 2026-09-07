"""Emit the versioned overlay (spec 4.4). Never modifies the upstream grader;
writes a self-contained, provenance-preserving overlay directory. Runs under .venv."""
import os, sys, json, difflib
sys.path.insert(0, os.path.dirname(__file__))
from m4_grader import grade_file
from m4_mutants import HELDOUT, TRAINING, OPERATORS
import m1_run

HERE = os.path.dirname(__file__)
META = json.load(open(os.path.join(HERE, "meta.json")))
LOG = os.path.join(HERE, "log_m4_{name}.txt")
OUT = os.path.join(HERE, "overlay", f"{META['instance_id']}@rewardpatch-1")
MUT = os.path.join(OUT, "mutants")
os.makedirs(MUT, exist_ok=True)

TEST_PATH = "testing/test_mark.py"

ORIGINAL_TEST = '''def test_mark_mro() -> None:
    xfail = pytest.mark.xfail

    @xfail("a")
    class A:
        pass

    @xfail("b")
    class B:
        pass

    @xfail("c")
    class C(A, B):
        pass

    from _pytest.mark.structures import get_unpacked_marks

    all_marks = get_unpacked_marks(C)

    assert all_marks == [xfail("c").mark, xfail("a").mark, xfail("b").mark]

    assert get_unpacked_marks(C, consider_mro=False) == [xfail("c").mark]
'''

def rew(name):
    return grade_file(LOG.format(name=name), META)["reward"]

# ---- patch.diff : the repaired-test change (form -> behavioral) ----
diff = difflib.unified_diff(
    ORIGINAL_TEST.splitlines(keepends=True),
    m1_run.REPAIRED_TEST.splitlines(keepends=True),
    fromfile=f"a/{TEST_PATH}", tofile=f"b/{TEST_PATH}",
)
open(os.path.join(OUT, "patch.diff"), "w", encoding="utf-8").write("".join(diff))

# ---- evidence.json : G4 contract grounding (structured, from M1 4.3 block) ----
evidence = {
    "instance_id": META["instance_id"],
    "issue_contract": "a test inheriting from two marked base classes must carry "
                      "the marks of BOTH (MRO considered), not one shadowing the other",
    "form_not_in_contract": [
        "private import from _pytest.mark.structures",
        "invented keyword get_unpacked_marks(..., consider_mro=False)",
        "exact list order [c, a, b]",
    ],
    "behavior_asserted": "both base-class marks present on the test, via public "
                         "item.iter_markers(); asserted as a set of names",
    "verdict": "private symbol + invented keyword + exact order are implementation-"
               "coupled -> replaced with observable presence check; presence stays asserted",
    "boundary": "set-equality does not forbid marker DUPLICATION; the issue is silent "
                "on uniqueness, so this repair does NOT distinguish duplicated markers. "
                "Documented, not claimed as covered (see mutants/H_dup).",
    "grounding_mode": "manual (G4 auto-extraction is M3, not M4)",
}
json.dump(evidence, open(os.path.join(OUT, "evidence.json"), "w"), indent=2)

# ---- mutants/ : training + held-out, with verdicts ----
def verdict(name):
    r = rew(name)
    return {"reward": r, "verdict": "caught" if r == 0 else "survives"}

mut_index = {"operators": OPERATORS, "training": {}, "held_out": {}}
for n in TRAINING:
    v = verdict(n)
    mut_index["training"][n] = v
    json.dump({"name": n, "bucket": "training", "source": "hand-authored (M1)", **v},
              open(os.path.join(MUT, f"{n}.json"), "w"), indent=2)
for n, spec in HELDOUT.items():
    v = verdict(n)
    mut_index["held_out"][n] = {**v, "failure_mode": spec["failure_mode"]}
    json.dump({"name": n, "bucket": "held_out", "operator": spec["operator"],
               "transform": {"old": spec["old"], "new": spec["new"]},
               "failure_mode": spec["failure_mode"], **v},
              open(os.path.join(MUT, f"{n}.json"), "w"), indent=2)
json.dump(mut_index, open(os.path.join(MUT, "index.json"), "w"), indent=2)

# ---- validation.json : G1-G4 + MSR per set ----
tr_surv = [n for n in TRAINING if rew(n) > 0]
ho_surv = [n for n in HELDOUT if rew(n) > 0]
validation = {
    "instance_id": META["instance_id"],
    "grader": "verifiers SWEBenchTaskSet._calculate_reward (real)",
    "G1_positive_preservation": {"gold_reward": rew("gold"), "pass": rew("gold") == 1.0},
    "G3_false_negative_recovery": {"alt_reward": rew("alt"), "pass": rew("alt") == 1.0},
    "G2_negative_preservation": {
        "training":  {"survivors": tr_surv, "survival_rate": f"{len(tr_surv)}/{len(TRAINING)}"},
        "held_out":  {"survivors": ho_surv, "survival_rate": f"{len(ho_surv)}/{len(HELDOUT)}"},
    },
    "G4_contract_grounding": "manual, see evidence.json",
    "held_out_finding": {
        "H_dup_survives": "H_dup" in ho_surv,
        "note": "H_dup survival is a documented contract boundary (duplication not "
                "specified by the issue), not a rejection. Split changes no accept "
                "verdict vs pooled: survival is per-mutant.",
    },
    "upstream_untouched": True,
}
json.dump(validation, open(os.path.join(OUT, "validation.json"), "w"), indent=2)

# ---- print tree ----
print(f"overlay emitted (upstream grader NOT modified):\n")
print(f"{META['instance_id']}@rewardpatch-1/")
for root, dirs, files in os.walk(OUT):
    for f in sorted(files):
        rel = os.path.relpath(os.path.join(root, f), OUT)
        sz = os.path.getsize(os.path.join(root, f))
        print(f"    {rel:28s} {sz:5d} B")
print("\nvalidation.json:")
print(json.dumps(validation, indent=2))
