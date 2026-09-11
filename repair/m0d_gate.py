"""repair-M0d gate: `django__django-11179`. Config over `repair/gate.py`.

The question this gate exists to answer is not "does the repair pass" but
"is a repair available at all". `Collector` is not public -- no `__all__` in
`django/db/models/deletion.py`, not re-exported from `django.db.models` -- and
the coupled line is a PRECONDITION assertion (`can_fast_delete(u)` is true),
not the contract assertion (`u.pk is None`).

`bug_nofast` is the mutant that decides it. It forces `can_fast_delete` to
return False, which is exactly the regression the deleted precondition existed
to catch. If the repaired test still catches it, the precondition had a
behavioural proxy; if it survives, removing the precondition cost real detection
and the repair is a hollowing-out, not a repair.

    ~/.venv-fc/bin/python repair/m0d_gate.py
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gate import Gate  # noqa: E402

TARGET = "django/db/models/deletion.py"

# `setattr(instance, model._meta.pk.attname, None)` occurs TWICE in this file --
# the gold adds it to the fast path (line 280) and the slow path has always had
# it (line 327). The gate's anchor guard caught that on the first run and
# refused, which is the guard working: an edit applied to the wrong one of two
# identical lines would have produced a "mutant" that changes a code path the
# test never reaches. The anchors below carry the following line to disambiguate.
FAST_PATH = ("                setattr(instance, model._meta.pk.attname, None)\n"
             "                return count, {model._meta.label: count}")

MUTANTS = {
    "bug_revert": {
        "old": FAST_PATH,
        "new": "                return count, {model._meta.label: count}",
        "effect": "the pre-issue behaviour: the fast path leaves the pk set",
    },
    "bug_zero": {
        "old": FAST_PATH,
        "new": ("                setattr(instance, model._meta.pk.attname, 0)\n"
                "                return count, {model._meta.label: count}"),
        "effect": "the pk is cleared to 0 rather than None",
    },
    "bug_nofast": {
        "old": "    def can_fast_delete(self, objs, from_field=None):",
        "new": "    def can_fast_delete(self, objs, from_field=None):\n        return False",
        "effect": "fast deletion disabled -- the path the issue is about is never taken",
    },
}

GATE = Gate(
    instance_id="django__django-11179",
    image="swebench/sweb.eval.x86_64.django_1776_django-11179:latest",
    container="repair-m0d-gate",
    target=TARGET,
    # Every production file that references `Collector`, which is what
    # `symbol_rename` rewrites. Listing only `deletion.py` broke django itself
    # rather than performing an alpha-rename -- see the guard in `gate.build`.
    rename=("Collector", "Collector__renamed", [
        TARGET,
        "django/db/models/base.py",
        "django/db/models/query.py",
        "django/contrib/admin/utils.py",
        "django/contrib/contenttypes/management/commands/remove_stale_contenttypes.py",
    ]),
    mutants=MUTANTS,
    test_variants={
        "original": None,
        "import_local": os.path.join(
            HERE, "overlay_importlocal_django_11179.diff"),
        "repaired": os.path.join(HERE, "overlay_repair_django_11179.diff"),
    },
    python="/opt/miniconda3/envs/testbed/bin/python",
    out=os.path.join(HERE, "m0d_gate_result.json"),
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true")
    sys.exit(GATE.run(keep_image=ap.parse_args().keep_image))
