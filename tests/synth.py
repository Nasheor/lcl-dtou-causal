"""Synthetic inputs for the tests: a half-hourly raw table with known rule violations, a 2013 schedule with
known bands, and a household-month panel with an injected effect of known size."""
from __future__ import annotations

import numpy as np
import pandas as pd

HIGH_HOURS = (17, 18)
LOW_HOURS = (2, 3)
PRICES = {"High": 67.20, "Normal": 11.76, "Low": 3.99}


def synthetic_schedule() -> pd.DataFrame:
    ts = pd.date_range("2013-01-01 00:00", "2013-12-31 23:30", freq="30min")
    band = np.where(ts.hour.isin(HIGH_HOURS), "High", np.where(ts.hour.isin(LOW_HOURS), "Low", "Normal"))
    df = pd.DataFrame({"ts": ts, "band": band})
    df["price_p_per_kwh"] = df["band"].map(PRICES)
    return df


def _rows(lclid: str, grp: str, start: str, end: str, kwh: float) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="30min", inclusive="left")
    return pd.DataFrame({"lclid": lclid, "grp": grp, "ts": ts, "kwh": float(kwh)})


def synthetic_raw() -> pd.DataFrame:
    """Households with known properties.

    A: Std, constant 0.5 kWh from Nov 2011 to Feb 2014, one duplicate reading on 10 Jan 2012 10:00 (1.0 and 3.0
       instead of 0.5) and 30 missing half-hours in April 2012 (still above 80 %).
    B: ToU, constant 1.0 kWh, full coverage.
    C: Std, full 2012 except March at 50 % coverage, and only January to May 2013 (five months, dropped by R4).
    D: Std in 2012 and ToU in 2013 (dropped by R5).
    E: ToU, 2013 only (dropped by R4).
    F: ToU, full 2012 and January to June 2013 only (six months, kept with 18 months).
    """
    parts = []
    a = _rows("A", "Std", "2011-11-01", "2014-03-01", 0.5)
    a = a[~((a["ts"] >= "2012-04-10 00:00") & (a["ts"] < "2012-04-10 15:00"))]  # 30 half-hours missing
    dup = pd.DataFrame({"lclid": "A", "grp": "Std", "ts": [pd.Timestamp("2012-01-10 10:00")] * 2, "kwh": [1.0, 3.0]})
    a = a[a["ts"] != pd.Timestamp("2012-01-10 10:00")]
    parts += [a, dup]
    parts.append(_rows("B", "ToU", "2011-11-01", "2014-03-01", 1.0))
    c = _rows("C", "Std", "2012-01-01", "2013-06-01", 0.7)
    march = (c["ts"] >= "2012-03-01") & (c["ts"] < "2012-04-01")
    c = c[~(march & (c["ts"].dt.hour >= 12))]  # March at 50 %
    parts.append(c)
    parts.append(_rows("D", "Std", "2012-01-01", "2013-01-01", 0.4))
    parts.append(_rows("D", "ToU", "2013-01-01", "2014-01-01", 0.4))
    parts.append(_rows("E", "ToU", "2013-01-01", "2014-01-01", 0.9))
    parts.append(_rows("F", "ToU", "2012-01-01", "2013-07-01", 0.6))
    return pd.concat(parts, ignore_index=True)


def synthetic_panel(n_tou: int = 120, n_std: int = 280, effect_pct: float = -10.0, selection_pct: float = 20.0, seed: int = 7, noise_sd: float = 0.08) -> tuple[pd.DataFrame, float]:
    """A household-month panel with additive household and month effects (so parallel trends hold in
    levels), a treated group whose base usage is ``selection_pct`` higher (self-selection), and a
    multiplicative ``effect_pct`` on treated 2013 months. Returns the panel and the true average treatment
    effect on the treated in levels for ``kwh_total``."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2012-01-01", "2013-12-01", freq="MS")
    season = 75.0 * np.cos(2 * np.pi * (months.month - 1) / 12.0)
    ids = [f"T{i:04d}" for i in range(n_tou)] + [f"S{i:04d}" for i in range(n_std)]
    tou = np.array([1] * n_tou + [0] * n_std)
    base = rng.lognormal(mean=np.log(300.0), sigma=0.4, size=len(ids)) * (1 + selection_pct / 100.0 * tou)
    rows = []
    true = []
    for i, hid in enumerate(ids):
        for t, m in enumerate(months):
            y0 = base[i] + season[t] + noise_sd * base[i] * rng.standard_normal()
            post = int(m.year == 2013)
            y = y0 * (1 + effect_pct / 100.0) if (tou[i] and post) else y0
            if tou[i] and post:
                true.append(y - y0)
            rows.append(
                {
                    "lclid": hid,
                    "group": "ToU" if tou[i] else "Std",
                    "month": m,
                    "post": post,
                    "tou": int(tou[i]),
                    "kwh_total": y,
                    "kwh_high": 0.1 * y,
                    "kwh_low": 0.1 * y,
                    "cost_own_gbp": y * 0.14228,
                    "cost_dtou_gbp": y * 0.12,
                }
            )
    return pd.DataFrame(rows), float(np.mean(true)) if true else 0.0
