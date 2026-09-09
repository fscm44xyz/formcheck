"""Windows shim for `fcntl`, so `verifiers` v1 can be IMPORTED on this machine.

`verifiers/v1/runtimes/limiters.py` imports `fcntl` at module scope and uses
`flock(LOCK_EX)` / `flock(LOCK_UN)` for an advisory, cross-process creation
limiter. `fcntl` is Unix-only, so `import verifiers.v1` fails outright on
Windows -- the same shape as the `resource` import that `swebench_shim.py`
already stubs for the grader.

SCOPE, stated plainly: this makes the import work and the locks NO-OPS. It is
sound for what we use it for -- importing the library and exercising the
validation hooks in a single process, with no sandbox creation and no
concurrency. It is NOT a Windows port, and it would be wrong to run a real
multi-process eval behind it, because the advisory lock it removes is exactly
what serialises sandbox creation.

Import this BEFORE any `verifiers` import.
"""
import sys
import types

if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401  (present on POSIX -- then nothing is stubbed)
    except ImportError:
        _stub = types.ModuleType("fcntl")
        _stub.LOCK_EX = 2
        _stub.LOCK_SH = 1
        _stub.LOCK_UN = 8
        _stub.LOCK_NB = 4

        def _flock(fd, operation):  # noqa: D103 - advisory lock, no-op here
            return None

        def _fcntl(fd, cmd, arg=0):  # noqa: D103
            return 0

        def _ioctl(fd, request, arg=0, mutate_flag=True):  # noqa: D103
            return 0

        _stub.flock = _flock
        _stub.fcntl = _fcntl
        _stub.ioctl = _ioctl
        _stub.lockf = _flock
        _stub.__doc__ = "no-op Windows stub installed by formcheck f3_fcntl_shim"
        sys.modules["fcntl"] = _stub
