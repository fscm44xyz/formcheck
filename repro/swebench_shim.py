"""Import swebench's grading code on Windows.

swebench/__init__.py pulls in prepare_images.py, which imports the Unix-only
`resource` module. We only use the log-parsing / grading path (no Docker), so a
stub is enough. This affects imports only -- no grading logic is altered.
"""
import sys, types

if sys.platform == "win32" and "resource" not in sys.modules:
    m = types.ModuleType("resource")
    m.RLIMIT_NOFILE = 7
    m.RLIM_INFINITY = -1
    m.getrlimit = lambda *a, **k: (1024, 4096)
    m.setrlimit = lambda *a, **k: None
    sys.modules["resource"] = m
