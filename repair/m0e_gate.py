"""repair-M0e gate: `django__django-11433`. Config over `repair/gate.py`.

Second django task, picked by the criterion fixed before M0d: import shape,
single-file gold, lexicographic instance id.

`construct_instance` is not public -- absent from `django/forms/models.py`'s
`__all__` and not re-exported from `django.forms`. The coupled test is a unit
test of it:

    form = modelform_factory(Person, fields="__all__")({'name': 'John Doe'})
    instance = construct_instance(form, Person(), fields=())
    self.assertEqual(instance.name, '')

`bug_fieldfilter` is the mutant that decides this task. It inverts the `fields`
filter inside `construct_instance` -- the exact behaviour that test exists to
pin. The public route reaches the same ASSERTION by a different MECHANISM
(a form with `fields=()` has no fields, so `cleaned_data` is empty and the filter
never runs), so it is predicted not to catch it. C3 adjudicates.

    ~/.venv-fc/bin/python repair/m0e_gate.py
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gate import Gate  # noqa: E402

TARGET = "django/forms/models.py"

GOLD_COND = """        if (
            f.has_default() and
            form[f.name].field.widget.value_omitted_from_data(form.data, form.files, form.add_prefix(f.name)) and
            cleaned_data.get(f.name) in form[f.name].field.empty_values
        ):"""

MUTANTS = {
    "bug_revert": {
        "old": GOLD_COND,
        "new": ("        if (f.has_default() and\n"
                "                form[f.name].field.widget.value_omitted_from_data("
                "form.data, form.files, form.add_prefix(f.name))):"),
        "effect": "the pre-issue condition: the default wins over a non-empty cleaned value",
    },
    "bug_invert": {
        "old": "            cleaned_data.get(f.name) in form[f.name].field.empty_values",
        "new": "            cleaned_data.get(f.name) not in form[f.name].field.empty_values",
        "effect": "the added condition is negated",
    },
    # `if fields is not None and f.name not in fields:` occurs THREE times in
    # this file -- in `construct_instance`, `fields_for_model` and
    # `_get_foreign_key`-adjacent code. The gate's anchor guard refused the bare
    # form; the anchor below carries the two preceding lines, which are unique to
    # `construct_instance`.
    "bug_fieldfilter": {
        "old": ("                or f.name not in cleaned_data:\n"
                "            continue\n"
                "        if fields is not None and f.name not in fields:"),
        "new": ("                or f.name not in cleaned_data:\n"
                "            continue\n"
                "        if fields is not None and f.name in fields:"),
        "effect": "the `fields` argument filter is inverted -- what the coupled test pins",
    },
}

GATE = Gate(
    instance_id="django__django-11433",
    image="swebench/sweb.eval.x86_64.django_1776_django-11433:latest",
    container="repair-m0e-gate",
    target=TARGET,
    # Every production file naming `construct_instance`; `gate.build` verifies
    # no production residue is left after the rename.
    rename=("construct_instance", "construct_instance__renamed", [TARGET]),
    mutants=MUTANTS,
    test_variants={
        "original": None,
        "import_local": os.path.join(
            HERE, "overlay_importlocal_django_11433.diff"),
        "repaired": os.path.join(HERE, "overlay_repair_django_11433.diff"),
    },
    python="/opt/miniconda3/envs/testbed/bin/python",
    out=os.path.join(HERE, "m0e_gate_result.json"),
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-image", action="store_true")
    sys.exit(GATE.run(keep_image=ap.parse_args().keep_image))
