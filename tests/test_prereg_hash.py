"""The committed pre-registration hash must equal the hash of PREREGISTRATION.md as it stands."""
import hashlib
import json


def test_hash_file_matches_the_plan(repo_root):
    rec = json.loads((repo_root / "results" / "preregistration_sha256.json").read_text(encoding="utf-8"))
    current = hashlib.sha256((repo_root / "PREREGISTRATION.md").read_bytes()).hexdigest()
    assert rec["sha256"] == current, "PREREGISTRATION.md changed after it was frozen"
    assert len(rec["plan_commit"]) == 40


def test_prereg_module_agrees(repo_root):
    from lcl_dtou_causal import prereg

    st = prereg.status()
    assert st["match"] is True
    assert prereg.require_frozen()["match"] is True
