"""Fetch the London Datastore files into ``data/raw/`` and verify them.

The partitioned release (168 CSV files of one million rows) and ``Tariffs.xlsx`` are downloaded with HTTP
range resume, their byte counts checked against the server's ``Content-Length`` and their sha256 recorded.
The zip is extracted into ``data/raw/lcl/``. One DuckDB pass over the CSV files then records the checks
the pre-registration lists in section 2 into ``results/download_check.json``. The licence rows in
``LICENCE_CHECK.md`` were written before this module ran. Downloaded files are data, never code: nothing
is executed from ``data/raw/``.
"""
from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

from .common import DOWNLOAD_CHECK, RAW, RUNS, write_json

DATASET_PAGE = "https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households"
FILES = {
    "Tariffs.xlsx": {
        "url": "https://data.london.gov.uk/download/vqm0d/14855047-44c2-4856-8a48-e5649200e6ce/Tariffs.xlsx",
        "expected_bytes": 245_384,
    },
    "Partitioned LCL Data.zip": {
        "url": "https://data.london.gov.uk/download/vqm0d/04feba67-f1a3-4563-98d0-f3071e3d56d1/Partitioned%20LCL%20Data.zip",
        "expected_bytes": 795_722_689,
    },
}
CSV_DIR = RAW / "lcl"
USER_AGENT = "lcl-dtou-causal/0.1 (research, resume-capable downloader)"
CHUNK = 8 * 1024 * 1024


def _log(msg: str) -> None:
    RUNS.mkdir(exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with (RUNS / "download.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _head_length(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        cl = r.headers.get("Content-Length")
        return int(cl) if cl else None


def fetch(url: str, dest: Path, expected: int | None, retries: int = 12) -> int:
    """Download ``url`` to ``dest`` with range resume. Returns the final byte count."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    if dest.exists() and (expected is None or dest.stat().st_size == expected):
        _log(f"have {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest.stat().st_size
    attempt = 0
    while True:
        have = part.stat().st_size if part.exists() else 0
        if expected is not None and have >= expected:
            break
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if have and r.status != 206:
                    _log(f"server ignored the range request for {dest.name}, restarting from zero")
                    have = 0
                    mode = "wb"
                else:
                    mode = "ab" if have else "wb"
                total = r.headers.get("Content-Range", "").split("/")[-1] or r.headers.get("Content-Length")
                _log(f"fetch {dest.name} from byte {have:,} (total {total})")
                with part.open(mode) as f:
                    t0 = time.time()
                    got = 0
                    while True:
                        chunk = r.read(CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if got % (64 * CHUNK) < CHUNK:
                            rate = got / max(time.time() - t0, 1e-9) / 1e6
                            _log(f"  {dest.name}: {have + got:,} bytes ({rate:.1f} MB/s)")
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            attempt += 1
            if attempt > retries:
                raise
            wait = min(60, 5 * attempt)
            _log(f"retry {attempt}/{retries} for {dest.name} after {type(e).__name__}: {e} (wait {wait}s)")
            time.sleep(wait)
    size = part.stat().st_size
    if expected is not None and size != expected:
        raise RuntimeError(f"{dest.name}: got {size:,} bytes, expected {expected:,}")
    part.replace(dest)
    _log(f"done {dest.name} ({size:,} bytes)")
    return size


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def extract(zip_path: Path, out_dir: Path) -> dict:
    """Extract plain CSV members of the zip. Members are written under ``out_dir`` by their base name only."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written, skipped, names = 0, 0, []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".csv"):
                continue
            name = Path(info.filename).name
            if "/" in name or "\\" in name or name.startswith("."):
                continue
            target = out_dir / name
            names.append(name)
            if target.exists() and target.stat().st_size == info.file_size:
                skipped += 1
                continue
            with z.open(info) as src, target.open("wb") as dst:
                while True:
                    block = src.read(CHUNK)
                    if not block:
                        break
                    dst.write(block)
            written += 1
    _log(f"extracted {written} files, {skipped} already present, {len(names)} CSV members")
    return {"csv_files": len(names), "written": written, "already_present": skipped}


def _connect() -> duckdb.DuckDBPyConnection:
    RUNS.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{(RUNS / 'duckdb_tmp').as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def csv_glob() -> str:
    return (CSV_DIR / "*.csv").as_posix()


def verify_csv() -> dict:
    """Checks from pre-registration section 2 over all CSV files in one DuckDB session."""
    con = _connect()
    cols = con.execute(f"DESCRIBE SELECT * FROM read_csv('{csv_glob()}', header=true, all_varchar=true)").fetchall()
    colnames = [c[0] for c in cols]
    kwh_col = next((c for c in colnames if c.strip().upper().startswith("KWH")), None)
    group_col = next((c for c in colnames if c.strip().lower() == "stdortou"), None)
    id_col = next((c for c in colnames if c.strip().lower() == "lclid"), None)
    dt_col = next((c for c in colnames if c.strip().lower() == "datetime"), None)
    if not all([kwh_col, group_col, id_col, dt_col]):
        raise RuntimeError(f"unexpected columns {colnames}")
    sample = con.execute(f"SELECT * FROM read_csv('{csv_glob()}', header=true, all_varchar=true) LIMIT 3").fetchall()
    q = lambda c: '"' + c.replace('"', '""') + '"'  # noqa: E731
    con.execute(
        f"""
        CREATE TABLE raw AS
        SELECT {q(id_col)} AS lclid, {q(group_col)} AS grp,
               try_cast(substr({q(dt_col)}, 1, 19) AS TIMESTAMP) AS ts,
               try_cast({q(kwh_col)} AS DOUBLE) AS kwh,
               {q(kwh_col)} AS kwh_raw
        FROM read_csv('{csv_glob()}', header=true, all_varchar=true)
        """
    )
    n_rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    groups = con.execute("SELECT grp, count(*), count(DISTINCT lclid) FROM raw GROUP BY grp ORDER BY grp").fetchall()
    n_ids = con.execute("SELECT count(DISTINCT lclid) FROM raw").fetchone()[0]
    both = con.execute("SELECT count(*) FROM (SELECT lclid FROM raw GROUP BY lclid HAVING count(DISTINCT grp) > 1)").fetchone()[0]
    ts_range = con.execute("SELECT min(ts), max(ts), count(*) FILTER (WHERE ts IS NULL) FROM raw").fetchone()
    nulls = con.execute(
        "SELECT count(*) FILTER (WHERE kwh IS NULL), count(DISTINCT kwh_raw) FILTER (WHERE kwh IS NULL) FROM raw"
    ).fetchone()
    null_tokens = [r[0] for r in con.execute("SELECT DISTINCT kwh_raw FROM raw WHERE kwh IS NULL LIMIT 5").fetchall()]
    aligned = con.execute(
        "SELECT count(*) FILTER (WHERE minute(ts) IN (0, 30) AND second(ts) = 0), count(*) FROM raw WHERE ts IS NOT NULL"
    ).fetchone()
    dups = con.execute(
        "SELECT count(*) FROM (SELECT lclid, ts FROM raw WHERE ts IS NOT NULL GROUP BY lclid, ts HAVING count(*) > 1)"
    ).fetchone()[0]
    dst = {}
    for day in ("2012-03-25", "2012-10-28", "2013-03-31", "2013-10-27"):
        rows = con.execute(
            f"""
            SELECT hour(ts), count(*) FROM raw
            WHERE ts >= TIMESTAMP '{day} 00:00:00' AND ts < TIMESTAMP '{day} 04:00:00'
            GROUP BY 1 ORDER BY 1
            """
        ).fetchall()
        dst[day] = {f"{h:02d}": int(n) for h, n in rows}
    per_year = con.execute(
        "SELECT year(ts), grp, count(DISTINCT lclid) FROM raw WHERE ts IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    con.close()
    return {
        "columns": colnames,
        "first_rows": [list(map(str, r)) for r in sample],
        "rows": int(n_rows),
        "stdorToU_present": True,
        "stdorToU_values": {g: {"rows": int(n), "households": int(h)} for g, n, h in groups},
        "households_distinct": int(n_ids),
        "households_with_both_flags": int(both),
        "households_ToU": int(next((h for g, _, h in groups if g == "ToU"), 0)),
        "households_Std": int(next((h for g, _, h in groups if g == "Std"), 0)),
        "timestamp_min": str(ts_range[0]),
        "timestamp_max": str(ts_range[1]),
        "timestamps_unparseable": int(ts_range[2]),
        "kwh_missing_rows": int(nulls[0]),
        "kwh_missing_tokens": null_tokens,
        "timestamps_on_half_hour": int(aligned[0]),
        "timestamps_total": int(aligned[1]),
        "duplicate_household_timestamps": int(dups),
        "readings_per_hour_on_clock_change_nights": dst,
        "households_by_year_and_group": {f"{y}_{g}": int(n) for y, g, n in per_year},
    }


def verify_tariffs(xlsx: Path) -> dict:
    """Read every sheet of Tariffs.xlsx and describe what it holds."""
    sheets = pd.read_excel(xlsx, sheet_name=None, engine="openpyxl")
    out = {"sheets": {}}
    for name, df in sheets.items():
        info = {"rows": int(len(df)), "columns": [str(c) for c in df.columns]}
        dt_col = next((c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()), None)
        band_col = next((c for c in df.columns if "tariff" in str(c).lower() and c != dt_col), None)
        if dt_col is not None:
            ts = pd.to_datetime(df[dt_col], errors="coerce")
            info["timestamp_min"] = str(ts.min())
            info["timestamp_max"] = str(ts.max())
            info["timestamps_unparseable"] = int(ts.isna().sum())
            info["duplicate_timestamps"] = int(ts.duplicated().sum())
            info["timestamps_on_half_hour"] = int(((ts.dt.minute.isin([0, 30])) & (ts.dt.second == 0)).sum())
        if band_col is not None:
            vc = df[band_col].astype(str).str.strip().value_counts()
            info["band_counts"] = {str(k): int(v) for k, v in vc.items()}
        info["head"] = [[str(x) for x in row] for row in df.head(3).itertuples(index=False)]
        out["sheets"][str(name)] = info
    bands = set()
    for s in out["sheets"].values():
        bands |= set(s.get("band_counts", {}).keys())
    out["has_2013_half_hourly_schedule"] = any(
        s.get("rows", 0) >= 17_000 and {"High", "Normal", "Low"} <= set(s.get("band_counts", {}).keys())
        for s in out["sheets"].values()
    )
    out["bands_found"] = sorted(bands)
    return out


def run() -> int:
    t0 = time.time()
    RAW.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, spec in FILES.items():
        dest = RAW / name
        server_len = None
        try:
            server_len = _head_length(spec["url"])
        except Exception as e:  # noqa: BLE001
            _log(f"HEAD failed for {name}: {e}")
        expected = server_len or spec["expected_bytes"]
        size = fetch(spec["url"], dest, expected)
        files[name] = {
            "url": spec["url"],
            "bytes": int(size),
            "server_content_length": server_len,
            "expected_bytes_recorded_in_licence_check": spec["expected_bytes"],
            "size_matches_server": bool(server_len is None or size == server_len),
            "sha256": sha256_of(dest),
        }
        _log(f"sha256 {name} {files[name]['sha256']}")
    ext = extract(RAW / "Partitioned LCL Data.zip", CSV_DIR)
    _log("verifying the CSV files with DuckDB")
    csv_info = verify_csv()
    _log("verifying Tariffs.xlsx")
    tariffs = verify_tariffs(RAW / "Tariffs.xlsx")
    schedule_route = "open release (Tariffs.xlsx)" if tariffs["has_2013_half_hourly_schedule"] else "unavailable in the open release"
    out = {
        "dataset_page": DATASET_PAGE,
        "licence": "CC BY 4.0, see LICENCE_CHECK.md",
        "files": files,
        "extraction": ext,
        "csv": csv_info,
        "tariffs_xlsx": tariffs,
        "schedule_route": schedule_route,
        "expected_households_near": 5567,
        "expected_tou_households_near": 1100,
        "raw_rows_committed": False,
    }
    write_json(DOWNLOAD_CHECK, out)
    write_json(RUNS / "download_timing.json", {"seconds": round(time.time() - t0, 1)})
    _log(f"download check written, {time.time() - t0:.0f} s, schedule route: {schedule_route}")
    return 0
