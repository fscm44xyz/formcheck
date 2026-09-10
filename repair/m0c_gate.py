"""repair-M0c gate: `astropy__astropy-12907`. Config over `repair/gate.py`.

Three test variants, not two, because this task's coupling splits in a way
xarray's did not:

    original      the shipped test module. One module-level `from ... import`
                  names `_cstack`, so renaming it stops the module importing and
                  all 15 graded tests fail -- 14 of which never use the symbol.
    import_local  the DIAGNOSTIC. `_cstack` is dropped from the module import and
                  imported inside the one test that uses it. This isolates the
                  collateral damage from the intrinsic coupling: it says how many
                  of the 15 failures were only ever about the import line.
    repaired      the actual repair. `test_cstack` reaches the same behaviour
                  through `separability_matrix`, the module's exported API.

`import_local` is expected to FAIL C1 and is kept anyway: it is the measurement
that distinguishes "the import took the module down" from "this test is about
the renamed symbol", and those are different findings.

    ~/.venv-fc/bin/python repair/m0c_gate.py
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gate import Gate  # noqa: E402

TARGET = "astropy/modeling/separable.py"

MUTANTS = {
    "bug_revert": {
        "old": "        cright[-right.shape[0]:, -right.shape[1]:] = right",
        "new": "        cright[-right.shape[0]:, -right.shape[1]:] = 1",
        "effect": "the pre-issue behaviour: the right block is filled with ones",
    },
    "bug_leftblock": {
        "old": "        cleft[: left.shape[0], : left.shape[1]] = left",
        "new": "        cleft[: left.shape[0], : left.shape[1]] = 1",
        "effect": "the mirror bug on the left operand's block",
    },
    "bug_stackorder": {
        "old": "    return np.hstack([cleft, cright])",
        "new": "    return np.hstack([cright, cleft])",
        "effect": "operand columns emitted in the wrong order",
    },
}

GATE = Gate(
    instance_id="astropy__astropy-12907",
    image="swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest",
    container="repair-m0c-gate",
    target=TARGET,
    # `_cstack` is defined and referenced only inside separable.py.
    rename=("_cstack", "_cstack__renamed", [TARGET]),
    mutants=MUTANTS,
    test_variants={
        "original": None,
        "import_local": os.path.join(
            HERE, "overlay_importlocal_astropy_12907.diff"),
        "repaired": os.path.join(HERE, "overlay_repair_astropy_12907.diff"),
    },
    python="/opt/miniconda3/envs/testbed/bin/python",
    out=os.path.join(HERE, "m0c_gate_result.json"),
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true")
    sys.exit(GATE.run(keep_image=ap.parse_args().keep_image))
