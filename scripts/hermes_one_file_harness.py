#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agent_code_analyzer.hermes_harness import run_one_file_harness


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hermes one-file ingestion harness")
    parser.add_argument("--output-file", type=Path, default=Path("./hermes-harness-report.json"))
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--project-name", default="hermes-one-file")
    args = parser.parse_args()

    result = run_one_file_harness(
        output_file=args.output_file,
        workdir=args.workdir,
        project_name=args.project_name,
    )
    print(result.output_file)
    print(f"file_count={result.ingest_summary['file_count']} symbol_count={result.ingest_summary['symbol_count']}")
    print(f"agent_requests={result.agent_log['count']} hermes_requests={result.hermes_log['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
