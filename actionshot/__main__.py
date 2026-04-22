"""CLI entry point for ``python -m actionshot.benchmark``.

Usage::

    python -m actionshot.benchmark --suite benchmarks/ --report report.json
"""

import argparse
import json
import sys

from actionshot.benchmark import BenchmarkSuite


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ActionShot benchmark suite and report results."
    )
    parser.add_argument(
        "--suite",
        default="benchmarks/",
        help="Path to the benchmarks directory (default: benchmarks/).",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Path to write the JSON report (optional).",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Path to a baseline report JSON for regression comparison.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        help="Exit with code 1 if one_shot_success_rate regressed >5%%.",
    )

    args = parser.parse_args()

    suite = BenchmarkSuite(suite_dir=args.suite)

    if not suite.cases:
        print(f"No benchmark cases found in {args.suite}", file=sys.stderr)
        sys.exit(1)

    report = suite.run_all()
    suite.print_report(report)

    if args.report:
        suite.save_report(report, args.report)
        print(f"\nReport saved to {args.report}")

    # Regression comparison
    if args.baseline:
        try:
            with open(args.baseline, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Warning: could not load baseline {args.baseline}: {exc}",
                  file=sys.stderr)
            baseline = None

        if baseline is not None:
            comparison = BenchmarkSuite.compare(baseline, report)
            print("\n" + "=" * 70)
            print("  Regression Comparison")
            print("=" * 70)

            for metric, info in comparison["deltas"].items():
                marker = " << REGRESSION" if info.get("regression") else ""
                print(
                    f"  {metric:35s}  "
                    f"baseline={info['baseline']}  "
                    f"new={info['new']}  "
                    f"delta={info['delta']}{marker}"
                )

            if args.fail_on_regression:
                oss = comparison["deltas"].get("one_shot_success_rate", {})
                delta = oss.get("delta")
                if delta is not None and delta < -0.05:
                    print(
                        f"\nFAILED: one_shot_success_rate regressed by "
                        f"{abs(delta):.1%} (threshold: 5%)",
                        file=sys.stderr,
                    )
                    sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
