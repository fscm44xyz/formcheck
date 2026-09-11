"""repair-M0b gate: `pydata__xarray-4966`. Config over `repair/gate.py`.

The repair moves the two coupled tests off the internal `UnsignedIntegerCoder`
and onto `xr.decode_cf`, which `xarray/__init__.py` exports.

    ~/.venv-fc/bin/python repair/m0b_gate.py
    ~/.venv-fc/bin/python repair/m0b_gate.py --keep-image
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gate import Gate  # noqa: E402

TARGET = "xarray/coding/variables.py"

# BEHAVIOURAL mutants: expression edits inside the gold's own added branch. No
# identifier, import or class name is touched, so a failure is a failure of
# behaviour and not a re-measurement of the coupling being repaired.
MUTANTS = {
    "bug_noop": {
        "old": "                    data = lazy_elemwise_func(data, transform, signed_dtype)",
        "new": "                    data = data",
        "effect": "the signed view is computed and then never applied",
    },
    "bug_width": {
        "old": '                    signed_dtype = np.dtype("i%s" % data.dtype.itemsize)',
        "new": '                    signed_dtype = np.dtype("i1")',
        "effect": "converts to int8 regardless of width -- correct only at bits=1",
    },
    "bug_condflip": {
        "old": '                if unsigned == "false":',
        "new": '                if unsigned == "true":',
        "effect": "the added branch never fires for the case the issue describes",
    },
}

GATE = Gate(
    instance_id="pydata__xarray-4966",
    image="swebench/sweb.eval.x86_64.pydata_1776_xarray-4966:latest",
    container="repair-m0b-gate",
    target=TARGET,
    rename=("UnsignedIntegerCoder", "UnsignedIntegerCoder__renamed",
            [TARGET, "xarray/conventions.py"]),
    mutants=MUTANTS,
    test_variants={
        "original": None,
        "repaired": os.path.join(HERE, "overlay_repair_xarray_4966.diff"),
    },
    python="/opt/miniconda3/envs/testbed/bin/python",
    out=os.path.join(HERE, "m0b_gate_result.json"),
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true")
    sys.exit(GATE.run(keep_image=ap.parse_args().keep_image))
