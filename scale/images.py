"""Resolve the epoch-pinned Docker image for a SWE-bench instance.

WHY NOT INHERIT THIS FROM VERIFIERS. Its Harbor taskset does not name, build or
derive SWE-bench image refs: a task's `[environment].docker_image` arrives
already-resolved inside a registry package, verifiers refuses to build
Dockerfile-only environments, and the reward is read back from
`/logs/verifier/reward.json` (`verifiers/v1/tasksets/harbor/taskset.py`). There
is therefore nothing upstream to inherit, and the correct fallback is the
namespace `swebench` itself publishes.

WHY THIS IS NOT A GUESSED STRING. The ref is produced by `swebench`'s own
`TestSpec.instance_image_key` property, called on a `TestSpec` we construct. The
naming rule is never reimplemented here, so a change in `swebench` changes this
resolver with it instead of silently disagreeing with it. For the record, the
rule as it stands in 4.0.3 (`swebench/harness/test_spec/test_spec.py:109-113`):

    key = f"sweb.eval.{arch}.{instance_id.lower()}:{instance_image_tag}"
    if is_remote_image:                       # i.e. namespace is not None
        key = f"{namespace}/{key}".replace("__", "_1776_")

with `namespace` defaulting to "swebench" (`harness/run_evaluation.py:274`),
`instance_image_tag` to `LATEST == "latest"` (`harness/constants/__init__.py:169`),
and `arch` resolving to `x86_64` on any non-aarch64 host (`test_spec.py:219-223`).
The `__` -> `_1776_` substitution exists because Docker rejects a double
underscore in a repository name, and every SWE-bench instance id contains one.
"""

import platform

from swebench.harness.test_spec.test_spec import TestSpec

DEFAULT_NAMESPACE = "swebench"
DEFAULT_TAG = "latest"


def host_arch() -> str:
    """`x86_64` unless we are on an ARM host, matching `make_test_spec`."""
    return "arm64" if platform.machine() in {"aarch64", "arm64"} else "x86_64"


def image_ref(
    instance_id: str,
    namespace: str | None = DEFAULT_NAMESPACE,
    tag: str = DEFAULT_TAG,
    arch: str | None = None,
) -> str:
    """The pullable image ref for `instance_id`, via swebench's own property.

    The `TestSpec` fields that do not participate in `instance_image_key` are
    filled with empties: this object exists only to be asked for its image name,
    and constructing it that way is what keeps the naming rule in swebench's
    hands rather than in ours.
    """
    spec = TestSpec(
        instance_id=instance_id,
        repo="",
        version="",
        repo_script_list=[],
        env_script_list=[],
        eval_script_list=[],
        arch=arch or host_arch(),
        FAIL_TO_PASS=[],
        PASS_TO_PASS=[],
        language="py",
        docker_specs={},
        namespace=namespace,
        instance_image_tag=tag,
    )
    return spec.instance_image_key


if __name__ == "__main__":
    import sys

    for iid in sys.argv[1:] or ["pytest-dev__pytest-10356"]:
        print(f"{iid}\n  -> {image_ref(iid)}")
