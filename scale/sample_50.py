"""Draw M3's 50 tasks, stratified by repo, and freeze them to a file.

WHY THE IDS ARE COMMITTED BEFORE THE RUN. A sample chosen after seeing results is
not a sample, and "we re-drew because the first draw looked odd" is unfalsifiable
after the fact. So the draw is deterministic from a fixed seed, written to
`scale/ids_50.txt`, and committed in its own commit before any container starts.
The commit order is the evidence; the seed alone would not be, since a seed can
be tried repeatedly.

WHY STRATIFIED BY REPO. Verified is dominated by a handful of repos (django and
sympy between them are a large fraction). A simple random draw of 50 would be
mostly django, and a witness rate over it would be a statement about django's
test conventions wearing the label of a statement about SWE-bench. Proportional
allocation by repo keeps the mix representative while guaranteeing the smaller
repos are not wiped out by chance.

Largest-remainder allocation, so the parts sum to exactly 50 without a final
top-up that would quietly favour whichever repo the loop reached last.

    ~/.venv-fc/bin/python scale/sample_50.py
"""

import argparse
import collections
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ELIGIBLE = os.path.join(HERE, "eligible.jsonl")
OUT = os.path.join(HERE, "ids_50.txt")

SEED = 20260908
N = 50


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["eligible"]:
                rows.append(row)
    return sorted(rows, key=lambda r: r["instance_id"])


def allocate(counts, n):
    """Largest-remainder proportional allocation of `n` across `counts`."""
    total = sum(counts.values())
    exact = {k: v * n / total for k, v in counts.items()}
    base = {k: int(v) for k, v in exact.items()}
    short = n - sum(base.values())
    order = sorted(counts, key=lambda k: (-(exact[k] - base[k]), k))
    for k in order[:short]:
        base[k] += 1
    return base


def draw(rows, n=N, seed=SEED):
    """Stratify by target-count group FIRST, then by repo within each group.

    WHY TWO LEVELS, AND WHEN THIS WAS DECIDED -- stated plainly because the
    sequence matters. The first version stratified by repo only. Drawn at seed
    20260908 it returned 50 single-target tasks and ZERO multi-target ones, out
    of a pool that is 70/500 multi-target. The code was not at fault: seeds 1, 2
    and 3 return 11, 6 and 8. That seed was simply an unlucky draw, at roughly
    p = 0.0006.

    The draw was then re-designed rather than re-seeded. The distinction is the
    whole point: re-rolling until a sample looks agreeable is choosing a sample
    after seeing it, and no seed would make that legitimate. What was wrong here
    is the DESIGN -- the report is specified to give single-file and multi-file
    results separately, so target-count group is a reporting stratum and had to
    be a sampling stratum too. A design that can return an empty group cannot
    produce the required report.

    Nothing about outcomes was observed when this changed: no container had run,
    and the only thing seen was the sample's composition, which is exactly what
    stratification exists to control. The seed is unchanged.
    """
    rng = random.Random(seed)
    groups = {"single": [r for r in rows if r["n_targets"] == 1],
              "multi": [r for r in rows if r["n_targets"] > 1]}
    group_quota = allocate({k: len(v) for k, v in groups.items() if v}, n)
    picked = []
    for group in sorted(groups):
        pool_g = groups[group]
        if not pool_g or not group_quota.get(group):
            continue
        by_repo = collections.defaultdict(list)
        for r in pool_g:
            by_repo[r["repo"]].append(r)
        quota = allocate({k: len(v) for k, v in by_repo.items()},
                         group_quota[group])
        for repo in sorted(by_repo):
            pool = sorted(by_repo[repo], key=lambda r: r["instance_id"])
            k = min(quota[repo], len(pool))
            if k:
                picked.extend(rng.sample(pool, k))
    picked.sort(key=lambda r: r["instance_id"])
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("-n", type=int, default=N)
    args = ap.parse_args()

    rows = load(ELIGIBLE)
    picked = draw(rows, args.n, args.seed)

    single = [r for r in picked if r["n_targets"] == 1]
    multi = [r for r in picked if r["n_targets"] > 1]

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# M3 sample -- {len(picked)} tasks, seed {args.seed}, "
                f"stratified by repo (largest remainder)\n")
        f.write(f"# drawn from {len(rows)} eligible tasks in eligible.jsonl\n")
        f.write(f"# single-target {len(single)}, multi-target {len(multi)}\n")
        f.write("# Committed BEFORE the run. Do not redraw.\n")
        for r in picked:
            f.write(f"{r['instance_id']}\n")

    print(f"drawn {len(picked)} of {len(rows)} eligible, seed {args.seed}\n")
    per_repo = collections.Counter(r["repo"] for r in picked)
    pool_repo = collections.Counter(r["repo"] for r in rows)
    print(f"  {'repo':30s} {'pool':>5} {'share':>7} {'drawn':>6}")
    for repo in sorted(per_repo):
        share = pool_repo[repo] / len(rows)
        print(f"  {repo:30s} {pool_repo[repo]:>5} {share:>6.1%} {per_repo[repo]:>6}")
    print(f"\n  single-target {len(single)}   multi-target {len(multi)}")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
