"""Build the 2013 dToU half-hour schedule and the price file from the open release.

``Tariffs.xlsx`` (sheet ``Sheet1``, columns ``TariffDateTime`` and ``Tariff``) gives one band per half-hour of
2013: ``High``, ``Normal`` or ``Low``. It carries no prices, so the pence values come from Low Carbon London
Report A3 (printed pages 5 and 32) and the Datastore description, which agree. Both are recorded in
``data/derived/prices.json`` as the sources. The derived schedule is written to
``data/derived/dtou_schedule_2013.parquet`` with the dataset's CC BY 4.0 note in ``data/derived/LICENCE``.
"""
from __future__ import annotations

import pandas as pd

from .common import ATTRIBUTION, DERIVED, PRICES, RAW, RESULTS, SCHEDULE, write_json, write_text

TARIFFS_XLSX = RAW / "Tariffs.xlsx"
BANDS = ("High", "Normal", "Low")
PRICE_P_PER_KWH = {"High": 67.20, "Normal": 11.76, "Low": 3.99}
FLAT_STD_P_PER_KWH = 14.228
PRICE_SOURCES = [
    "Low Carbon London Learning Report A3, Residential consumer responsiveness to time-varying pricing, "
    "Schofield, Carmichael, Tindemans, Woolf and Bilton, Imperial College London, 30 June 2014, printed page 5: "
    "High price 67.20 pence/kWh, Mid price 11.76 pence/kWh, Low price 3.99 pence/kWh, nonTOU flat rate 14.228 pence/kWh. "
    "https://doi.org/10.25561/21252",
    "The same report, printed page 32 (section Final pricing schedule): High 67.2, Default 11.76, Low 3.99, nonTOU 14.228.",
    "London Datastore dataset description, https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households: "
    "High (67.20p/kWh), Low (3.99p/kWh) or normal (11.76p/kWh), flat rate 14.228pence/kWh.",
]

LICENCE_NOTE = f"""Derived data licence

The files in this folder are derived from the dataset "SmartMeter Energy Consumption Data in London
Households" (UK Power Networks, Low Carbon London), published on the London Datastore under the
Creative Commons Attribution 4.0 International licence, https://creativecommons.org/licenses/by/4.0/ .
They are redistributed under the same licence.

Attribution line to carry with any reuse:
{ATTRIBUTION}

Files:
- dtou_schedule_2013.parquet: one row per half-hour of 2013 with the price band (High, Normal, Low) read
  from the release's Tariffs.xlsx and the pence per kWh for that band.
- prices.json: the band prices and the flat rate with their sources.
- panel_monthly.parquet: one row per household and month (January 2012 to December 2013) with the
  pseudonymous household id as published, the trial group, half-hours observed, kWh in total and by band,
  and the cost at the flat rate, at the dToU schedule and at the household's own tariff. No half-hourly row
  is included.

The code in this repository is separate and under the MIT licence (see LICENSE).
"""


def read_tariffs(path=TARIFFS_XLSX) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Sheet1", engine="openpyxl")
    df = df.rename(columns={"TariffDateTime": "ts", "Tariff": "band"})
    df["ts"] = pd.to_datetime(df["ts"])
    df["band"] = df["band"].astype(str).str.strip()
    bad = sorted(set(df["band"]) - set(BANDS))
    if bad:
        raise RuntimeError(f"unexpected bands in Tariffs.xlsx: {bad}")
    if df["ts"].duplicated().any():
        raise RuntimeError("duplicate half-hours in Tariffs.xlsx")
    if len(df) != 17_520 or df["ts"].min() != pd.Timestamp("2013-01-01") or df["ts"].max() != pd.Timestamp("2013-12-31 23:30"):
        raise RuntimeError(f"Tariffs.xlsx does not cover 2013 half-hourly: {len(df)} rows, {df['ts'].min()} to {df['ts'].max()}")
    df["price_p_per_kwh"] = df["band"].map(PRICE_P_PER_KWH)
    return df.sort_values("ts").reset_index(drop=True)


BST_LOCAL_START = pd.Timestamp("2013-03-31 02:00")
BST_LOCAL_END = pd.Timestamp("2013-10-27 01:00")


def shifted_to_gmt(df: pd.DataFrame) -> pd.DataFrame:
    """The schedule re-labelled as if the readings were stamped in GMT while the schedule is in local time.

    Report A3 states the event schedule in local time and kept events off the clock-change days. During
    British Summer Time a local label is one hour ahead of GMT, so each schedule row inside BST moves back
    one hour. Labels that collide or go missing at the two changes (all Normal, no events on those days) are
    resolved by keeping the first and filling with Normal. Used only by the sensitivity run outside the
    pre-registered table."""
    s = df[["ts", "band", "price_p_per_kwh"]].copy()
    s["ts"] = pd.to_datetime(s["ts"])
    inside = (s["ts"] >= BST_LOCAL_START) & (s["ts"] < BST_LOCAL_END)
    s["ts"] = s["ts"].where(~inside, s["ts"] - pd.Timedelta(hours=1))
    s = s.drop_duplicates("ts", keep="first")
    full = pd.DataFrame({"ts": pd.date_range("2013-01-01 00:00", "2013-12-31 23:30", freq="30min")})
    s = full.merge(s, on="ts", how="left")
    s["band"] = s["band"].fillna("Normal")
    s["price_p_per_kwh"] = s["band"].map(PRICE_P_PER_KWH)
    return s.sort_values("ts").reset_index(drop=True)


def describe(df: pd.DataFrame) -> dict:
    """Band counts, event days and the clock-hour profile of the High and Low bands by season."""
    out = {
        "source": "open release, Tariffs.xlsx sheet Sheet1, columns TariffDateTime and Tariff",
        "half_hours": int(len(df)),
        "band_counts": {b: int((df["band"] == b).sum()) for b in BANDS},
        "event_days": int(df.loc[df["band"] != "Normal", "ts"].dt.date.nunique()),
        "high_days": int(df.loc[df["band"] == "High", "ts"].dt.date.nunique()),
        "low_days": int(df.loc[df["band"] == "Low", "ts"].dt.date.nunique()),
        "slots_per_day_on_clock_change": {
            d: int((df["ts"].dt.strftime("%Y-%m-%d") == d).sum()) for d in ("2013-03-31", "2013-10-27")
        },
    }
    bst = (df["ts"] >= "2013-03-31 01:00") & (df["ts"] < "2013-10-27 01:00")
    for band in ("High", "Low"):
        for season, mask in (("gmt_months", ~bst), ("bst_months", bst)):
            sub = df[(df["band"] == band) & mask]
            prof = sub["ts"].dt.hour.value_counts().sort_index()
            out[f"{band.lower()}_half_hours_by_clock_hour_{season}"] = {f"{int(h):02d}": int(n) for h, n in prof.items()}
    return out


def run() -> int:
    df = read_tariffs()
    DERIVED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SCHEDULE, index=False)
    write_json(
        PRICES,
        {
            "unit": "pence per kWh, unit rate only, no standing charge, VAT or levy",
            "dtou": PRICE_P_PER_KWH,
            "flat_Std": FLAT_STD_P_PER_KWH,
            "schedule_source": "open release, Tariffs.xlsx",
            "price_sources": PRICE_SOURCES,
            "tariffs_xlsx_carries_prices": False,
        },
    )
    write_text(DERIVED / "LICENCE", LICENCE_NOTE)
    info = describe(df)
    write_json(RESULTS / "schedule.json", info)
    print(f"schedule: {info['half_hours']} half-hours, bands {info['band_counts']}, event days {info['event_days']}")
    return 0
