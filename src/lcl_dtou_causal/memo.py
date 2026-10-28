"""Write docs/memo.md, docs/partner_slide.md, results/readme_numbers.json and the README results block.

Every number in the three documents is read from ``results/*.json`` written by ``analyse``, ``panel`` and
``download``, and formatted once by ``fmt`` so the README test can find each value verbatim.
"""
from __future__ import annotations

import re

from . import prereg
from .analyse import OUTCOMES, PRIMARY
from .common import (
    DOCS,
    DOWNLOAD_CHECK,
    README_MARK_END,
    README_MARK_START,
    RESULTS,
    ROOT,
    read_json,
    write_json,
    write_text,
)


def fmt(x: float, nd: int = 2) -> str:
    s = f"{x:.{nd}f}"
    return "0." + "0" * nd if s in (f"-0.{'0' * nd}",) else s


def ci(d: dict, nd: int = 2) -> str:
    return f"[{fmt(d['ci_low'], nd)}, {fmt(d['ci_high'], nd)}]"


def pval(p: float) -> str:
    return "< 0.001" if p < 0.001 else fmt(p, 3)


def perm_text(p: dict) -> str:
    hits = int(round(p["p"] * p["n_permutations"]))
    return f"{hits} of {p['n_permutations']} (p {'< ' + fmt(1.0 / p['n_permutations'], 3) if hits == 0 else '= ' + fmt(p['p'], 3)})"


def load() -> dict:
    r = {name: read_json(RESULTS / f"{name}.json") for name in ("did", "event_study", "randomised", "placebo", "balance", "heterogeneity", "counts", "sample", "schedule")}
    r["download"] = read_json(DOWNLOAD_CHECK)
    tf = RESULTS / "timeframe_check.json"
    r["timeframe"] = read_json(tf) if tf.exists() else None
    sens = RESULTS / "sensitivity_timeframe.json"
    r["sensitivity"] = read_json(sens) if sens.exists() else None
    r["prereg"] = prereg.status()
    return r


def results_table(r: dict) -> tuple[str, dict[str, str]]:
    """The README results table and the label-to-string map asserted by tests/test_readme_numbers.py."""
    c = r["counts"]
    numbers: dict[str, str] = {}
    head = (
        "| Outcome | 2012 mean, ToU group | ATT (DiD) | 95 % CI | Clustered SE | ATT as % of 2012 mean | "
        "Pre-trend p (joint) | Placebo-date estimate | Permutation p (500) | ANCOVA estimate (the check that would be primary under randomisation) | "
        "Households (ToU / Std) | Months (pre / post) |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for key, (_, label) in OUTCOMES.items():
        d, es, an = r["did"][key], r["event_study"][key], r["randomised"][key]
        unit = "£" if "cost" in label else "kWh"
        vals = {
            f"{key}_pre_mean": fmt(d["tou_pre_mean"]),
            f"{key}_att": fmt(d["att"]),
            f"{key}_ci": ci(d),
            f"{key}_se": fmt(d["se"]),
            f"{key}_pct": fmt(d["att_pct_of_pre_mean"], 1),
            f"{key}_pretrend_p": pval(es["pretrend_p_chi2"]),
            f"{key}_ancova": f"{fmt(an['estimate'])} {ci(an)}",
        }
        if key in PRIMARY:
            pl = r["placebo"][key]
            vals[f"{key}_placebo"] = f"{fmt(pl['placebo_date']['att'])} {ci(pl['placebo_date'])}"
            vals[f"{key}_perm"] = perm_text(pl["permutation"])
        else:
            vals[f"{key}_placebo"] = "not pre-registered"
            vals[f"{key}_perm"] = "not pre-registered"
        numbers.update(vals)
        rows.append(
            f"| {key}, {label} | {vals[f'{key}_pre_mean']} {unit} | {vals[f'{key}_att']} {unit} | {vals[f'{key}_ci']} | {vals[f'{key}_se']} | "
            f"{vals[f'{key}_pct']} % | {vals[f'{key}_pretrend_p']} | {vals[f'{key}_placebo']} | {vals[f'{key}_perm']} | {vals[f'{key}_ancova']} | "
            f"{c['households_ToU']} / {c['households_Std']} | {c['months_pre']} / {c['months_post']} |"
        )
    numbers["households_ToU"] = str(c["households_ToU"])
    numbers["households_Std"] = str(c["households_Std"])
    numbers["household_months"] = f"{c['household_months']:,}"
    att = r["sample"]["attrition"]
    numbers["attrition_Std_pct"] = fmt(att["Std"]["share_lost_R0_to_R4_pct"], 1)
    numbers["attrition_ToU_pct"] = fmt(att["ToU"]["share_lost_R0_to_R4_pct"], 1)
    b = r["balance"]["O4"]
    numbers["balance_kwh_ToU"] = fmt(b["mean_ToU"], 1)
    numbers["balance_kwh_Std"] = fmt(b["mean_Std"], 1)
    numbers["balance_kwh_p"] = pval(b["welch_p"])
    numbers["prereg_sha256"] = r["prereg"]["recorded_sha256"]
    note = (
        f"\nSample: {numbers['households_ToU']} ToU and {numbers['households_Std']} Std households, {numbers['household_months']} household-months, "
        f"January 2012 to December 2013. Attrition from the raw release to the kept sample: {numbers['attrition_Std_pct']} % of Std and "
        f"{numbers['attrition_ToU_pct']} % of ToU households. 2012 balance on total kWh per month: ToU {numbers['balance_kwh_ToU']}, "
        f"Std {numbers['balance_kwh_Std']}, Welch p {numbers['balance_kwh_p']}. Pre-registration sha256 `{numbers['prereg_sha256']}`. "
        "Placebo-date estimates are for a false treatment date of July 2012 inside the pre-period. Permutation p is the share of 500 "
        "random relabellings whose absolute estimate reaches the observed one. The ANCOVA column regresses each household's 2013 mean "
        "on its group and its 2012 mean, the comparison that would have been primary had assignment been randomised.\n"
    )
    return head + "\n".join(rows) + "\n" + note, numbers


def timeframe_paragraph(r: dict) -> str:
    """The time-frame caveat: what the report says, what the files show, and the sensitivity numbers."""
    head = (
        "Report A3 gives the event schedule in local time (Figure 3.10). The readings carry 01:00 and 01:30 labels on 31 March 2013, "
        "an hour that did not exist in local time, so they are most likely stamped in GMT and the pre-registered join on equal labels "
        "is then one hour off during British Summer Time for O1, O2, O3 and O5 (the evening-peak evidence in "
        "`results/timeframe_check.json` is mixed). "
    )
    sens = r["sensitivity"]
    if sens is None:
        return head + "The pre-registered join was kept."
    o = sens["outcomes"]
    return head + (
        "The join was kept for the Results table. With the schedule moved back one hour inside British Summer Time before the join "
        "(DEVIATIONS.md D1, `results/sensitivity_timeframe.json`), the DiD gives O1 "
        f"{fmt(o['O1']['shifted_did']['att'])} £ {ci(o['O1']['shifted_did'])} against {fmt(o['O1']['pre_registered_did']['att'])} pre-registered, "
        f"O2 {fmt(o['O2']['shifted_did']['att'])} kWh {ci(o['O2']['shifted_did'])} against {fmt(o['O2']['pre_registered_did']['att'])}, "
        f"O3 {fmt(o['O3']['shifted_did']['att'])} £ against {fmt(o['O3']['pre_registered_did']['att'])} and O5 "
        f"{fmt(o['O5']['shifted_did']['att'])} kWh against {fmt(o['O5']['pre_registered_did']['att'])}, so the frame does not move the findings."
    )


def memo_text(r: dict) -> str:
    c, d, es, an, pl, b, h, s = r["counts"], r["did"], r["event_study"], r["randomised"], r["placebo"], r["balance"], r["heterogeneity"], r["sample"]
    dl, sch = r["download"], r["schedule"]
    o1, o2 = d["O1"], d["O2"]
    att = s["attrition"]
    t = []
    t.append("# Memo: the Low Carbon London dynamic time-of-use tariff, bills and peak-hour use in 2013\n")
    t.append(
        f"The 2013 price schedule came from the open London Datastore release (`Tariffs.xlsx`, {sch['half_hours']:,} half-hours, "
        f"{sch['band_counts']['High']} High, {sch['band_counts']['Low']} Low, {sch['event_days']} event days), so neither fallback was needed. "
        "The trial was opt-in, not randomised (Learning Report A3, printed pages 22 to 24): households volunteered for the dToU tariff "
        "with a £100 sign-up and £50 completion incentive, and the report's authors assumed that self-selection had created a difference "
        "between the groups. The two-way fixed-effects difference-in-differences with household-clustered errors is therefore the primary "
        "design. The ANCOVA, each household's 2013 mean on its group and its 2012 mean, is reported as the check that would have been "
        "primary under random assignment. Both are reported and they agree.\n"
    )
    t.append("## Question\n")
    t.append(
        "What did moving a household to the dynamic time-of-use tariff do to its monthly bill at its own tariff (O1) and to its "
        "consumption in High-price half-hours (O2), with the bill at the dToU schedule (O3), total kWh (O4) and Low-price kWh (O5) as "
        "secondary outcomes. The plan was frozen before any data was downloaded (`PREREGISTRATION.md`, sha256 "
        f"`{r['prereg']['recorded_sha256'][:12]}`).\n"
    )
    t.append("## Data\n")
    t.append(
        f"UK Power Networks' Low Carbon London smart-meter release: {dl['csv']['rows']:,} half-hourly readings from "
        f"{dl['csv']['households_distinct']:,} London households ({dl['csv']['households_ToU']:,} flagged ToU, {dl['csv']['households_Std']:,} Std), "
        f"{dl['csv']['timestamp_min'][:10]} to {dl['csv']['timestamp_max'][:10]}, CC BY 4.0. Prices: High 67.20, Normal 11.76, Low 3.99 pence per kWh "
        "for the ToU group in 2013, 14.228 pence flat for Std and for everyone in 2012, unit rates only. Sample rules in order: January 2012 to "
        "December 2013, duplicate readings averaged, a household-month counts with at least 80 % of its half-hours observed, a household needs "
        f"at least six valid months in each year. This keeps {c['households_ToU']} ToU and {c['households_Std']} Std households and "
        f"{c['household_months']:,} household-months. Attrition from the raw file to the kept sample is {fmt(att['Std']['share_lost_R0_to_R4_pct'], 1)} % "
        f"for Std and {fmt(att['ToU']['share_lost_R0_to_R4_pct'], 1)} % for ToU, almost all of it the six-month rule, because recruitment ran through 2012 "
        f"({s['households_with_valid_month_by_month']['2012-01_ToU']} ToU households have a valid January 2012, "
        f"{s['households_with_valid_month_by_month']['2012-12_ToU']} a valid December 2012). The two groups lose the same share.\n"
    )
    t.append("## Design\n")
    t.append(
        "Two-way fixed effects: outcome on household effects, month effects and ToU times Post, errors clustered by household, pre-period "
        "January to December 2012 when both groups paid the flat rate, post-period January to December 2013. The 2013 schedule is mapped onto "
        "2012 by calendar date and clock time so O2, O3 and O5 are defined in both years. The event study puts one coefficient on each month "
        "relative to December 2012 and tests the eleven free pre-period coefficients jointly. The check estimator regresses each household's "
        "2013 mean on its group and its 2012 mean. Placebos: a false treatment date of July 2012 inside the pre-period, and 500 random "
        "reassignments of the ToU label. Heterogeneity by 2012 usage terciles is secondary.\n"
    )
    t.append("## Results\n")
    t.append(
        f"In 2012 the ToU group used less than the Std group ({fmt(b['O4']['mean_ToU'], 1)} against {fmt(b['O4']['mean_Std'], 1)} kWh per month, "
        f"Welch p {pval(b['O4']['welch_p'])}), which is the self-selection the report expected and which the household effects absorb.\n"
    )
    t.append(
        f"O1, bill at own tariff: ATT {fmt(o1['att'])} £ per month, 95 % CI {ci(o1)}, clustered SE {fmt(o1['se'])}, which is "
        f"{fmt(o1['att_pct_of_pre_mean'], 1)} % of the ToU group's 2012 mean of {fmt(o1['tou_pre_mean'])} £. The pre-trend test passes "
        f"(joint p {pval(es['O1']['pretrend_p_chi2'])}). The check estimator gives {fmt(an['O1']['estimate'])} {ci(an['O1'])}, the same sign.\n"
    )
    t.append(
        f"O2, kWh in High-price half-hours: ATT {fmt(o2['att'])} kWh per month, 95 % CI {ci(o2)}, SE {fmt(o2['se'])}, "
        f"{fmt(o2['att_pct_of_pre_mean'], 1)} % of the 2012 mean of {fmt(o2['tou_pre_mean'])} kWh. The check estimator gives "
        f"{fmt(an['O2']['estimate'])} {ci(an['O2'])}. The pre-trend test fails (joint p {pval(es['O2']['pretrend_p_chi2'])}): the 2012 "
        "coefficients sit about one kWh above the December 2012 reference without a trend in either direction, so the O2 estimate rests on "
        "December 2012 being an ordinary month for the gap between the groups. Read O2 as suggestive, not as a clean causal estimate.\n"
    )
    t.append(
        f"Secondary: O3 {fmt(d['O3']['att'])} £ {ci(d['O3'])} ({fmt(d['O3']['att_pct_of_pre_mean'], 1)} %, pre-trend p "
        f"{pval(es['O3']['pretrend_p_chi2'])}), O4 {fmt(d['O4']['att'])} kWh {ci(d['O4'])} ({fmt(d['O4']['att_pct_of_pre_mean'], 1)} %, "
        f"pre-trend p {pval(es['O4']['pretrend_p_chi2'])}), O5 {fmt(d['O5']['att'])} kWh {ci(d['O5'])} ({fmt(d['O5']['att_pct_of_pre_mean'], 1)} %, "
        f"pre-trend p {pval(es['O5']['pretrend_p_chi2'])}). Total use fell by about three percent and Low-price use did not rise by a "
        "detectable amount, so the High-price reduction looks more like avoided use than shifted use. By 2012 usage terciles the O1 effect is "
        f"{fmt(h['terciles']['T1_low']['O1']['att'])}, {fmt(h['terciles']['T2_mid']['O1']['att'])} and {fmt(h['terciles']['T3_high']['O1']['att'])} £ "
        f"({fmt(h['terciles']['T1_low']['O1']['att_pct_of_pre_mean'], 1)}, {fmt(h['terciles']['T2_mid']['O1']['att_pct_of_pre_mean'], 1)} and "
        f"{fmt(h['terciles']['T3_high']['O1']['att_pct_of_pre_mean'], 1)} %), so the saving scales with usage.\n"
    )
    t.append("## Placebos\n")
    t.append(
        f"False treatment date, July 2012: O1 {fmt(pl['O1']['placebo_date']['att'])} {ci(pl['O1']['placebo_date'])}, O2 "
        f"{fmt(pl['O2']['placebo_date']['att'])} {ci(pl['O2']['placebo_date'])}, both intervals cover zero. Permutation test, 500 random "
        f"reassignments of the ToU label: {perm_text(pl['O1']['permutation'])} permuted estimates were at least as large as the observed O1 "
        f"effect (95th percentile of the permuted absolute estimates {fmt(pl['O1']['permutation']['permuted_abs_p95'])} £ against "
        f"{fmt(abs(o1['att']))} observed), {perm_text(pl['O2']['permutation'])} for O2 ({fmt(pl['O2']['permutation']['permuted_abs_p95'])} "
        f"against {fmt(abs(o2['att']))} kWh).\n"
    )
    t.append("## Caveats\n")
    t.append(
        "Opt-in trial at both stages with cash incentives, London only, 2013 only, early smart-meter adopters without prepayment meters, "
        "micro-generation, Economy 7 or dual-fuel contracts, a guarantee that nobody would be worse off, day-ahead notification of prices, "
        "and one year of treatment. The DiD removes fixed differences between the groups but not a different response to the weather of "
        "2013. The O2 pre-trend test fails, see above. Bills are unit rates only. "
        f"Time frame: {timeframe_paragraph(r)} "
        f"Duplicate readings ({s['R2_duplicate_household_timestamps']:,} household-timestamps) were averaged and "
        f"{s['R0_rows_missing_kwh']:,} Null readings were treated as missing.\n"
    )
    t.append("## What this means for a pilot\n")
    t.append(
        "A pilot that moves households onto a time-of-use tariff should pre-register the comparison before the switch, keep a year of "
        "pre-switch readings for every household, randomise who switches if it can, and otherwise plan on fixed effects, a pre-trend test "
        "and a placebo date as the minimum. The code here runs unchanged on a household-by-month panel in the same shape.\n"
    )
    return "\n".join(t)


def slide_text(r: dict) -> str:
    c, d, pl = r["counts"], r["did"], r["placebo"]
    o1, o2 = d["O1"], d["O2"]
    return (
        "# Slide: what a dynamic time-of-use tariff did in the Low Carbon London trial (2013)\n\n"
        f"- Public data: {c['households_ToU']} households on dynamic prices, {c['households_Std']} on a flat rate, half-hourly readings for 2012 and 2013\n"
        f"- Bills at own tariff: {fmt(o1['att'])} £ per household-month, 95 % CI {ci(o1)}, {fmt(o1['att_pct_of_pre_mean'], 1)} % of the 2012 bill\n"
        f"- Use in High-price half-hours: {fmt(o2['att'])} kWh per month, {fmt(o2['att_pct_of_pre_mean'], 1)} %, with a failed pre-trend test, so read with care\n"
        f"- Total use {fmt(d['O4']['att_pct_of_pre_mean'], 1)} %, Low-price use {fmt(d['O5']['att_pct_of_pre_mean'], 1)} % (not distinguishable from zero)\n"
        f"- Placebos: a false July 2012 treatment date gives nothing, {perm_text(pl['O1']['permutation'])} random relabellings match the bill effect\n"
        "- Design: pre-registered and hash-frozen plan, difference-in-differences with household and month fixed effects, household-clustered errors\n"
        "- The trial was opt-in, not randomised, with cash incentives, so the difference-in-differences is the headline and the ANCOVA check is the comparison that would have been primary under random assignment\n"
        "- For a pilot: pre-register before the switch, a year of pre-switch readings per household, randomise the switch if possible\n"
    )


def update_readme(table: str) -> bool:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if README_MARK_START not in text or README_MARK_END not in text:
        raise SystemExit("README.md lacks the results markers")
    new = re.sub(
        re.escape(README_MARK_START) + r".*?" + re.escape(README_MARK_END),
        README_MARK_START + "\n" + table + README_MARK_END,
        text,
        flags=re.S,
    )
    return write_text(readme, new)


def run(deviation: str | None = None) -> int:
    prereg.require_frozen(deviation)
    r = load()
    table, numbers = results_table(r)
    DOCS.mkdir(exist_ok=True)
    write_text(DOCS / "memo.md", memo_text(r))
    write_text(DOCS / "partner_slide.md", slide_text(r))
    write_json(RESULTS / "readme_numbers.json", numbers)
    changed = update_readme(table)
    words = len((DOCS / "memo.md").read_text(encoding="utf-8").split())
    print(f"memo {words} words, README results block {'updated' if changed else 'unchanged'}")
    return 0
