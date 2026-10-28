"""Command line entry point.

    python -m lcl_dtou_causal prereg freeze | check
    python -m lcl_dtou_causal download
    python -m lcl_dtou_causal schedule
    python -m lcl_dtou_causal panel
    python -m lcl_dtou_causal analyse [--permutations N] [--deviation ID]
    python -m lcl_dtou_causal memo [--deviation ID]
    python -m lcl_dtou_causal smoke

``smoke`` runs the analysis on a stratified sample of 300 households from the committed panel with 100
permutations, writes ``results/smoke.json`` and finishes in under 10 minutes. The README numbers come
from the full run (``analyse`` then ``memo``) and are asserted by ``tests/test_readme_numbers.py``.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lcl_dtou_causal")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("prereg", help="freeze or check the pre-registration hash")
    pr.add_argument("action", choices=["freeze", "check"])

    sub.add_parser("download", help="fetch the London Datastore files into data/raw and verify them")
    sub.add_parser("schedule", help="build the 2013 dToU half-hour schedule and the price file")
    pa = sub.add_parser("panel", help="one DuckDB pass from the raw CSV files to the household-month panel")
    pa.add_argument("--variant", choices=["prereg", "bst-shift"], default="prereg", help="bst-shift builds the sensitivity panel")

    an = sub.add_parser("analyse", help="balance, DiD, event study, ANCOVA, placebos, heterogeneity")
    an.add_argument("--permutations", type=int, default=500)
    an.add_argument("--deviation", default=None)
    an.add_argument("--sensitivity-timeframe", action="store_true", help="DiD on the bst-shift panel, outside the Results table")

    me = sub.add_parser("memo", help="write docs/memo.md, docs/partner_slide.md and results/readme_numbers.json")
    me.add_argument("--deviation", default=None)

    sub.add_parser("smoke", help="short reproducible run on 300 households, 100 permutations")

    args = p.parse_args(argv)

    if args.cmd == "prereg":
        from . import prereg

        if args.action == "freeze":
            rec = prereg.freeze()
            print(f"frozen sha256 {rec['sha256']} plan commit {rec['plan_commit'][:12]} freeze commit {rec['freeze_commit'][:12]}")
            return 0
        st = prereg.status()
        print(st)
        return 0 if st["match"] else 1
    if args.cmd == "download":
        from .download import run

        return run()
    if args.cmd == "schedule":
        from .schedule import run

        return run()
    if args.cmd == "panel":
        from .panel import run

        return run(variant=args.variant)
    if args.cmd == "analyse":
        from .analyse import run_full, run_sensitivity_timeframe

        if args.sensitivity_timeframe:
            return run_sensitivity_timeframe(deviation=args.deviation)
        return run_full(permutations=args.permutations, deviation=args.deviation)
    if args.cmd == "memo":
        from .memo import run

        return run(deviation=args.deviation)
    if args.cmd == "smoke":
        from .analyse import run_smoke

        return run_smoke()
    return 2


if __name__ == "__main__":
    sys.exit(main())
