"""Estimators, placebos, balance and heterogeneity on the household-month panel.

Everything here follows ``PREREGISTRATION.md`` sections 7 to 10. The panel columns used are ``lclid``,
``group`` (``ToU`` or ``Std``), ``month`` (first day of the month), ``post`` and the five outcome columns
named in ``OUTCOMES``. The two-way fixed effects regressions use linearmodels ``PanelOLS`` with household
and month effects and errors clustered by household. The permutation test recomputes the point estimate
with an alternating-projection two-way demeaning, which the full run checks against ``PanelOLS`` on the
observed assignment and records the difference.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.panel import PanelOLS
from scipy import stats

from . import prereg
from .common import DOCS, PANEL, RESULTS, RUNS, r, write_json

OUTCOMES = {
    "O1": ("cost_own_gbp", "monthly cost at own tariff (£)"),
    "O2": ("kwh_high", "monthly kWh in High-price half-hours"),
    "O3": ("cost_dtou_gbp", "monthly cost at the dToU schedule (£)"),
    "O4": ("kwh_total", "total monthly kWh"),
    "O5": ("kwh_low", "monthly kWh in Low-price half-hours"),
}
PRIMARY = ("O1", "O2")
SEED = 20261028
REFERENCE_MONTH = pd.Timestamp("2012-12-01")
TREATMENT_MONTH = pd.Timestamp("2013-01-01")
PLACEBO_MONTH = pd.Timestamp("2012-07-01")
Z95 = 1.959963984540054


# ---------------------------------------------------------------- panel helpers


def load_panel(path=PANEL) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["month"] = pd.to_datetime(df["month"])
    df["tou"] = (df["group"] == "ToU").astype(int)
    df["post"] = (df["month"] >= TREATMENT_MONTH).astype(int)
    return df.sort_values(["lclid", "month"]).reset_index(drop=True)


def stratified_sample(df: pd.DataFrame, n_tou: int, n_std: int, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids_tou = np.sort(df.loc[df["tou"] == 1, "lclid"].unique())
    ids_std = np.sort(df.loc[df["tou"] == 0, "lclid"].unique())
    keep = set(rng.choice(ids_tou, size=min(n_tou, len(ids_tou)), replace=False))
    keep |= set(rng.choice(ids_std, size=min(n_std, len(ids_std)), replace=False))
    return df[df["lclid"].isin(keep)].reset_index(drop=True)


def _panel_index(df: pd.DataFrame) -> pd.DataFrame:
    return df.set_index(["lclid", "month"])


def tou_pre_mean(df: pd.DataFrame, y: str) -> float:
    return float(df.loc[(df["tou"] == 1) & (df["post"] == 0), y].mean())


def counts(df: pd.DataFrame) -> dict:
    return {
        "households_ToU": int(df.loc[df["tou"] == 1, "lclid"].nunique()),
        "households_Std": int(df.loc[df["tou"] == 0, "lclid"].nunique()),
        "months_pre": int(df.loc[df["post"] == 0, "month"].nunique()),
        "months_post": int(df.loc[df["post"] == 1, "month"].nunique()),
        "household_months": int(len(df)),
    }


# ---------------------------------------------------------------- E1 DiD


def twfe_did(df: pd.DataFrame, y: str, treat: str = "D") -> dict:
    """Two-way fixed effects DiD, errors clustered by household."""
    p = _panel_index(df)
    res = PanelOLS(p[y], p[[treat]], entity_effects=True, time_effects=True).fit(cov_type="clustered", cluster_entity=True)
    att = float(res.params[treat])
    se = float(res.std_errors[treat])
    return {
        "att": r(att),
        "se": r(se),
        "ci_low": r(att - Z95 * se),
        "ci_high": r(att + Z95 * se),
        "p": r(float(res.pvalues[treat]), 6),
        "n_obs": int(res.nobs),
        "n_households": int(df["lclid"].nunique()),
    }


def did_outcome(df: pd.DataFrame, y: str) -> dict:
    d = df.assign(D=df["tou"] * df["post"])
    out = twfe_did(d, y)
    base = tou_pre_mean(df, y)
    out["tou_pre_mean"] = r(base)
    out["att_pct_of_pre_mean"] = r(100.0 * out["att"] / base, 2) if base else None
    return out


# ---------------------------------------------------------------- E2 event study


def event_study(df: pd.DataFrame, y: str) -> dict:
    months = sorted(df["month"].unique())
    free = [m for m in months if m != REFERENCE_MONTH]
    d = df.copy()
    names = []
    for m in free:
        name = f"ev_{pd.Timestamp(m).strftime('%Y_%m')}"
        d[name] = d["tou"] * (d["month"] == m).astype(int)
        names.append(name)
    p = _panel_index(d)
    res = PanelOLS(p[y], p[names], entity_effects=True, time_effects=True).fit(cov_type="clustered", cluster_entity=True)
    coefs = []
    for m in months:
        if m == REFERENCE_MONTH:
            coefs.append({"month": pd.Timestamp(m).strftime("%Y-%m"), "coef": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0, "reference": True})
            continue
        name = f"ev_{pd.Timestamp(m).strftime('%Y_%m')}"
        c, s = float(res.params[name]), float(res.std_errors[name])
        coefs.append({"month": pd.Timestamp(m).strftime("%Y-%m"), "coef": r(c), "se": r(s), "ci_low": r(c - Z95 * s), "ci_high": r(c + Z95 * s), "reference": False})
    pre_names = [f"ev_{pd.Timestamp(m).strftime('%Y_%m')}" for m in free if m < TREATMENT_MONTH]
    rest = np.zeros((len(pre_names), len(names)))
    for i, n in enumerate(pre_names):
        rest[i, names.index(n)] = 1.0
    wald = res.wald_test(restriction=rest)
    q = len(pre_names)
    g = int(df["lclid"].nunique())
    f_stat = float(wald.stat) / q
    p_f = float(stats.f.sf(f_stat, q, g - 1))
    return {
        "coefficients": coefs,
        "pre_months": [c["month"] for c in coefs if c["month"] < TREATMENT_MONTH.strftime("%Y-%m")],
        "post_months": [c["month"] for c in coefs if c["month"] >= TREATMENT_MONTH.strftime("%Y-%m")],
        "reference_month": REFERENCE_MONTH.strftime("%Y-%m"),
        "pretrend_wald_chi2": r(float(wald.stat)),
        "pretrend_df": q,
        "pretrend_p_chi2": r(float(wald.pval), 6),
        "pretrend_f": r(f_stat),
        "pretrend_p_f": r(p_f, 6),
        "n_obs": int(res.nobs),
    }


def plot_event_study(es: dict, key: str, label: str, out_dir) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    c = es["coefficients"]
    x = np.arange(len(c))
    est = np.array([v["coef"] for v in c])
    lo = np.array([v["ci_low"] for v in c])
    hi = np.array([v["ci_high"] for v in c])
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=120)
    ax.axhline(0, color="#777777", lw=0.8)
    ax.axvline(x[[v["month"] for v in c].index(TREATMENT_MONTH.strftime("%Y-%m"))] - 0.5, color="#b04a00", lw=1, ls="--")
    ax.errorbar(x, est, yerr=[est - lo, hi - est], fmt="o", color="#1f4e79", ecolor="#1f4e79", capsize=2, ms=4, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels([v["month"] for v in c], rotation=90, fontsize=7)
    ax.set_ylabel(f"{key}: {label}\ncoefficient vs {es['reference_month']}", fontsize=8)
    ax.set_title(f"Event study, {key}, ToU minus Std by month, 95 % household-clustered intervals", fontsize=9)
    ax.text(0.01, 0.97, f"pre-trend joint p = {es['pretrend_p_chi2']:.3f}", transform=ax.transAxes, va="top", fontsize=8)
    fig.tight_layout()
    path = out_dir / f"event_study_{key}.png"
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------- E3 comparison with a pre-period covariate


def ancova(df: pd.DataFrame, y: str) -> dict:
    """Post-period household mean on ToU and the pre-period household mean, HC1 errors."""
    pre = df[df["post"] == 0].groupby("lclid")[y].mean().rename("pre")
    post = df[df["post"] == 1].groupby("lclid")[y].mean().rename("post")
    tou = df.groupby("lclid")["tou"].first()
    h = pd.concat([pre, post, tou], axis=1).dropna()
    X = sm.add_constant(h[["tou", "pre"]].astype(float))
    res = sm.OLS(h["post"].astype(float), X).fit(cov_type="HC1")
    est, se = float(res.params["tou"]), float(res.bse["tou"])
    return {
        "estimate": r(est),
        "se": r(se),
        "ci_low": r(est - Z95 * se),
        "ci_high": r(est + Z95 * se),
        "p": r(float(res.pvalues["tou"]), 6),
        "pre_coefficient": r(float(res.params["pre"])),
        "n_households": int(len(h)),
    }


# ---------------------------------------------------------------- placebos


def placebo_date(df: pd.DataFrame, y: str) -> dict:
    pre = df[df["post"] == 0].copy()
    pre["D"] = pre["tou"] * (pre["month"] >= PLACEBO_MONTH).astype(int)
    out = twfe_did(pre, y)
    out["placebo_month"] = PLACEBO_MONTH.strftime("%Y-%m")
    out["covers_zero"] = bool(out["ci_low"] <= 0.0 <= out["ci_high"])
    return out


def two_way_demean(x: np.ndarray, ent: np.ndarray, tim: np.ndarray, n_ent: int, n_tim: int, tol: float = 1e-11, max_iter: int = 5000) -> np.ndarray:
    """Remove entity and time means by alternating projections (exact for a balanced panel in one pass)."""
    x = np.array(x, dtype=float, copy=True)
    cnt_e = np.bincount(ent, minlength=n_ent).astype(float)
    cnt_t = np.bincount(tim, minlength=n_tim).astype(float)
    for _ in range(max_iter):
        me = np.bincount(ent, weights=x, minlength=n_ent) / cnt_e
        x -= me[ent]
        mt = np.bincount(tim, weights=x, minlength=n_tim) / cnt_t
        x -= mt[tim]
        if max(np.abs(me).max(), np.abs(mt).max()) < tol:
            break
    return x


def fast_did_estimator(df: pd.DataFrame, y: str):
    """Return a function mapping a household-level treatment vector to the TWFE DiD point estimate."""
    ent_codes, ent_index = pd.factorize(df["lclid"], sort=True)
    tim_codes, _ = pd.factorize(df["month"], sort=True)
    n_ent, n_tim = len(ent_index), int(tim_codes.max()) + 1
    post = df["post"].to_numpy(dtype=float)
    y_dd = two_way_demean(df[y].to_numpy(dtype=float), ent_codes, tim_codes, n_ent, n_tim)

    def estimate(tou_by_household: np.ndarray) -> float:
        d = tou_by_household[ent_codes] * post
        d_dd = two_way_demean(d, ent_codes, tim_codes, n_ent, n_tim)
        return float(d_dd @ y_dd / (d_dd @ d_dd))

    observed = df.groupby("lclid")["tou"].first().reindex(ent_index).to_numpy(dtype=float)
    return estimate, observed


def permutation_test(df: pd.DataFrame, y: str, n_perm: int, seed: int = SEED) -> dict:
    estimate, observed = fast_did_estimator(df, y)
    obs = estimate(observed)
    rng = np.random.default_rng(seed)
    n_treated = int(observed.sum())
    n = len(observed)
    perms = np.empty(n_perm)
    for k in range(n_perm):
        lab = np.zeros(n)
        lab[rng.choice(n, size=n_treated, replace=False)] = 1.0
        perms[k] = estimate(lab)
    p = float(np.mean(np.abs(perms) >= abs(obs)))
    return {
        "observed_fast_estimate": r(obs),
        "n_permutations": int(n_perm),
        "seed": int(seed),
        "p": r(p, 4),
        "permuted_abs_mean": r(float(np.abs(perms).mean())),
        "permuted_abs_p95": r(float(np.quantile(np.abs(perms), 0.95))),
    }


# ---------------------------------------------------------------- balance and heterogeneity


def balance(df: pd.DataFrame) -> dict:
    pre = df[df["post"] == 0]
    out = {}
    for key, (y, label) in OUTCOMES.items():
        hm = pre.groupby("lclid").agg(mean=(y, "mean"), tou=("tou", "first"))
        a, b = hm.loc[hm["tou"] == 1, "mean"], hm.loc[hm["tou"] == 0, "mean"]
        t = stats.ttest_ind(a, b, equal_var=False)
        out[key] = {
            "label": label,
            "mean_ToU": r(float(pre.loc[pre["tou"] == 1, y].mean())),
            "mean_Std": r(float(pre.loc[pre["tou"] == 0, y].mean())),
            "difference": r(float(pre.loc[pre["tou"] == 1, y].mean() - pre.loc[pre["tou"] == 0, y].mean())),
            "welch_t": r(float(t.statistic)),
            "welch_p": r(float(t.pvalue), 6),
            "households_ToU": int(len(a)),
            "households_Std": int(len(b)),
        }
    return out


def heterogeneity(df: pd.DataFrame, cuts: tuple[float, float] | None = None) -> dict:
    pre_use = df[df["post"] == 0].groupby("lclid")["kwh_total"].mean()
    if cuts is None:
        cuts = (float(pre_use.quantile(1 / 3)), float(pre_use.quantile(2 / 3)))
    tercile = pd.cut(pre_use, bins=[-np.inf, cuts[0], cuts[1], np.inf], labels=["T1_low", "T2_mid", "T3_high"])
    d = df.merge(tercile.rename("tercile"), left_on="lclid", right_index=True)
    out = {"cut_points_kwh_month": [r(cuts[0]), r(cuts[1])], "terciles": {}}
    for t in ["T1_low", "T2_mid", "T3_high"]:
        sub = d[d["tercile"] == t]
        out["terciles"][t] = {key: did_outcome(sub, OUTCOMES[key][0]) for key in PRIMARY}
        out["terciles"][t]["households_ToU"] = int(sub.loc[sub["tou"] == 1, "lclid"].nunique())
        out["terciles"][t]["households_Std"] = int(sub.loc[sub["tou"] == 0, "lclid"].nunique())
    return out


# ---------------------------------------------------------------- runs


def analyse(df: pd.DataFrame, permutations: int, fig_dir) -> dict:
    """Run every pre-registered estimate on ``df`` and return one nested dict."""
    out = {"counts": counts(df), "balance": balance(df), "did": {}, "event_study": {}, "randomised": {}, "placebo": {}, "figures": {}}
    for key, (y, label) in OUTCOMES.items():
        out["did"][key] = {"label": label, **did_outcome(df, y)}
        es = event_study(df, y)
        out["event_study"][key] = {"label": label, **es}
        out["figures"][key] = plot_event_study(es, key, label, fig_dir)
        out["randomised"][key] = {"label": label, **ancova(df, y)}
        out["randomised"][key]["same_sign_as_did"] = bool(np.sign(out["randomised"][key]["estimate"]) == np.sign(out["did"][key]["att"]))
    for key in PRIMARY:
        y = OUTCOMES[key][0]
        pdate = placebo_date(df, y)
        perm = permutation_test(df, y, permutations)
        perm["fast_minus_panelols"] = r(perm["observed_fast_estimate"] - out["did"][key]["att"], 6)
        out["placebo"][key] = {"label": OUTCOMES[key][1], "placebo_date": pdate, "permutation": perm}
    out["heterogeneity"] = heterogeneity(df)
    return out


def _split(res: dict) -> dict[str, dict]:
    return {
        "balance": res["balance"],
        "did": res["did"],
        "event_study": res["event_study"],
        "randomised": res["randomised"],
        "placebo": res["placebo"],
        "heterogeneity": res["heterogeneity"],
        "counts": res["counts"],
    }


def run_full(permutations: int = 500, deviation: str | None = None) -> int:
    st = prereg.require_frozen(deviation)
    t0 = time.time()
    df = load_panel()
    res = analyse(df, permutations, DOCS)
    for name, obj in _split(res).items():
        write_json(RESULTS / f"{name}.json", obj)
    write_json(
        RESULTS / "analysis_meta.json",
        {"preregistration_sha256": st["recorded_sha256"], "deviation": st.get("deviation"), "permutations": permutations, "seed": SEED, "figures": res["figures"]},
    )
    write_json(RUNS / "analyse_timing.json", {"seconds": round(time.time() - t0, 1)})
    print(f"analysed {res['counts']} in {time.time() - t0:.0f} s")
    for key in PRIMARY:
        d = res["did"][key]
        print(f"{key}: ATT {d['att']} [{d['ci_low']}, {d['ci_high']}] = {d['att_pct_of_pre_mean']} % of the ToU 2012 mean, permutation p {res['placebo'][key]['permutation']['p']}")
    return 0


def run_sensitivity_timeframe(deviation: str | None = None) -> int:
    """DiD and the check estimator on the panel built with the schedule shifted to GMT during British Summer
    Time. A documented stretch outside the pre-registered Results table (DEVIATIONS.md D1)."""
    from .common import PANEL_BST_SHIFT

    prereg.require_frozen(deviation)
    if not PANEL_BST_SHIFT.exists():
        raise SystemExit("run `python -m lcl_dtou_causal panel --variant bst-shift` first")
    base = load_panel()
    shifted = load_panel(PANEL_BST_SHIFT)
    out = {
        "what": "schedule re-labelled to GMT during British Summer Time before the join, everything else as pre-registered",
        "counts_shifted": counts(shifted),
        "outcomes": {},
    }
    for key, (y, label) in OUTCOMES.items():
        out["outcomes"][key] = {
            "label": label,
            "pre_registered_did": {k: did_outcome(base, y)[k] for k in ("att", "ci_low", "ci_high", "att_pct_of_pre_mean")},
            "shifted_did": did_outcome(shifted, y),
            "shifted_ancova": ancova(shifted, y),
        }
    write_json(RESULTS / "sensitivity_timeframe.json", out)
    for key in PRIMARY:
        o = out["outcomes"][key]
        print(f"{key}: pre-registered ATT {o['pre_registered_did']['att']} shifted ATT {o['shifted_did']['att']} [{o['shifted_did']['ci_low']}, {o['shifted_did']['ci_high']}]")
    return 0


def run_smoke(n_tou: int = 150, n_std: int = 150, permutations: int = 100) -> int:
    st = prereg.require_frozen()
    t0 = time.time()
    df = stratified_sample(load_panel(), n_tou, n_std)
    res = analyse(df, permutations, RUNS / "smoke")
    out = {
        "smoke_ok": "yes",
        "sample": {"households_ToU": n_tou, "households_Std": n_std, "seed": SEED, "permutations": permutations},
        "preregistration_sha256": st["recorded_sha256"],
        **_split(res),
    }
    out["figures"] = {k: str(v) for k, v in res["figures"].items()}
    write_json(RESULTS / "smoke.json", out)
    write_json(RUNS / "smoke_timing.json", {"seconds": round(time.time() - t0, 1)})
    print(f"smoke ok, {res['counts']['household_months']} household-months, {time.time() - t0:.0f} s")
    return 0
