"""Pre-registration freeze and check.

``freeze`` hashes ``PREREGISTRATION.md`` with sha256, writes ``results/preregistration_sha256.json`` (the
hash, the UTC time, the git commit that holds the plan) and commits that one file in its own commit.
``check`` compares the current hash with the recorded one. Every analysis command calls
``require_frozen`` and refuses to run when the hash file is missing or the plan has changed, unless
``--deviation <id>`` names an entry in ``DEVIATIONS.md``. A deviation entry is a heading of the form
``## D1 (2026-10-28)`` followed by a ``Reason:`` line. Coding fixes may be recorded there. A change of
outcome, group, period or estimator is not a deviation but a stop.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import subprocess

from .common import DEVIATIONS, HASH_FILE, PREREG, ROOT, git, git_head, read_json, write_json

CO_AUTHOR = "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"


def sha256_of(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_hash() -> str:
    return sha256_of(PREREG)


def recorded() -> dict | None:
    if not HASH_FILE.exists():
        return None
    return read_json(HASH_FILE)


def status() -> dict:
    rec = recorded()
    cur = current_hash() if PREREG.exists() else None
    return {
        "plan_exists": PREREG.exists(),
        "hash_file_exists": rec is not None,
        "current_sha256": cur,
        "recorded_sha256": rec.get("sha256") if rec else None,
        "frozen_at_utc": rec.get("frozen_at_utc") if rec else None,
        "plan_commit": rec.get("plan_commit") if rec else None,
        "match": bool(rec and cur and rec.get("sha256") == cur),
    }


def freeze() -> dict:
    """Record the hash of the committed plan and commit the hash file on its own."""
    if not PREREG.exists():
        raise SystemExit("PREREGISTRATION.md is missing")
    if HASH_FILE.exists():
        raise SystemExit(f"{HASH_FILE} already exists, the plan is frozen")
    dirty = git("status", "--porcelain", "--", str(PREREG.relative_to(ROOT)))
    if dirty:
        raise SystemExit("commit PREREGISTRATION.md before freezing it")
    rec = {
        "file": "PREREGISTRATION.md",
        "sha256": current_hash(),
        "frozen_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "plan_commit": git_head(),
    }
    write_json(HASH_FILE, rec)
    git("add", str(HASH_FILE.relative_to(ROOT)))
    msg = f"Freeze the pre-registration, sha256 {rec['sha256'][:12]}\n\n{CO_AUTHOR}\n"
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    rec["freeze_commit"] = git_head()
    return rec


def deviation_ids() -> set[str]:
    if not DEVIATIONS.exists():
        return set()
    text = DEVIATIONS.read_text(encoding="utf-8")
    return set(re.findall(r"^## (D\d+) \(\d{4}-\d{2}-\d{2}\)", text, flags=re.M))


def require_frozen(deviation: str | None = None) -> dict:
    """Refuse to run an analysis unless the plan is frozen and unchanged, or a named deviation exists."""
    st = status()
    if not st["hash_file_exists"]:
        raise SystemExit("the pre-registration is not frozen: run `python -m lcl_dtou_causal prereg freeze` first")
    if st["match"]:
        return st
    if deviation and deviation in deviation_ids():
        st["deviation"] = deviation
        return st
    raise SystemExit(
        "PREREGISTRATION.md has changed since it was frozen "
        f"(recorded {st['recorded_sha256'][:12]}, current {st['current_sha256'][:12]}). "
        "Add an entry to DEVIATIONS.md and pass --deviation <id>, or restore the frozen plan."
    )
