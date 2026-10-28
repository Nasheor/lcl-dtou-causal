# Pre-registered analysis plan: the Low Carbon London dynamic time-of-use tariff, 2013

Written on 2026-10-28 before any data file was downloaded and before any analysis ran. The sha256 of
this file is recorded in `results/preregistration_sha256.json` by `python -m lcl_dtou_causal prereg freeze`
and committed on its own. Every analysis command checks that hash first. Anything that changes after
the freeze is recorded in `DEVIATIONS.md` under the rule in section 12.

## 1. Question

What was the effect of moving a London household to the dynamic time-of-use (dToU) tariff during 2013
on its monthly electricity cost at its own tariff and on its consumption in High-price half-hours, with
three secondary outcomes listed in section 6.

## 2. Data source and the checks to record before any analysis

Source: "SmartMeter Energy Consumption Data in London Households", London Datastore, UK Power Networks
(Low Carbon London), CC BY 4.0 (see `LICENCE_CHECK.md`). Files: `Partitioned LCL Data.zip` (168 CSV
files of one million half-hourly rows, expected columns `LCLid`, `stdorToU`, `DateTime`,
`KWH/hh (per half hour)`) and `Tariffs.xlsx` ("Time of Use Tariffs for 2013").

`python -m lcl_dtou_causal download` writes `results/download_check.json` with:

- the byte count of each file against the server's `Content-Length` and the sha256 of each file,
- whether `stdorToU` is present and its distinct values (expected `Std` and `ToU`),
- the number of distinct `LCLid` values (expected near 5,567) and the number flagged `ToU` (expected
  near 1,100, Report A3 gives 1,119 recruited),
- the first and last timestamp (expected November 2011 to February 2014),
- whether `Tariffs.xlsx` carries a half-hourly 2013 schedule with the bands High, Normal and Low
  (expected 17,520 half-hours), the sheet and column names read, and the count of half-hours per band,
- the timestamp conventions found: alignment to the half-hour, duplicated household-timestamps, the
  half-hours around the clock changes on 25 March 2012, 28 October 2012, 31 March 2013 and 27 October 2013.

Schedule route, in order: (1) the open release's `Tariffs.xlsx`, (2) UK Data Service study SN 7857, which
needs Avinash's registration and stops the unit, (3) the reduced design in which the outcomes are total
kWh and kWh in a fixed 16:00 to 20:00 evening window and no cost effect is estimated. The memo says in its
first paragraph which route was used.

Prices to verify, not facts until the schedule file is read: High 67.20, Normal 11.76 and Low 3.99 pence
per kWh for the dToU group, 14.228 pence per kWh flat for the Std group. Sources: Report A3, printed pages
5 and 32, and the Datastore description. If `Tariffs.xlsx` carries prices they must agree with these.
Only unit rates are used. No standing charge, VAT or levy is applied, because the comparison is between
the two unit-rate structures the trial charged and everything else was the same for both groups.

The schedule and the readings carry the same publisher's half-hour labels, so they are joined on equal
timestamps. If the readings turn out to be labelled by the end of the half-hour rather than the start, the
join is still on equal labels, because the schedule file uses the same labelling.

## 3. What the trial documentation says about assignment

This is written before the freeze because it decides which estimator is primary. The unit's build
specification expected that assignment to the dToU tariff was randomised, in which case the simple
post-period comparison with a pre-period covariate would be primary and the difference-in-differences
would be the robustness design.

Low Carbon London Learning Report A3 (Schofield, Carmichael, Tindemans, Woolf and Bilton, Imperial College
London, 30 June 2014, printed pages 22 to 25) says otherwise. The trial was "opt-in" at both stages.
Households were first recruited into the smart-meter programme, then "secondary recruitment into the
treatment group" took volunteers from those households with incentives of £100 for signing up and £50 for
staying on the tariff, and the authors write that "because secondary recruitment was also opt-in ... it
was assumed that self selection had created a natural difference between the populations of the dTOU and
nonTOU groups". Table 3.1 gives 4,414 nonTOU and 1,119 dTOU households at the start, 4,068 and 1,044 at the
end (attrition 7.8 % and 6.7 %).

The plan therefore treats the two groups as self-selected. The two-way fixed effects
difference-in-differences, which removes every time-invariant difference between households, is the
primary estimator. The post-period comparison with the pre-period mean as a covariate is kept, as the spec
asks, and reported as the secondary check that would have been primary under randomised assignment. The
parallel-trends assumption behind the primary estimator is tested with the pre-period event-study
coefficients and the placebo date in section 8. The memo and the README state this plainly.

## 4. Sample rules

Applied in this order. `results/sample.json` records the number of households and household-months by
group after each rule, and attrition by group as defined at the end of this section.

- R0. Every row with a parseable timestamp. A row whose reading is not numeric (the release writes `Null`)
  counts as an absent half-hour.
- R1. Calendar window January 2012 to December 2013. November and December 2011 are excluded as ramp-up,
  January and February 2014 as run-down.
- R2. Duplicate readings for the same household and timestamp are collapsed to their mean and count as one
  observed half-hour. Their number is recorded.
- R3. A household-month is valid only when at least 80 % of its half-hours are observed, the expected
  count being the number of days in the month times 48.
- R4. A household is kept only with at least six valid months in 2012 and at least six valid months in
  2013. This is the "observed in both years" rule.
- R5. A household's group is its `stdorToU` value. A household that carries both values is dropped and
  counted.

Attrition by group: the number of households present under R0, with at least one valid month under R3,
and kept under R4, by group, and for each calendar month the number of households with a valid month,
by group. The memo discusses the attrition figures and whether they differ between groups.

## 5. Groups and periods

Treated: households flagged `ToU`. Control: households flagged `Std`. Pre-period: January to December
2012, when both groups paid the flat rate. Post-period: January to December 2013, when the dToU prices
applied to the treated group. The treatment date is 1 January 2013. The unit of analysis is the
household-month, unweighted.

## 6. Outcomes, in order of importance

Costs are in pounds: the sum over the month's observed half-hours of kWh times the pence rate, divided
by 100. Band quantities use the 2013 schedule. For 2012 months the 2013 schedule is mapped by calendar
date and clock half-hour, so 5 March 2012 at 17:00 takes the band of 5 March 2013 at 17:00. The
half-hours of 29 February 2012 take the bands of 28 February 2013 at the same clock times.

- O1, primary: monthly cost at the household's own tariff. ToU households in 2013 at the dToU schedule
  prices, ToU households in 2012 at the flat rate, Std households at the flat rate in both years. The
  effect on O1 is the effect of the tariff on the bill, which includes the price structure itself and the
  household's response to it.
- O2, primary: monthly kWh in High-price half-hours, the schedule applied to both groups and both years.
- O3: monthly cost at the dToU schedule for both groups and both years.
- O4: total monthly kWh.
- O5: monthly kWh in Low-price half-hours.

No multiple-testing adjustment is applied. The stated order of importance is the protection.

## 7. Estimators

- E1, primary, difference-in-differences. For each outcome y, the two-way fixed effects regression
  y(i, t) = a(i) + b(t) + ATT × ToU(i) × Post(t) + e(i, t) over all valid household-months, with household
  and month fixed effects and standard errors clustered by household. Reported: ATT, clustered SE, 95 %
  confidence interval (ATT plus or minus 1.96 SE), ATT as a share of the treated group's 2012 mean of y
  over its valid 2012 household-months.
- E2, event study. The same fixed effects and clustering with one coefficient per month for
  ToU(i) × 1[t = m], December 2012 the reference fixed at zero. The twelve pre-period months are
  January to December 2012 (eleven free coefficients and the reference) and the twelve post-period months
  are January to December 2013. Pre-trend test: a joint Wald test with the clustered covariance that the
  eleven free pre-period coefficients are all zero, reported as a p-value with the chi-square form and its
  F form. Figures `docs/event_study_<outcome>.png` for O1 to O5.
- E3, secondary, the comparison that would be primary under randomised assignment. One row per household:
  mean of y over the household's valid 2013 months regressed on ToU(i) and on the mean of y over its valid
  2012 months, with HC1 robust standard errors. Reported: the coefficient on ToU with its 95 % interval,
  and whether its sign agrees with E1 for O1 and O2.

## 8. Placebos

- P1, placebo date. Within 2012 only, the treatment indicator is ToU(i) × 1[month is July to December
  2012], estimated as in E1. The expectation is an interval that covers zero.
- P2, permutation test. The ToU label is reassigned at random across the households kept under R4,
  holding the number of treated households, 500 times in the full run and 100 times in the smoke run,
  seed 20261028. E1's point estimate is recomputed each time. p is the share of permuted estimates whose
  absolute value is at least the observed absolute estimate. Reported for O1 and O2.

## 9. Heterogeneity, secondary only

Households are split into terciles of their 2012 mean monthly kWh, cut points from the full kept sample.
E1 is estimated within each tercile for O1 and O2.

## 10. Balance

The 2012 mean of each outcome by group, their difference, and a Welch t-test p-value on the household
means. Balance is descriptive. Under self-selection a difference is expected and does not invalidate E1.

## 11. Reporting and decision thresholds

The README `## Results` table and `docs/memo.md` report, for each outcome: the treated group's 2012 mean,
ATT, 95 % CI, clustered SE, ATT as a percentage of the 2012 mean, the pre-trend p-value, the placebo-date
estimate, the permutation p (500 draws), the E3 estimate, the households by group and the months pre and
post. There are no decision thresholds. The memo reports what is found, including null results.

## 12. Deviations

Any change after the freeze goes into `DEVIATIONS.md` as `## D<n> (<date>)` with a `Reason:` line. A
coding error may be fixed with such an entry and the analysis re-run with `--deviation D<n>`. A change of
outcome, group, period or estimator is not a deviation but a stop for Avinash.

## 13. Smoke run and software

The smoke run takes 150 ToU and 150 Std households from the committed panel (`data/derived/panel_monthly.parquet`)
with seed 20261028, runs E1 to E3, P1, P2 with 100 permutations and the heterogeneity split, and writes
`results/smoke.json`. Smoke results are never the README numbers. Packages are pinned in `pyproject.toml`
and `requirements.lock`: duckdb 2.0.0, pandas 3.1.0, pyarrow 26.0.0, numpy 2.5.4, statsmodels 0.15.0,
linearmodels 7.1, scipy 1.18.1, matplotlib 3.11.2, openpyxl 3.1.5.
