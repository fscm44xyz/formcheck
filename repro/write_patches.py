import os, json, pandas as pd
HERE = os.path.dirname(__file__)
df = pd.read_parquet(os.path.join(HERE, "swebench_verified.parquet"))
r = df[df.instance_id == "pytest-dev__pytest-10356"].iloc[0]

# write with LF endings (git-diff native)
def w(name, text):
    p = os.path.join(HERE, name)
    if not text.endswith("\n"):
        text += "\n"
    with open(p, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    print("wrote", name, len(text), "chars")

w("gold.diff", r["patch"])
w("tests.diff", r["test_patch"])

meta = {
    "instance_id": r["instance_id"], "repo": r["repo"], "version": r["version"],
    "base_commit": r["base_commit"],
    "FAIL_TO_PASS": json.loads(r["FAIL_TO_PASS"]) if isinstance(r["FAIL_TO_PASS"], str) else list(r["FAIL_TO_PASS"]),
    "PASS_TO_PASS": json.loads(r["PASS_TO_PASS"]) if isinstance(r["PASS_TO_PASS"], str) else list(r["PASS_TO_PASS"]),
}
with open(os.path.join(HERE, "meta.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print("F2P:", meta["FAIL_TO_PASS"])
print("n P2P:", len(meta["PASS_TO_PASS"]))
