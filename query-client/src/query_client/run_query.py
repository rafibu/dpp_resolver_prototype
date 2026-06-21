"""CLI entry point for reproducible federated queries.

Usage::

    python -m query_client.run_query --request query.json

Loads a JSON federated query request, runs it to completion against the
configured resolver/platforms, and prints the full federated result as JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import get_config
from .models import FederatedPredicateQueryRequest
from .service import run_federated_query
from .validation import QueryValidationError


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m query_client.run_query",
        description="Run a federated predicate query and print the JSON result.",
    )
    parser.add_argument(
        "--request",
        required=True,
        help="Path to a JSON file containing the federated query request.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation for the printed JSON result (default: 2).",
    )
    return parser.parse_args(argv)


async def _run(request_path: str, indent: int) -> int:
    with open(request_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    request = FederatedPredicateQueryRequest.model_validate(payload)
    try:
        result = await run_federated_query(request, config=get_config())
    except QueryValidationError as exc:
        print(f"Invalid query request: {exc}", file=sys.stderr)
        return 2

    print(result.model_dump_json(indent=indent))
    # Non-zero exit if no platform succeeded, so scripts can detect total failure.
    return 0 if result.status.value in ("SUCCESS", "PARTIAL") else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args.request, args.indent))


if __name__ == "__main__":
    raise SystemExit(main())
