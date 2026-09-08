# M1's 5-task pilot, kept because M2 reused `scale/records/`

`scale/run.py` writes to `scale/records/`, and M2 overwrote M1's pilot there.
These are the pilot's own records, restored so both evidence sets exist in the
tree rather than only in history (`79694c9`).

Sampled from `scale/eligible.jsonl` with seed 0: django-13810,
scikit-learn-14894, sphinx-9591, sympy-13091, sympy-17139. 5/5 controls passed
across four different test runners, 0 witnesses. `sympy-13091` is the 21-target
outlier that exercised the multi-target widening.

`aggregate.py --results scale/records_m1_pilot` reads them.

NOTE: these predate `CHANGES.md` 13. Their `INVALID` rows are subject to the
same lost P2P partition, so any `INVALID` here may be a WITNESS.
