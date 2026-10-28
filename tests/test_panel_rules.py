"""The sample rules and the outcome arithmetic on a synthetic half-hourly table with known violations."""
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import HIGH_HOURS, LOW_HOURS, PRICES, synthetic_raw, synthetic_schedule  # noqa: E402

from lcl_dtou_causal.panel import build_panel, register_schedule  # noqa: E402
from lcl_dtou_causal.schedule import FLAT_STD_P_PER_KWH  # noqa: E402


@pytest.fixture(scope="module")
def built():
    con = duckdb.connect()
    con.execute("SET threads TO 1")
    con.register("raw", synthetic_raw())
    register_schedule(con, synthetic_schedule(), FLAT_STD_P_PER_KWH)
    df, log = build_panel(con)
    con.close()
    return df, log


def test_window_excludes_2011_and_2014(built):
    df, _ = built
    assert df["month"].min().strftime("%Y-%m") == "2012-01"
    assert df["month"].max().strftime("%Y-%m") == "2013-12"


def test_households_kept_and_dropped(built):
    df, log = built
    kept = set(df["lclid"].unique())
    assert kept == {"A", "B", "F"}, kept
    assert log["R5_households_with_both_groups"] == 1  # D
    assert df[df["lclid"] == "F"]["month"].nunique() == 18


def test_eighty_percent_rule(built):
    df, log = built
    # C's March 2012 was at 50 %, so C had 11 valid months in 2012 and five in 2013: dropped by R4, counted at R3.
    assert log["R3_household_months_valid"]["Std"]["household_months"] >= 11
    a_april = df[(df["lclid"] == "A") & (df["month"] == "2012-04-01")].iloc[0]
    assert a_april["halfhours_observed"] == 30 * 48 - 30
    assert a_april["halfhours_expected"] == 30 * 48


def test_duplicates_collapsed_to_mean(built):
    df, log = built
    assert log["R2_duplicate_household_timestamps"] == 1
    a_jan = df[(df["lclid"] == "A") & (df["month"] == "2012-01-01")].iloc[0]
    assert a_jan["halfhours_observed"] == 31 * 48
    assert a_jan["duplicates_collapsed"] == 1
    # 31 days of 0.5 kWh with one half-hour replaced by the mean of 1.0 and 3.0.
    assert a_jan["kwh_total"] == pytest.approx(31 * 48 * 0.5 - 0.5 + 2.0, abs=1e-6)


def test_band_and_cost_arithmetic(built):
    df, _ = built
    b_mar13 = df[(df["lclid"] == "B") & (df["month"] == "2013-03-01")].iloc[0]
    days = 31
    assert b_mar13["kwh_total"] == pytest.approx(days * 48 * 1.0, abs=1e-6)
    assert b_mar13["kwh_high"] == pytest.approx(days * 2 * len(HIGH_HOURS) * 1.0, abs=1e-6)
    assert b_mar13["kwh_low"] == pytest.approx(days * 2 * len(LOW_HOURS) * 1.0, abs=1e-6)
    high, low = b_mar13["kwh_high"], b_mar13["kwh_low"]
    normal = b_mar13["kwh_total"] - high - low
    assert b_mar13["cost_flat_gbp"] == pytest.approx(b_mar13["kwh_total"] * FLAT_STD_P_PER_KWH / 100, abs=1e-6)
    assert b_mar13["cost_dtou_gbp"] == pytest.approx((high * PRICES["High"] + low * PRICES["Low"] + normal * PRICES["Normal"]) / 100, abs=1e-6)


def test_own_tariff_by_group_and_year(built):
    df, _ = built
    b = df[df["lclid"] == "B"].set_index("month")
    assert b.loc["2012-06-01", "cost_own_gbp"] == pytest.approx(b.loc["2012-06-01", "cost_flat_gbp"])
    assert b.loc["2013-06-01", "cost_own_gbp"] == pytest.approx(b.loc["2013-06-01", "cost_dtou_gbp"])
    a = df[df["lclid"] == "A"].set_index("month")
    assert a.loc["2013-06-01", "cost_own_gbp"] == pytest.approx(a.loc["2013-06-01", "cost_flat_gbp"])


def test_schedule_mapped_onto_2012_including_leap_day(built):
    df, log = built
    b_feb12 = df[(df["lclid"] == "B") & (df["month"] == "2012-02-01")].iloc[0]
    assert b_feb12["kwh_high"] == pytest.approx(29 * 2 * len(HIGH_HOURS) * 1.0, abs=1e-6)
    assert log["halfhours_without_schedule_band"] == 0
