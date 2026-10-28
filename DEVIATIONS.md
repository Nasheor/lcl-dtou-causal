# Deviations from the frozen pre-registration

Rule (PREREGISTRATION.md section 12): every entry has an id, a date and a reason. A coding fix is allowed.
A change of outcome, group, period or estimator is a stop. The pre-registered estimates in the README
Results table were not changed by any entry below.

## D1 (2026-10-28)

Reason: an addition outside the Results table, not a change to it. After the freeze, Report A3 (printed
pages 31 to 34) was found to state the event schedule in local time, while the readings carry 01:00 and
01:30 labels on 31 March 2013, an hour that did not exist in local time, so the readings are most likely
stamped in a fixed GMT frame and the pre-registered join on equal labels is one hour off during British
Summer Time. The pre-registered join was kept and reported as planned. A sensitivity run was added:
`python -m lcl_dtou_causal panel --variant bst-shift` builds a second panel with the schedule moved back
one hour inside British Summer Time before the join, and `python -m lcl_dtou_causal analyse
--sensitivity-timeframe` re-estimates E1 and E3 on it into `results/sensitivity_timeframe.json`. The
outcomes, groups, periods and estimators are those of the plan. The memo's caveats quote both sets of
numbers. The plan file itself was not edited and its hash still matches.
