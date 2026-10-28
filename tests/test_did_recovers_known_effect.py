"""An injected 10 % effect on a synthetic panel with self-selected groups is recovered within the 95 % CI,
and the fast permutation estimator equals PanelOLS on the observed assignment."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import synthetic_panel  # noqa: E402

from lcl_dtou_causal.analyse import ancova, did_outcome, event_study, fast_did_estimator  # noqa: E402


@pytest.fixture(scope="module")
def panel():
    return synthetic_panel(n_tou=120, n_std=280, effect_pct=-10.0, selection_pct=20.0, seed=7)


def test_did_recovers_the_injected_effect(panel):
    df, true_att = panel
    res = did_outcome(df, "kwh_total")
    assert res["ci_low"] <= true_att <= res["ci_high"], (res, true_att)
    assert -13.0 < res["att_pct_of_pre_mean"] < -7.0
    assert res["n_households"] == 400


def test_fast_estimator_matches_panelols(panel):
    df, _ = panel
    res = did_outcome(df, "kwh_total")
    estimate, observed = fast_did_estimator(df, "kwh_total")
    assert estimate(observed) == pytest.approx(res["att"], abs=1e-4)


def test_event_study_post_coefficients_are_negative_and_pre_are_flat(panel):
    df, _ = panel
    es = event_study(df, "kwh_total")
    post = [c["coef"] for c in es["coefficients"] if c["month"] >= "2013-01"]
    pre = [c["coef"] for c in es["coefficients"] if c["month"] < "2013-01"]
    assert len(pre) == 12 and len(post) == 12
    assert all(c < 0 for c in post)
    assert es["pretrend_p_chi2"] > 0.01


def test_ancova_has_the_same_sign(panel):
    df, true_att = panel
    res = ancova(df, "kwh_total")
    assert res["estimate"] < 0
    assert res["ci_low"] <= true_att <= res["ci_high"]
