"""Paths, deterministic JSON writing and small git helpers shared by every step.

Result files are written with sorted keys, two-space indentation and LF line endings, and only when
their content changes, so a repeated run leaves the working tree untouched. Timing and timestamps go
to ``runs/`` (gitignored), never into ``results/``.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
DERIVED = DATA / "derived"
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
RUNS = ROOT / "runs"

PREREG = ROOT / "PREREGISTRATION.md"
DEVIATIONS = ROOT / "DEVIATIONS.md"
HASH_FILE = RESULTS / "preregistration_sha256.json"
DOWNLOAD_CHECK = RESULTS / "download_check.json"

PANEL = DERIVED / "panel_monthly.parquet"
SCHEDULE = DERIVED / "dtou_schedule_2013.parquet"
PRICES = DERIVED / "prices.json"

ATTRIBUTION = (
    "Contains data from 'SmartMeter Energy Consumption Data in London Households', UK Power Networks "
    "(Low Carbon London), published on the London Datastore under the Creative Commons Attribution 4.0 "
    "International licence (https://creativecommons.org/licenses/by/4.0/). Changes: aggregated from "
    "half-hourly readings to household-month totals and joined to the 2013 dynamic time-of-use price schedule."
)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, obj: Any) -> bool:
    """Write ``obj`` as JSON only if the file content would change. Returns True when written."""
    text = dumps(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def write_text(path: Path, text: str) -> bool:
    """Write text with LF endings only if it changes. Returns True when written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def git_head() -> str:
    try:
        return git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def r(x: float, nd: int = 4) -> float:
    """Round for result files so that repeated runs give identical bytes."""
    return float(round(float(x), nd))
