"""Command-line interface for the payment terms synchroniser."""

from __future__ import annotations

import argparse
import sys

from .runner import run_payment_terms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronise payment terms between Excel and QuickBooks"
    )
    parser.add_argument(
        "--workbook",
        required=True,
        help="Excel workbook containing the payment_terms worksheet",
    )
    parser.add_argument("--output", help="Optional JSON output path")

    args = parser.parse_args(argv)

    path = run_payment_terms("", args.workbook, output_path=args.output)
    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual invocation
    sys.exit(main())
