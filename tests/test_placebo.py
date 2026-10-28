"""Placebo date and permutation test behave as expected on synthetic panels with and without an effect."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synth import synthetic_panel  # noqa: E402

from lcl_dtou_causal.analyse import permutation_test, placebo_date  # noqa: E402


def test_placebo_date_covers_zero_without_an_effect():
    df, _ = synthetic_panel(effect_pct=0.0, seed=11)
    res = placebo_date(df, "kwh_total")
    assert res["covers_zero"] is True
    assert res["placebo_month"] == "2012-07"


def test_placebo_date_covers_zero_even_with_a_post_effect():
    df, _ = synthetic_panel(effect_pct=-10.0, seed=11)
    res = placebo_date(df, "kwh_total")
    assert res["covers_zero"] is True


def test_permutation_p_is_small_with_an_effect_and_large_without():
    with_effect, _ = synthetic_panel(effect_pct=-10.0, seed=3)
    without, _ = synthetic_panel(effect_pct=0.0, seed=3)
    p_effect = permutation_test(with_effect, "kwh_total", n_perm=100, seed=5)["p"]
    p_null = permutation_test(without, "kwh_total", n_perm=100, seed=5)["p"]
    assert p_effect <= 0.01
    assert p_null > 0.05
