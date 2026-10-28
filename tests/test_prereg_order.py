"""The freeze commit must come before the first commit that adds any result file.

Read from ``git log``: the commit that first added ``results/preregistration_sha256.json`` has to precede
the first commit adding any other path under ``results/`` except ``download_check.json``, and the plan
itself has to be committed before the freeze.
"""
import subprocess

HASH_FILE = "results/preregistration_sha256.json"
ALLOWED_BEFORE = {HASH_FILE, "results/download_check.json"}


def _first_add(repo_root) -> dict[str, int]:
    out = subprocess.run(
        ["git", "log", "--reverse", "--diff-filter=A", "--name-only", "--format=COMMIT %H"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout
    first: dict[str, int] = {}
    idx = -1
    for line in out.splitlines():
        if line.startswith("COMMIT "):
            idx += 1
        elif line.strip():
            first.setdefault(line.strip(), idx)
    return first


def test_freeze_precedes_every_result(repo_root):
    first = _first_add(repo_root)
    assert HASH_FILE in first, "the pre-registration hash file is not committed"
    freeze = first[HASH_FILE]
    assert first["PREREGISTRATION.md"] < freeze
    late = [p for p, i in first.items() if p.startswith("results/") and p not in ALLOWED_BEFORE and i <= freeze]
    assert not late, f"result files committed at or before the freeze: {late}"


def test_plan_not_modified_after_freeze(repo_root):
    """No commit after the freeze touches PREREGISTRATION.md (a deviation would also change the hash)."""
    first = _first_add(repo_root)
    log = subprocess.run(
        ["git", "log", "--reverse", "--format=%H", "--", "PREREGISTRATION.md"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout.split()
    all_commits = subprocess.run(["git", "log", "--reverse", "--format=%H"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.split()
    freeze_idx = first[HASH_FILE]
    touched_after = [c for c in log if all_commits.index(c) > freeze_idx]
    assert not touched_after, f"PREREGISTRATION.md changed after the freeze in {touched_after}"
