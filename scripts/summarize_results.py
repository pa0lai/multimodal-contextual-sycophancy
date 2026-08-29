#!/usr/bin/env python3
"""Offline aggregation of released compact result rows."""

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from src.evaluation.summary import FILTER_FIELDS, aggregate_correctness, load_compact_rows, matching_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=list(Path("results/compact").glob("*.jsonl")))
    for field in FILTER_FIELDS:
        parser.add_argument(f"--{field.replace('_', '-')}", dest=field)
    args = parser.parse_args()
    filters = {field: getattr(args, field) for field in FILTER_FIELDS if getattr(args, field)}
    print(json.dumps({"filters": filters, **aggregate_correctness(matching_rows(load_compact_rows(args.paths), **filters))}, indent=2))


if __name__ == "__main__":
    main()

