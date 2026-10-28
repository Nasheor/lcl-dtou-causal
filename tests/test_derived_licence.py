"""No raw half-hourly row is committed, and the derived data carries the CC BY 4.0 note with the attribution line."""
import subprocess


def _tracked(repo_root) -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.split("\n")


def test_no_raw_rows_tracked(repo_root):
    tracked = _tracked(repo_root)
    assert not [p for p in tracked if p.startswith("data/raw/")]
    assert not [p for p in tracked if p.lower().endswith((".csv", ".zip", ".xlsx"))]


def test_derived_files_tracked_and_small(repo_root):
    tracked = _tracked(repo_root)
    for name in ("data/derived/panel_monthly.parquet", "data/derived/dtou_schedule_2013.parquet", "data/derived/prices.json", "data/derived/LICENCE"):
        assert name in tracked, name
    size = (repo_root / "data" / "derived" / "panel_monthly.parquet").stat().st_size
    assert size < 20 * 1024 * 1024


def test_licence_note(repo_root):
    text = (repo_root / "data" / "derived" / "LICENCE").read_text(encoding="utf-8")
    assert "Creative Commons Attribution 4.0 International" in text
    assert "https://creativecommons.org/licenses/by/4.0/" in text
    assert "UK Power Networks" in text and "Low Carbon London" in text
    assert "Changes:" in text
    assert ";" not in text
