"""One DuckDB pass from the raw half-hourly CSV files to the household-month panel.

Implements the sample rules R0 to R5 of ``PREREGISTRATION.md`` section 4 and the outcome definitions of
section 6. Sums are taken in integers (micro-kWh and milli-pence) so the committed panel is identical
whatever DuckDB's thread count. ``build_panel`` takes a connection that already holds a relation named
``raw`` with columns ``lclid``, ``grp``, ``ts`` and ``kwh``, so the test suite can feed it a small
synthetic table. ``run`` reads the 168 CSV files, builds the panel, writes
``data/derived/panel_monthly.parquet`` and ``results/sample.json``.
"""
from __future__ import annotations

import time

import duckdb
import pandas as pd

from .common import PANEL, RESULTS, RUNS, SCHEDULE, read_json, write_json
from .download import CSV_DIR
from .schedule import FLAT_STD_P_PER_KWH, PRICES

WINDOW_START = "2012-01-01 00:00:00"
WINDOW_END = "2014-01-01 00:00:00"
MIN_SHARE_OBSERVED = 0.8
MIN_VALID_MONTHS = 6
PRICE_SCALE = 1000  # milli-pence
KWH_SCALE = 1_000_000  # micro-kWh


def connect(threads: int | None = None) -> duckdb.DuckDBPyConnection:
    RUNS.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{(RUNS / 'duckdb_tmp').as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    if threads:
        con.execute(f"SET threads TO {int(threads)}")
    return con


def register_raw_from_csv(con: duckdb.DuckDBPyConnection) -> None:
    glob = (CSV_DIR / "*.csv").as_posix()
    con.execute(
        f"""
        CREATE VIEW raw AS
        SELECT "LCLid" AS lclid, "stdorToU" AS grp,
               try_cast(substr("DateTime", 1, 19) AS TIMESTAMP) AS ts,
               try_cast("KWH/hh (per half hour)" AS DOUBLE) AS kwh
        FROM read_csv('{glob}', header=true, all_varchar=true)
        """
    )


def register_schedule(con: duckdb.DuckDBPyConnection, schedule: pd.DataFrame, flat_p_per_kwh: float = FLAT_STD_P_PER_KWH) -> None:
    """Register ``sched_all``: the 2013 schedule plus its mapping onto 2012 by calendar date and clock time.
    29 February 2012 takes the bands of 28 February 2013 at the same clock times."""
    s = schedule[["ts", "band", "price_p_per_kwh"]].copy()
    s["ts"] = pd.to_datetime(s["ts"])
    con.register("sched_2013", s)
    con.execute(f"SET VARIABLE flat_milli = {int(round(flat_p_per_kwh * PRICE_SCALE))}")
    con.execute(
        f"""
        CREATE TABLE sched_all AS
        SELECT ts, band, CAST(round(price_p_per_kwh * {PRICE_SCALE}) AS BIGINT) AS price_milli FROM sched_2013
        UNION ALL
        SELECT make_timestamp(2012, month(ts), day(ts), hour(ts), minute(ts), 0) AS ts, band,
               CAST(round(price_p_per_kwh * {PRICE_SCALE}) AS BIGINT) AS price_milli
        FROM sched_2013
        UNION ALL
        SELECT make_timestamp(2012, 2, 29, hour(ts), minute(ts), 0) AS ts, band,
               CAST(round(price_p_per_kwh * {PRICE_SCALE}) AS BIGINT) AS price_milli
        FROM sched_2013 WHERE month(ts) = 2 AND day(ts) = 28
        """
    )


def build_panel(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, dict]:
    """Apply R0 to R5 to the ``raw`` relation joined to ``sched_all``. Returns the panel and the sample log."""
    log: dict = {}

    def hh(sql: str) -> dict:
        rows = con.execute(sql).fetchall()
        return {g: {"households": int(h), "household_months": int(m) if m is not None else None} for g, h, m in rows}

    # R0 and R1: parseable timestamp, numeric reading, calendar window.
    con.execute(
        f"""
        CREATE TABLE r1 AS
        SELECT lclid, grp, ts, kwh FROM raw
        WHERE ts IS NOT NULL AND kwh IS NOT NULL
          AND ts >= TIMESTAMP '{WINDOW_START}' AND ts < TIMESTAMP '{WINDOW_END}'
        """
    )
    log["R0_all_rows"] = hh("SELECT grp, count(DISTINCT lclid), NULL FROM raw GROUP BY grp ORDER BY grp")
    log["R0_rows_total"] = int(con.execute("SELECT count(*) FROM raw").fetchone()[0])
    log["R0_rows_unparseable_timestamp"] = int(con.execute("SELECT count(*) FROM raw WHERE ts IS NULL").fetchone()[0])
    log["R0_rows_missing_kwh"] = int(con.execute("SELECT count(*) FROM raw WHERE kwh IS NULL").fetchone()[0])
    log["R1_rows_in_window"] = int(con.execute("SELECT count(*) FROM r1").fetchone()[0])
    log["R1_households"] = hh("SELECT grp, count(DISTINCT lclid), NULL FROM r1 GROUP BY grp ORDER BY grp")
    log["kwh_rows_with_more_than_3_decimals"] = int(
        con.execute("SELECT count(*) FROM r1 WHERE abs(kwh * 1000 - round(kwh * 1000)) > 1e-6").fetchone()[0]
    )

    # R2: duplicates collapsed to their mean, one observed half-hour.
    con.execute(
        f"""
        CREATE TABLE r2 AS
        SELECT lclid, grp, ts, CAST(round(avg(kwh) * {KWH_SCALE}) AS BIGINT) AS kwh_micro, count(*) AS n_readings
        FROM r1 GROUP BY lclid, grp, ts
        """
    )
    log["R2_duplicate_household_timestamps"] = int(con.execute("SELECT count(*) FROM r2 WHERE n_readings > 1").fetchone()[0])
    log["R2_rows_removed_by_collapsing"] = int(con.execute("SELECT sum(n_readings - 1) FROM r2").fetchone()[0] or 0)

    # Join the schedule, aggregate to household-month.
    con.execute(
        """
        CREATE TABLE hm AS
        SELECT r.lclid, r.grp, date_trunc('month', r.ts)::DATE AS month,
               count(*) AS halfhours_observed,
               sum(CASE WHEN r.n_readings > 1 THEN 1 ELSE 0 END) AS duplicates_collapsed,
               sum(CASE WHEN s.band IS NULL THEN 1 ELSE 0 END) AS halfhours_without_band,
               sum(r.kwh_micro) AS kwh_total_micro,
               sum(CASE WHEN s.band = 'High' THEN r.kwh_micro ELSE 0 END) AS kwh_high_micro,
               sum(CASE WHEN s.band = 'Normal' THEN r.kwh_micro ELSE 0 END) AS kwh_normal_micro,
               sum(CASE WHEN s.band = 'Low' THEN r.kwh_micro ELSE 0 END) AS kwh_low_micro,
               sum(r.kwh_micro * coalesce(s.price_milli, getvariable('flat_milli'))) AS cost_dtou_micro_milli,
               sum(r.kwh_micro * getvariable('flat_milli')) AS cost_flat_micro_milli
        FROM r2 r LEFT JOIN sched_all s ON s.ts = r.ts
        GROUP BY r.lclid, r.grp, month
        """
    )
    log["halfhours_without_schedule_band"] = int(con.execute("SELECT coalesce(sum(halfhours_without_band), 0) FROM hm").fetchone()[0])

    # R3: at least 80 % of the month's half-hours observed.
    con.execute(
        f"""
        CREATE TABLE r3 AS
        SELECT *, CAST(day(last_day(month)) * 48 AS INTEGER) AS halfhours_expected,
               halfhours_observed >= {MIN_SHARE_OBSERVED} * day(last_day(month)) * 48 AS valid
        FROM hm
        """
    )
    log["R3_household_months_before"] = hh("SELECT grp, count(DISTINCT lclid), count(*) FROM r3 GROUP BY grp ORDER BY grp")
    log["R3_household_months_valid"] = hh("SELECT grp, count(DISTINCT lclid), count(*) FROM r3 WHERE valid GROUP BY grp ORDER BY grp")

    # R4: at least six valid months in each year. R5: one group per household.
    con.execute(
        f"""
        CREATE TABLE keep AS
        SELECT lclid FROM r3 WHERE valid
        GROUP BY lclid
        HAVING count(*) FILTER (WHERE year(month) = 2012) >= {MIN_VALID_MONTHS}
           AND count(*) FILTER (WHERE year(month) = 2013) >= {MIN_VALID_MONTHS}
           AND count(DISTINCT grp) = 1
        """
    )
    log["R5_households_with_both_groups"] = int(
        con.execute("SELECT count(*) FROM (SELECT lclid FROM r3 GROUP BY lclid HAVING count(DISTINCT grp) > 1)").fetchone()[0]
    )
    con.execute(
        """
        CREATE TABLE panel AS
        SELECT r.lclid, r.grp AS "group", r.month, year(r.month) AS year, year(r.month) = 2013 AS post,
               r.halfhours_observed, r.halfhours_expected, r.duplicates_collapsed,
               r.kwh_total_micro, r.kwh_high_micro, r.kwh_normal_micro, r.kwh_low_micro,
               r.cost_flat_micro_milli, r.cost_dtou_micro_milli
        FROM r3 r JOIN keep k USING (lclid)
        WHERE r.valid
        ORDER BY r.lclid, r.month
        """
    )
    log["R4_households_kept"] = hh('SELECT "group", count(DISTINCT lclid), count(*) FROM panel GROUP BY "group" ORDER BY "group"')
    log["valid_months_per_household"] = {
        g: {"mean": float(m), "min": int(lo), "max": int(hi)}
        for g, m, lo, hi in con.execute(
            'SELECT "group", avg(n), min(n), max(n) FROM (SELECT "group", lclid, count(*) AS n FROM panel GROUP BY 1, 2) GROUP BY 1 ORDER BY 1'
        ).fetchall()
    }
    log["households_with_valid_month_by_month"] = {
        f"{m}_{g}": int(n)
        for m, g, n in con.execute(
            "SELECT strftime(month, '%Y-%m'), grp, count(*) FROM r3 WHERE valid GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
    }
    df = con.execute("SELECT * FROM panel").df()
    for c in ("kwh_total", "kwh_high", "kwh_normal", "kwh_low"):
        df[c] = (df[f"{c}_micro"] / KWH_SCALE).round(6)
    df["cost_flat_gbp"] = (df["cost_flat_micro_milli"] / (KWH_SCALE * PRICE_SCALE * 100)).round(6)
    df["cost_dtou_gbp"] = (df["cost_dtou_micro_milli"] / (KWH_SCALE * PRICE_SCALE * 100)).round(6)
    own = (df["group"] == "ToU") & (df["year"] == 2013)
    df["cost_own_gbp"] = df["cost_flat_gbp"].where(~own, df["cost_dtou_gbp"])
    cols = [
        "lclid", "group", "month", "year", "post", "halfhours_observed", "halfhours_expected", "duplicates_collapsed",
        "kwh_total", "kwh_high", "kwh_normal", "kwh_low", "cost_flat_gbp", "cost_dtou_gbp", "cost_own_gbp",
    ]
    df = df[cols].sort_values(["lclid", "month"]).reset_index(drop=True)
    df["month"] = pd.to_datetime(df["month"])
    return df, log


CLOCK_CHANGES = ("2012-03-25", "2012-10-28", "2013-03-31", "2013-10-27")


def timeframe_check(con: duckdb.DuckDBPyConnection) -> dict:
    """Mean half-hourly profile of the Std group in the fourteen days before and after each clock change.

    If the readings were stamped in local clock time, the profile keeps its shape across the change. If they
    were stamped in a fixed frame such as GMT, the whole profile moves by two slots after a spring change
    and back after an autumn change. The slot of the evening maximum and the first morning slot above the
    daily mean are reported for each window. Uses the ``r2`` table left by ``build_panel``."""
    cases = []
    for d in CLOCK_CHANGES:
        day = pd.Timestamp(d)
        before = (day - pd.Timedelta(days=14), day)
        after = (day + pd.Timedelta(days=1), day + pd.Timedelta(days=15))
        cases.append((f"{d}_before", before))
        cases.append((f"{d}_after", after))
    when = " ".join(f"WHEN ts >= TIMESTAMP '{a}' AND ts < TIMESTAMP '{b}' THEN '{name}'" for name, (a, b) in cases)
    rows = con.execute(
        f"""
        SELECT win, hour(ts) * 2 + minute(ts) // 30 AS slot, avg(kwh_micro) / {KWH_SCALE} AS kwh
        FROM (SELECT ts, kwh_micro, CASE {when} END AS win FROM r2 WHERE grp = 'Std')
        WHERE win IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).fetchall()
    prof: dict[str, list[float]] = {}
    for win, slot, kwh in rows:
        prof.setdefault(win, [0.0] * 48)[int(slot)] = float(kwh)
    out = {"group": "Std", "window_days": 14, "windows": {}}
    for name, (a, b) in cases:
        p = prof.get(name, [0.0] * 48)
        mean = sum(p) / 48.0
        evening = max(range(24, 48), key=lambda s: p[s])
        morning = next((s for s in range(8, 48) if p[s] >= mean), None)
        out["windows"][name] = {
            "from": str(a.date()),
            "to_exclusive": str(b.date()),
            "profile_kwh_per_half_hour": [round(x, 4) for x in p],
            "evening_peak_slot": int(evening),
            "evening_peak_clock": f"{evening // 2:02d}:{30 * (evening % 2):02d}",
            "first_morning_slot_above_daily_mean": morning,
        }
    out["evening_peak_shift_slots"] = {
        d: out["windows"][f"{d}_after"]["evening_peak_slot"] - out["windows"][f"{d}_before"]["evening_peak_slot"] for d in CLOCK_CHANGES
    }
    out["morning_crossing_shift_slots"] = {
        d: (out["windows"][f"{d}_after"]["first_morning_slot_above_daily_mean"] or 0)
        - (out["windows"][f"{d}_before"]["first_morning_slot_above_daily_mean"] or 0)
        for d in CLOCK_CHANGES
    }
    return out


def attrition(log: dict) -> dict:
    """Households by group at R0, with any valid month at R3 and kept at R4, with the shares lost."""
    out = {}
    for g in ("Std", "ToU"):
        r0 = log["R0_all_rows"].get(g, {}).get("households", 0)
        r3 = log["R3_household_months_valid"].get(g, {}).get("households", 0)
        r4 = log["R4_households_kept"].get(g, {}).get("households", 0)
        out[g] = {
            "households_R0": int(r0),
            "households_any_valid_month_R3": int(r3),
            "households_kept_R4": int(r4),
            "share_lost_R0_to_R4_pct": round(100.0 * (r0 - r4) / r0, 2) if r0 else None,
            "share_lost_R3_to_R4_pct": round(100.0 * (r3 - r4) / r3, 2) if r3 else None,
        }
    return out


def run(variant: str = "prereg") -> int:
    """``prereg`` builds the pre-registered panel. ``bst-shift`` builds the sensitivity panel of DEVIATIONS.md D1
    with the schedule moved back one hour inside British Summer Time before the join."""
    t0 = time.time()
    if not SCHEDULE.exists() or not PRICES.exists():
        raise SystemExit("run `python -m lcl_dtou_causal schedule` first")
    prices = read_json(PRICES)
    sched = pd.read_parquet(SCHEDULE)
    if variant == "bst-shift":
        from .common import PANEL_BST_SHIFT
        from .schedule import shifted_to_gmt

        sched = shifted_to_gmt(sched)
        out_path, log_path = PANEL_BST_SHIFT, RESULTS / "sensitivity_timeframe_sample.json"
    else:
        out_path, log_path = PANEL, RESULTS / "sample.json"
    con = connect()
    register_raw_from_csv(con)
    register_schedule(con, sched, float(prices["flat_Std"]))
    df, log = build_panel(con)
    if variant == "prereg":
        write_json(RESULTS / "timeframe_check.json", timeframe_check(con))
    else:
        log["variant"] = "schedule shifted to GMT during British Summer Time before the join (DEVIATIONS.md D1)"
    con.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    log["attrition"] = attrition(log)
    log["panel_rows"] = int(len(df))
    log["panel_columns"] = list(df.columns)
    log["rules"] = {
        "window": [WINDOW_START, WINDOW_END],
        "min_share_observed": MIN_SHARE_OBSERVED,
        "min_valid_months_per_year": MIN_VALID_MONTHS,
        "duplicates": "collapsed to their mean, one observed half-hour",
        "schedule_2012": "2013 bands mapped by calendar date and clock time, 29 February 2012 takes 28 February 2013",
    }
    write_json(log_path, log)
    write_json(RUNS / f"panel_timing_{variant}.json", {"seconds": round(time.time() - t0, 1)})
    print(f"panel: {len(df)} household-months, kept {log['R4_households_kept']}, {time.time() - t0:.0f} s")
    return 0
