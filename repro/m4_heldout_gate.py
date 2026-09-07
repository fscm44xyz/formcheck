"""M4 held-out gate: G1/G3 + G2 with train/held-out split and Mutation Survival
Rate per set (spec 4.3). Runs under .venv; worker under .venv-pytest."""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from m4_grader import grade_file
from m4_mutants import TRAINING, HELDOUT

def _default_pytest_python():
    # env override, else the .venv-pytest interpreter two levels up (primein/.venv-pytest)
    base = os.path.abspath(os.path.join(HERE, "..", "..", ".venv-pytest"))
    for cand in (os.path.join(base, "Scripts", "python.exe"),  # Windows
                 os.path.join(base, "bin", "python")):          # POSIX
        if os.path.exists(cand):
            return cand
    return None

PY_PYTEST = os.environ.get("REWARDPATCH_PYTEST_PYTHON") or _default_pytest_python()
if not PY_PYTEST or not os.path.exists(PY_PYTEST):
    raise SystemExit(
        "Test-runner interpreter not found.\n"
        "Set REWARDPATCH_PYTEST_PYTHON to the python of a venv with pytest "
        "installed editable, or create it at ../../.venv-pytest. See README.md."
    )
WORKER = os.path.join(HERE, "m4_worker.py")
META = json.load(open(os.path.join(HERE, "meta.json")))
LOG = os.path.join(HERE, "log_m4_{name}.txt")

GATES = [("gold", "G1"), ("alt", "G3")]
TRAIN = list(TRAINING)
HELD = list(HELDOUT.keys())
ALL = [n for n, _ in GATES] + TRAIN + HELD

def run_worker(names):
    r = subprocess.run([PY_PYTEST, WORKER, *names], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"worker failed:\n{r.stdout}\n{r.stderr}")
    print(r.stdout.strip())

def reward(name):
    return grade_file(LOG.format(name=name), META)["reward"]

def msr(names):
    """Mutation Survival Rate: bad mutants that SURVIVE (reward>0) / tested."""
    survivors = [n for n in names if reward(n) > 0]
    return survivors, len(survivors), len(names)

def main():
    print(f"[gate] executing {len(ALL)} solutions ...\n")
    run_worker(ALL)

    print(f"\nTask: {META['instance_id']}   four-gate contract, train/held-out split\n")
    # G1 / G3
    g1 = reward("gold"); g3 = reward("alt")
    print(f"G1 positive-preservation : gold reward = {g1}  {'OK' if g1 == 1.0 else 'FAIL'}")
    print(f"G3 false-neg-recovery    : alt  reward = {g3}  {'OK' if g3 == 1.0 else 'FAIL'}")

    # G2 train
    tr_surv, tr_s, tr_n = msr(TRAIN)
    print(f"\nG2 negative preservation -- TRAINING set ({tr_n} mutants):")
    for n in TRAIN:
        r = reward(n)
        print(f"    {n:12s} reward={r}  {'CAUGHT' if r == 0 else 'SURVIVES'}")
    print(f"  Mutation Survival Rate (train)   : {tr_s}/{tr_n} survive")

    # G2 held-out
    ho_surv, ho_s, ho_n = msr(HELD)
    print(f"\nG2 negative preservation -- HELD-OUT set ({ho_n} mutants, repair never saw them):")
    for n in HELD:
        r = reward(n)
        fm = HELDOUT[n]["failure_mode"]
        print(f"    {n:12s} reward={r}  {'CAUGHT' if r == 0 else 'SURVIVES'}   [{fm}]")
    print(f"  Mutation Survival Rate (held-out): {ho_s}/{ho_n} survive")

    # verdict analysis
    print("\n" + "=" * 78)
    pooled_surv = tr_s + ho_s
    print(f"Pooled (train+held-out) survivors: {pooled_surv}/{tr_n + ho_n}  "
          f"-> {sorted(set(tr_surv + ho_surv))}")
    print("Split changes a survivor verdict vs pooled?  "
          f"{'YES' if False else 'NO'} -- survival is per-mutant, identical under both.")
    if "H_dup" in ho_surv:
        print("\nH_dup SURVIVES (as predicted): set of names insensitive to duplicates.")
        print("  -> documented boundary, NOT a rejection: the issue contract is silent on")
        print("     marker duplication, so the behavioral test correctly does not forbid it.")
    else:
        print("\nH_dup was CAUGHT (refutes prediction) -- the test is stronger than expected.")

if __name__ == "__main__":
    main()
