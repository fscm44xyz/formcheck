"""Disk-aware image rotation, and reclaiming what a crashed run left behind.

M0 measured the binding constraint: 3.841 GB pulled and discarded for one task,
against 0.37 GiB of RAM and a container overhead of ~13%. Compute is not worth
optimizing; disk is the whole design problem. So an image is pulled, used, and
removed, and only as many are resident at once as there are workers.

WHY RECONCILE, AND WHY IT IS THE SAME BUG AS STALE BYTECODE.
A worker killed mid-task -- OOM, timeout, an operator's Ctrl-C -- never reaches
its `docker rmi`. The image stays resident. At ~3.6 GiB each a handful of those
silently consume the budget, and the next `docker pull` fails with a message
about space that reads like a network fault. That is state outliving the run it
belonged to, exactly as a stale `.pyc` outlived the case that produced it and
surfaced in the next one (`writeup.md` 9). The fix has the same shape: purge it
explicitly, every time, rather than trusting the previous run to have tidied up.

OWNERSHIP IS A LEASE ON DISK, NOT A VARIABLE IN MEMORY.
A variable dies with the process that crashed. A lease file does not: it records
the pid that took it, so a later run can ask whether that pid is still alive and
reclaim the image if it is not. Within one run all workers share a pid, which is
enough -- a live worker removes its own lease in a `finally`, so a lease with a
live pid and no owner cannot outlast the run that made it.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time

# Every SWE-bench instance image is published under this namespace by
# `swebench`'s own `TestSpec.instance_image_key` (see `images.py`). Reconcile
# deliberately matches on it rather than on "all images": this must never remove
# an image some other workload on the box is using.
NAMESPACE = "swebench/"

# Used only for the pre-pull headroom check, where the real size is not yet
# known. M0 measured 3.841 GB for `pytest-10356`; this rounds up. It is an
# estimate and is named as one -- the post-pull accounting below uses the real
# size reported by docker.
ASSUMED_IMAGE_BYTES = 4 * 1024**3

# Refuse to start a pull without room for the image twice over: once for the
# image, once for the layer extraction that happens alongside it.
HEADROOM_FACTOR = 2


class RateLimited(RuntimeError):
    """The registry refused to serve us, so the task was never attempted.

    Distinct from every task-level failure on purpose. A 429 says nothing about
    the task: it was not mounted, not controlled, not judged. Recording it as a
    failed task would put an infrastructure refusal in the same bucket as a real
    result, and 334 of those in a row is what M4 did before it was stopped.
    """


# Docker Hub publishes the quota on every request. Reading it is better than
# pacing against a hardcoded interval, which is a guess that breaks the day the
# quota changes -- and it did change: the limit is 100 per HOUR, not per six
# hours as first assumed.
_RATE_URL = ("https://auth.docker.io/token?service=registry.docker.io"
             "&scope=repository:ratelimitpreview/test:pull")
_RATE_HEAD = "https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest"

# Keep this many pulls in hand. Not a throttle -- a floor, so a burst never
# takes the last slot and turns every subsequent task into a refusal.
PULL_RESERVE = 8


def hub_rate_limit():
    """`{limit, remaining, window}` from Docker Hub's own headers, or None.

    The `ratelimitpreview/test` probe is the endpoint Docker documents for this
    and does not itself consume quota. Returning None means "cannot measure",
    which the caller must treat as "proceed and say so" rather than as "fine".
    """
    import json as _json
    import urllib.request
    try:
        with urllib.request.urlopen(_RATE_URL, timeout=20) as r:
            token = _json.load(r)["token"]
        req = urllib.request.Request(_RATE_HEAD, method="HEAD")
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=20) as r:
            hdrs = {k.lower(): v for k, v in r.headers.items()}
    except Exception:
        return None

    def parse(name):
        raw = hdrs.get(name)
        if not raw:
            return None
        head = raw.split(";")[0].strip()
        window = raw.split("w=")[-1] if "w=" in raw else "3600"
        try:
            return int(head), int(window)
        except ValueError:
            return None

    lim, rem = parse("ratelimit-limit"), parse("ratelimit-remaining")
    if not lim or not rem:
        return None
    return {"limit": lim[0], "remaining": rem[0], "window": lim[1]}


def wait_for_pull_slot(log=None):
    """Block until the registry has quota to spare, pacing off its own headers.

    Returns the last reading (or None if the quota cannot be measured), so the
    caller can record `remaining` alongside the pull and the margin is visible
    in `progress.jsonl` rather than inferred afterwards.
    """
    log = log or (lambda **kw: None)
    while True:
        info = hub_rate_limit()
        if info is None:
            log(event="rate_limit_unknown",
                note="registry quota not measurable; proceeding unpaced")
            return None
        if info["remaining"] > PULL_RESERVE:
            return info
        # One slot ages out roughly every window/limit seconds in a sliding
        # window, so that is the natural wait -- derived, not guessed.
        nap = max(20, info["window"] // max(1, info["limit"]))
        log(event="rate_limit_wait", remaining=info["remaining"],
            limit=info["limit"], window=info["window"], sleep_s=nap)
        time.sleep(nap)


def is_rate_limited(text: str) -> bool:
    t = (text or "").lower()
    return "429" in t or "toomanyrequests" in t or "too many requests" in t


class NotEnoughDisk(RuntimeError):
    """Raised instead of letting `docker pull` fail with a space error that
    reads like a network fault."""


def _docker(*args, timeout=600):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout)


_ROOT_DIR = None


def docker_root_dir() -> str:
    """Where the daemon actually stores images, asked of the daemon.

    Hardcoding `/var/lib/docker` happens to be right on the host this was written
    for, but it is the daemon's business, not ours: a separate docker volume, a
    rootless daemon or a remote one all put it elsewhere, and a headroom check
    guarding the wrong filesystem passes while the image store fills.
    """
    global _ROOT_DIR
    if _ROOT_DIR is None:
        out = _docker("info", "--format", "{{.DockerRootDir}}", timeout=30)
        _ROOT_DIR = out.stdout.strip() or "/var/lib/docker"
    return _ROOT_DIR


def free_bytes(path: str | None = None) -> int:
    try:
        return shutil.disk_usage(path or docker_root_dir()).free
    except OSError:
        # An unreadable root dir (a remote daemon, say) must not crash the run;
        # it must stop it, because an unmeasurable budget cannot be guarded.
        raise NotEnoughDisk(
            f"cannot measure free space at {path or docker_root_dir()!r}; "
            "refusing to pull against an unknown disk budget")


def resident_images() -> dict:
    """`{image_ref: size_bytes}` for every resident SWE-bench instance image."""
    out = _docker("images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}",
                  "--no-trunc")
    images = {}
    for line in out.stdout.splitlines():
        ref, _, _ = line.partition("\t")
        if ref.startswith(NAMESPACE):
            images[ref] = image_size(ref)
    return images


def image_size(ref: str) -> int:
    """Real size in bytes, from docker, or 0 when the image is already gone."""
    out = _docker("image", "inspect", "--format", "{{.Size}}", ref)
    try:
        return int(out.stdout.strip())
    except ValueError:
        return 0


class Leases:
    """Which resident image belongs to which still-running worker."""

    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)

    def _path(self, ref: str) -> str:
        # A ref contains `/` and `:`; neither may reach the filename.
        return os.path.join(self.dir, ref.replace("/", "_").replace(":", "_"))

    def take(self, ref: str, instance_id: str) -> None:
        with open(self._path(ref), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"pid": os.getpid(), "instance_id": instance_id,
                       "ref": ref, "taken": time.time()}, f)

    def release(self, ref: str) -> None:
        try:
            os.remove(self._path(ref))
        except FileNotFoundError:
            pass

    def live_refs(self) -> set:
        """Refs held by a lease whose owning process is still alive.

        A lease naming a dead pid is precisely the crash residue this module
        exists to clean up, so it is dropped here and its image becomes
        reclaimable.
        """
        live = set()
        for name in os.listdir(self.dir):
            path = os.path.join(self.dir, name)
            try:
                with open(path, encoding="utf-8") as f:
                    lease = json.load(f)
            except (OSError, ValueError):
                # Unreadable OR already gone. With several workers the listing
                # above is a snapshot: another worker can release its lease
                # between `listdir` and this `open`, and the removal below then
                # raced too. That is a real crash, not a hypothetical -- M4 lost
                # `astropy-8707` to it 0.8s in, with a FileNotFoundError naming
                # a DIFFERENT task's lease file.
                _unlink(path)
                continue
            if _pid_alive(lease.get("pid", -1)):
                live.add(lease["ref"])
            else:
                _unlink(path)
        return live


def _unlink(path: str) -> None:
    """Remove a lease, tolerating another worker having removed it first.

    Every removal here is racing every other worker's `release`, so "it is
    already gone" is the SUCCESS case, not an error.
    """
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid is None or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


class DiskBudgetError(RuntimeError):
    """Raised when disk does not come back after a task and cannot be reclaimed."""


# A task that has cleaned up correctly returns the filesystem to within noise of
# where it started; both a bare pull/rmi cycle and a full task (pull, container,
# formcheck, teardown, rmi) were measured at exactly 0 MiB residual. Anything
# above this is unexplained, and an unexplained budget cannot be guarded.
RESIDUAL_ABORT_MIB = 256


# The name `verifiers` gives the containers it starts for a validate run:
# `validate-{mode}-{idx}-{8 hex}` (`verifiers/v1/cli/validate.py`, `_run_check`).
# Matching on this prefix is what keeps reconcile from ever touching a container
# belonging to something else on this host.
CONTAINER_PREFIX = "validate-"


def reconcile_containers(keep_images: set) -> list:
    """Remove validate containers a killed worker left behind.

    A worker killed mid-task never reaches `runtime.stop()`, so its container
    keeps RUNNING. That is not merely untidy: a running container holds its
    image, so `docker rmi` cannot remove it and `docker image prune` will not
    collect its layers either. Reclaiming the image is therefore impossible
    until the container is gone, which is why this runs before the image sweep
    rather than after it.

    A container is orphaned iff its image is not one a live lease is holding. A
    live worker's container is protected because its image is in `keep_images`.
    """
    out = _docker("ps", "-a", "--format", "{{.Names}}\t{{.Image}}")
    removed = []
    for line in out.stdout.splitlines():
        name, _, image = line.partition("\t")
        if not name.startswith(CONTAINER_PREFIX) or image in keep_images:
            continue
        if _docker("rm", "-f", name, timeout=120).returncode == 0:
            removed.append(name)
    return removed


def image_present(ref: str) -> bool:
    return bool(_docker("images", "-q", ref).stdout.strip())


def containers_for(ref: str) -> list:
    out = _docker("ps", "-a", "--filter", f"ancestor={ref}", "--format", "{{.Names}}")
    return [n for n in out.stdout.split() if n]


def prune_is_safe() -> bool:
    """False while any worker is pulling. See `_PULLS_IN_FLIGHT`."""
    return _PULLS_IN_FLIGHT == 0


def reclaim_orphans(force: bool = False) -> int:
    """Collect layer data no image or container references, measured by `df`.

    WHY THIS EXISTS AND WHY IT IS MEASURED WITH `df`. A task killed mid-flight
    leaves layer data that `docker rmi` on the image does not collect. Worse,
    `docker system df` does not report it: over one session of this project it
    accumulated 5.06 GiB while `docker system df` showed `0B (0%)` reclaimable
    throughout, and `docker system prune` then reported reclaiming 41 kB while
    the filesystem gave back 5185 MiB. Docker's own accounting is therefore not
    usable as the budget; the filesystem is. Every byte figure here is a `df`
    delta.

    `image prune`, not `system prune`: it removes only dangling, untagged layer
    data. It can never take a tagged image, so it cannot touch a live worker's
    image or an unrelated workload's, and it does not remove stopped containers
    that might belong to something else on this host.
    """
    if not (force or prune_is_safe()):
        # Skipped, not silently done: a pull is in flight and pruning would
        # kill it. The orphan sweep is not urgent -- it runs at the start of
        # every run, when nothing is pulling.
        return 0
    before = free_bytes()
    _docker("image", "prune", "-f", timeout=300)
    return max(0, free_bytes() - before)


def reconcile(leases: Leases, keep: set | None = None, prune: bool = False) -> dict:
    """Remove every resident SWE-bench image no live worker is using.

    Returns what was reclaimed, so the caller can put it in `progress.jsonl`.
    Silent reclamation would make the disk budget unauditable: a run that ends
    with less free space than it started needs to show where it went.
    """
    keep = (keep or set()) | leases.live_refs()
    stale_containers = reconcile_containers(keep)
    removed, reclaimed = [], 0
    for ref, size in resident_images().items():
        if ref in keep:
            continue
        result = _docker("rmi", "-f", ref)
        if result.returncode == 0:
            removed.append(ref)
            reclaimed += size
        # A non-zero rc means something else holds the image (a running
        # container from another workload). Leaving it is correct; the headroom
        # check below is what decides whether the run can still proceed.
    orphaned = reclaim_orphans() if prune else 0
    return {"removed": removed,
            "containers_removed": stale_containers,
            # What `docker image inspect` said the removed images were worth.
            "reclaimed_bytes": reclaimed,
            # What the filesystem actually gave back from orphaned layer data,
            # which is the number docker's own accounting hides.
            "orphan_bytes_reclaimed": orphaned,
            "free_bytes_after": free_bytes()}


def ensure_headroom(need_bytes: int = ASSUMED_IMAGE_BYTES) -> None:
    free = free_bytes()
    if free < HEADROOM_FACTOR * need_bytes:
        raise NotEnoughDisk(
            f"{free / 1024**3:.2f} GiB free, need "
            f"{HEADROOM_FACTOR * need_bytes / 1024**3:.2f} GiB "
            f"({HEADROOM_FACTOR}x the assumed {need_bytes / 1024**3:.2f} GiB "
            "image). Not attempting the pull: a pull that fails on space "
            "reports it as a transport error.")


# Host RAM to reserve per concurrent worker. M0 measured +0.37 GiB for a whole
# task, so this is roughly 4x the measured figure -- headroom for a repo whose
# suite is heavier than pytest's, not a measurement.
RAM_PER_WORKER = 1536 * 1024**2

# A ceiling that disk and RAM cannot lift. Concurrent workers each pull ~3.6 GiB,
# so beyond a handful the bottleneck moves to the network and the docker daemon's
# own extraction, neither of which this module can measure. Raising it is a
# deliberate act with `--workers`.
MAX_WORKERS = 8

_RECONCILE_LOCK = asyncio.Lock()

# How many workers are inside a `docker pull` right now. Pruning is not safe
# while any of them are: `docker image prune` drops containerd content-store
# leases, and a pull in flight is HOLDING one, so the pull dies with
# "lease does not exist: not found" -- a daemon-level error with nothing in its
# text to connect it to the prune that caused it. Found by M2, whose five tasks
# all came back `unchecked` in ~2s. See `CHANGES.md` 11.
_PULLS_IN_FLIGHT = 0


def available_ram_bytes() -> int:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return RAM_PER_WORKER  # unknown -> assume room for exactly one


def suggested_workers(budget_bytes: int | None = None,
                      per_image: int = ASSUMED_IMAGE_BYTES) -> int:
    """How many tasks may run at once: whichever of disk, RAM or the ceiling
    binds first.

    Deliberately not a function of CPU count. M0 measured the container path at
    ~13% over the subprocess rig, so compute is not the constraint and tuning
    for it would be tuning for the wrong thing. Disk is what M0 showed binding,
    but on a box with a large empty volume the disk term alone suggests numbers
    (118, on the machine this was written for) that no other resource could
    sustain -- so it is a minimum over all three bounds, not just the one the
    finding named.
    """
    budget = budget_bytes if budget_bytes is not None else free_bytes()
    by_disk = int(budget // (HEADROOM_FACTOR * per_image))
    by_ram = int(available_ram_bytes() // RAM_PER_WORKER)
    return max(1, min(by_disk, by_ram, MAX_WORKERS))


class ImageLease:
    """Async context manager: reconcile, check headroom, pull, hold, remove.

    The `finally` is what keeps a normally-ending worker from becoming the crash
    residue above; the reconcile at the top is what handles the workers for which
    that `finally` never ran.

    WHY ASYNC. The first version was a plain `with`, and every docker call in it
    was a blocking `subprocess.run` executed directly inside a worker coroutine.
    That stalls the whole event loop for the duration of a ~4 GiB pull, so the
    workers serialized and `--workers 2` bought nothing -- visible in
    `progress.jsonl` as the second worker's `start` landing exactly at the first
    worker's `pulled`. The blocking calls now go through `asyncio.to_thread`, so
    concurrency is real rather than nominal.
    """

    def __init__(self, ref: str, instance_id: str, leases: Leases, log=None):
        self.ref, self.instance_id, self.leases = ref, instance_id, leases
        self.log = log or (lambda **kw: None)
        self.size = 0

    async def __aenter__(self):
        async with _RECONCILE_LOCK:
            # Serialized: two workers reconciling at once would each see the
            # other's freshly pulled image as unowned for the instant between
            # the pull and the lease being written.
            recovered = await asyncio.to_thread(
                reconcile, self.leases, {self.ref})
            if recovered["removed"]:
                self.log(event="reclaimed", instance_id=self.instance_id,
                         **recovered)
            ensure_headroom()
            self.leases.take(self.ref, self.instance_id)
        t0 = time.time()
        global _PULLS_IN_FLIGHT
        quota = await asyncio.to_thread(wait_for_pull_slot, self.log)
        _PULLS_IN_FLIGHT += 1
        try:
            pull = await asyncio.to_thread(_docker, "pull", self.ref,
                                           timeout=3600)
        finally:
            _PULLS_IN_FLIGHT -= 1
        if pull.returncode != 0:
            self.leases.release(self.ref)
            if is_rate_limited(pull.stderr):
                # NOT a task failure. The task was never attempted.
                raise RateLimited(
                    f"registry refused {self.ref}: "
                    f"{pull.stderr.strip()[:200]}")
            raise RuntimeError(f"docker pull {self.ref}: "
                               f"{pull.stderr.strip()[:300]}")
        self.size = await asyncio.to_thread(image_size, self.ref)
        self.log(event="pulled", instance_id=self.instance_id, ref=self.ref,
                 bytes=self.size, seconds=round(time.time() - t0, 1),
                 # The margin, logged per pull so it is visible rather than
                 # reconstructed after a burn.
                 quota_remaining=(quota or {}).get("remaining"),
                 quota_limit=(quota or {}).get("limit"))
        return self

    async def __aexit__(self, *exc):
        await asyncio.to_thread(_docker, "rmi", "-f", self.ref)
        self.leases.release(self.ref)
        self.log(event="removed", instance_id=self.instance_id, ref=self.ref,
                 bytes=self.size, free_bytes_after=free_bytes())
        return False
