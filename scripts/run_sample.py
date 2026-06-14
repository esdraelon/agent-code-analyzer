#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

from agent_code_analyzer import generate_ast_skeleton


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_sample.py <source-file>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    print(generate_ast_skeleton(str(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
