# Memo: the Low Carbon London dynamic time-of-use tariff, bills and peak-hour use in 2013

The 2013 price schedule came from the open London Datastore release (`Tariffs.xlsx`, 17,520 half-hours, 788 High, 1660 Low, 153 event days), so neither fallback was needed. The trial was opt-in, not randomised (Learning Report A3, printed pages 22 to 24): households volunteered for the dToU tariff with a £100 sign-up and £50 completion incentive, and the report's authors assumed that self-selection had created a difference between the groups. The two-way fixed-effects difference-in-differences with household-clustered errors is therefore the primary design. The ANCOVA, each household's 2013 mean on its group and its 2012 mean, is reported as the check that would have been primary under random assignment. Both are reported and they agree.

## Question

What did moving a household to the dynamic time-of-use tariff do to its monthly bill at its own tariff (O1) and to its consumption in High-price half-hours (O2), with the bill at the dToU schedule (O3), total kWh (O4) and Low-price kWh (O5) as secondary outcomes. The plan was frozen before any data was downloaded (`PREREGISTRATION.md`, sha256 `973b734c7e04`).

## Data

UK Power Networks' Low Carbon London smart-meter release: 167,932,474 half-hourly readings from 5,566 London households (1,123 flagged ToU, 4,443 Std), 2011-11-23 to 2014-02-28, CC BY 4.0. Prices: High 67.20, Normal 11.76, Low 3.99 pence per kWh for the ToU group in 2013, 14.228 pence flat for Std and for everyone in 2012, unit rates only. Sample rules in order: January 2012 to December 2013, duplicate readings averaged, a household-month counts with at least 80 % of its half-hours observed, a household needs at least six valid months in each year. This keeps 862 ToU and 3389 Std households and 84,713 household-months. Attrition from the raw file to the kept sample is 23.7 % for Std and 23.2 % for ToU, almost all of it the six-month rule, because recruitment ran through 2012 (57 ToU households have a valid January 2012, 1111 a valid December 2012). The two groups lose the same share.

## Design

Two-way fixed effects: outcome on household effects, month effects and ToU times Post, errors clustered by household, pre-period January to December 2012 when both groups paid the flat rate, post-period January to December 2013. The 2013 schedule is mapped onto 2012 by calendar date and clock time so O2, O3 and O5 are defined in both years. The event study puts one coefficient on each month relative to December 2012 and tests the eleven free pre-period coefficients jointly. The check estimator regresses each household's 2013 mean on its group and its 2012 mean. Placebos: a false treatment date of July 2012 inside the pre-period, and 500 random reassignments of the ToU label. Heterogeneity by 2012 usage terciles is secondary.

## Results

In 2012 the ToU group used less than the Std group (279.4 against 300.7 kWh per month, Welch p 0.002), which is the self-selection the report expected and which the household effects absorb.

O1, bill at own tariff: ATT -2.40 £ per month, 95 % CI [-3.06, -1.73], clustered SE 0.34, which is -6.0 % of the ToU group's 2012 mean of 39.76 £. The pre-trend test passes (joint p 0.206). The check estimator gives -2.22 [-2.85, -1.59], the same sign.

O2, kWh in High-price half-hours: ATT -1.46 kWh per month, 95 % CI [-1.77, -1.15], SE 0.16, -10.0 % of the 2012 mean of 14.57 kWh. The check estimator gives -1.32 [-1.62, -1.02]. The pre-trend test fails (joint p 0.002): the 2012 coefficients sit about one kWh above the December 2012 reference without a trend in either direction, so the O2 estimate rests on December 2012 being an ordinary month for the gap between the groups. Read O2 as suggestive, not as a clean causal estimate.

Secondary: O3 -1.94 £ [-2.60, -1.28] (-5.0 %, pre-trend p 0.018), O4 -9.28 kWh [-13.91, -4.65] (-3.3 %, pre-trend p 0.209), O5 0.45 kWh [-0.09, 1.00] (1.9 %, pre-trend p 0.068). Total use fell by about three percent and Low-price use did not rise by a detectable amount, so the High-price reduction looks more like avoided use than shifted use. By 2012 usage terciles the O1 effect is -1.20, -1.56 and -4.51 £ (-6.7, -4.5 and -6.4 %), so the saving scales with usage.

## Placebos

False treatment date, July 2012: O1 0.42 [-0.52, 1.35], O2 0.54 [-0.08, 1.17], both intervals cover zero. Permutation test, 500 random reassignments of the ToU label: 0 of 500 (p < 0.002) permuted estimates were at least as large as the observed O1 effect (95th percentile of the permuted absolute estimates 0.77 £ against 2.40 observed), 0 of 500 (p < 0.002) for O2 (0.34 against 1.46 kWh).

## Caveats

Opt-in trial at both stages with cash incentives, London only, 2013 only, early smart-meter adopters without prepayment meters, micro-generation, Economy 7 or dual-fuel contracts, a guarantee that nobody would be worse off, day-ahead notification of prices, and one year of treatment. The DiD removes fixed differences between the groups but not a different response to the weather of 2013. The O2 pre-trend test fails, see above. Bills are unit rates only. Time frame: Report A3 gives the event schedule in local time (Figure 3.10). The readings carry 01:00 and 01:30 labels on 31 March 2013, an hour that did not exist in local time, so they are most likely stamped in GMT and the pre-registered join on equal labels is then one hour off during British Summer Time for O1, O2, O3 and O5 (the evening-peak evidence in `results/timeframe_check.json` is mixed). The join was kept for the Results table. With the schedule moved back one hour inside British Summer Time before the join (DEVIATIONS.md D1, `results/sensitivity_timeframe.json`), the DiD gives O1 -2.39 £ [-3.06, -1.73] against -2.40 pre-registered, O2 -1.46 kWh [-1.77, -1.15] against -1.46, O3 -1.94 £ against -1.94 and O5 0.45 kWh against 0.45, so the frame does not move the findings. Duplicate readings (105,173 household-timestamps) were averaged and 5,560 Null readings were treated as missing.

## What this means for a pilot

A pilot that moves households onto a time-of-use tariff should pre-register the comparison before the switch, keep a year of pre-switch readings for every household, randomise who switches if it can, and otherwise plan on fixed effects, a pre-trend test and a placebo date as the minimum. The code here runs unchanged on a household-by-month panel in the same shape.
