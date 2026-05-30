#!/usr/bin/env python3
"""Normalize phone numbers from a text file.

Each input line should contain one phone number. The script removes spaces and
common separators, then strips either a country code prefix or a local leading
zero so the remaining value is the national number.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_COUNTRY_CODE = "964"


def clean_phone_number(raw_number: str, country_code: str = DEFAULT_COUNTRY_CODE) -> str:
    """Return a phone number without separators, country code, or local zero."""
    cleaned = re.sub(r"[^\d+]", "", raw_number.strip())

    if cleaned.startswith(f"+{country_code}"):
        cleaned = cleaned[len(country_code) + 1 :]
    elif cleaned.startswith(country_code):
        cleaned = cleaned[len(country_code) :]
    elif cleaned.startswith("0"):
        cleaned = cleaned[1:]

    return cleaned


def clean_phone_file(
    input_path: Path,
    output_path: Path | None = None,
    country_code: str = DEFAULT_COUNTRY_CODE,
) -> list[str]:
    """Clean one phone number per line from input_path."""
    numbers = [
        clean_phone_number(line, country_code)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if output_path is not None:
        output_path.write_text("\n".join(numbers) + "\n", encoding="utf-8")

    return numbers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean phone numbers by removing spaces, country code, and leading zero."
    )
    parser.add_argument("input_file", type=Path, help="Text file with one phone number per line.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional file to write cleaned numbers. Defaults to printing to the terminal.",
    )
    parser.add_argument(
        "--country-code",
        default=DEFAULT_COUNTRY_CODE,
        help=f"Country code to remove when present. Default: {DEFAULT_COUNTRY_CODE}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    numbers = clean_phone_file(args.input_file, args.output, args.country_code)

    if args.output is None:
        print("\n".join(numbers))


if __name__ == "__main__":
    main()
