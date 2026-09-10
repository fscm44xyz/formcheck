"""`recovery == 0` is classified only when all four checks hold.

A fourth outcome that has never refused anything is worth as little as a guard
that has never fired (`CHANGES.md` 19), so this pins both directions against the
real log from `django-14376` -- the task that produced the zero:

  positive   all four checks hold -> HELPER_COUPLED
  negative   each check broken on its own -> DEFECT, one at a time

The log is a fixture, not a container run. No Docker, no network, no model.

    ~/.venv-fc/bin/python repair/scan/test_classify_zero.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(ROOT, "scale"), os.path.join(ROOT, "repro")):
    if p not in sys.path:
        sys.path.insert(0, p)

from import_local_run import classify_zero  # noqa: E402

LOG = os.path.join(HERE, "fixtures", "django-14376_import_local.log")
SYMBOL = "DatabaseClient"

F2P = [
    "test_options_non_deprecated_keys_preferred (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_options_override_settings_proper_values (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_parameters (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
]
P2P = [
    "test_basic_params_specified_in_settings (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_can_connect_using_sockets (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_crash_password_does_not_leak (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_fails_with_keyerror_on_incomplete_config (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_options_charset (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
    "test_ssl_certificate_is_added (dbshell.test_mysql.MySqlDbshellCommandTestCase)",
]
SPEC = {"meta": {"FAIL_TO_PASS": F2P, "PASS_TO_PASS": P2P}}
FILES = ["./django/db/backends/mysql/client.py"] * 11
# 7 of the 9 graded ids were reported; two status lines were consumed by a
# subTest block (`CHANGES.md` 35). Both still have their own failure blocks,
# which is what check 4 reads -- and is why check 4 does not go through the
# status map.
REPORTED = [t for t in (F2P + P2P) if "override_settings_proper_values" not in t
            and not t.startswith("test_parameters")]
GOT = {"reported": REPORTED, "failing": F2P + P2P, "n_graded": 9}


def ev(files=None, verified=None, residue=None):
    files = FILES if files is None else files
    return {"files": files,
            "round_trip_verified": len(files) if verified is None else verified,
            "residue": residue or []}


def check(label, ok, expect_ok, checks, broken=None):
    status = "OK " if ok == expect_ok else "FAIL"
    print("  %s %-46s -> %s" % (status, label, "HELPER_COUPLED" if ok else "DEFECT"))
    if ok != expect_ok:
        print("       expected %s" % ("HELPER_COUPLED" if expect_ok else "DEFECT"))
        return False
    if broken is not None and checks[broken]:
        print("       expected check %r to be False" % broken)
        return False
    return True


def main():
    log = open(LOG, encoding="utf-8").read()
    good = 0

    print("positive -- the real django-14376 measurement:")
    ok, checks, why = classify_zero(SYMBOL, ev(), GOT, log, SPEC)
    good += check("all four checks hold", ok, True, checks)
    for k, v in sorted(checks.items()):
        print("       %-42s %s" % (k, v))
    if not ok:
        print("       why: %s" % why)

    print("\nnegative -- each check broken on its own:")
    cases = [
        ("round trip failed on one renamed file",
         (SYMBOL, ev(verified=10), GOT, log, SPEC), "round_trip_on_every_renamed_file"),
        ("residue left in a production file",
         (SYMBOL, ev(residue=["./django/db/backends/base/client.py"]), GOT, log, SPEC),
         "residue_empty"),
        ("nothing ran -- no graded id reported",
         (SYMBOL, ev(), dict(GOT, reported=[]), log, SPEC), "module_loaded"),
        ("a graded test's failure does not name the symbol",
         (SYMBOL, ev(), GOT, log.replace("cannot import name 'DatabaseClient'",
                                         "AssertionError: 1 != 2"), SPEC),
         "every_graded_test_reaches_the_symbol"),
        ("no renamed file at all",
         (SYMBOL, ev(files=[], verified=0), GOT, log, SPEC),
         "round_trip_on_every_renamed_file"),
    ]
    for label, args, broken in cases:
        ok, checks, _why = classify_zero(*args)
        good += check(label, ok, False, checks, broken)

    total = 1 + len(cases)
    print("\n%d of %d cases agree." % (good, total))
    return 0 if good == total else 1


if __name__ == "__main__":
    sys.exit(main())
