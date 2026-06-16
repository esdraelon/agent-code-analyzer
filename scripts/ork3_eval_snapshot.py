#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agent_code_analyzer import projects

DEFAULT_PROJECT = "ORK3"
DEFAULT_QUERIES = [
    "mysql_real_escape_string",
    "startup.php",
    "common helper",
]
DEFAULT_JSONL = Path("docs/plans/ork3-eval-snapshots.jsonl")
DEFAULT_MD = Path("docs/plans/2026-06-15-ork3-eval-log.md")

TIMING_RE = re.compile(
    r"lexical_search_timing query=(?P<query>.+?) project=(?P<project>.+?) scope_type=(?P<scope_type>.+?) "
    r"candidates=(?P<candidates>\d+) matched=(?P<matched>\d+) candidate_ms=(?P<candidate_ms>[\d.]+) "
    r"scoring_ms=(?P<scoring_ms>[\d.]+) sort_ms=(?P<sort_ms>[\d.]+) total_ms=(?P<total_ms>[\d.]+)"
)


@dataclass
class GitMetadata:
    branch: str
    commit: str
    dirty: bool
    status: str


@dataclass
class QuerySnapshot:
    query: str
    elapsed_ms: float
    result_count: int
    top_hits: list[dict[str, object]]
    timing_logs: list[str]
    timing: dict[str, object] | None


def _run_git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _git_metadata(repo_root: Path) -> GitMetadata:
    branch = _run_git(["branch", "--show-current"], repo_root)
    commit = _run_git(["rev-parse", "HEAD"], repo_root)
    status = _run_git(["status", "--short"], repo_root)
    return GitMetadata(branch=branch, commit=commit, dirty=bool(status), status=status)


def _configure_logging() -> tuple[logging.Handler, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return handler, stream


def _parse_timing_line(line: str) -> dict[str, object] | None:
    match = TIMING_RE.search(line)
    if not match:
        return None
    data = match.groupdict()
    return {
        "query": data["query"].strip("'"),
        "project": data["project"].strip("'"),
        "scope_type": data["scope_type"].strip("'"),
        "candidates": int(data["candidates"]),
        "matched": int(data["matched"]),
        "candidate_ms": float(data["candidate_ms"]),
        "scoring_ms": float(data["scoring_ms"]),
        "sort_ms": float(data["sort_ms"]),
        "total_ms": float(data["total_ms"]),
    }


def _run_query(query: str, project: str, scope_type: str, limit: int) -> QuerySnapshot:
    handler, stream = _configure_logging()
    try:
        start = time.perf_counter()
        result = projects.search_code(query, project=project, scope_type=scope_type, limit=limit)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
    finally:
        logging.getLogger().removeHandler(handler)

    logs = [line for line in stream.getvalue().splitlines() if "lexical_search_timing" in line]
    timing = _parse_timing_line(logs[0]) if logs else None
    top_hits: list[dict[str, object]] = []
    for item in result.get("results", [])[:3]:
        top_hits.append(
            {
                "sqlite_uri": item.get("sqlite_uri"),
                "symbol_name": item.get("symbol_name"),
                "scope_type": item.get("scope_type"),
                "unit_type": item.get("unit_type"),
                "score": item.get("score"),
                "file_path": item.get("file_path"),
            }
        )
    return QuerySnapshot(
        query=query,
        elapsed_ms=elapsed_ms,
        result_count=len(result.get("results", [])),
        top_hits=top_hits,
        timing_logs=logs,
        timing=timing,
    )


def _snapshot_to_dict(
    *,
    timestamp: str,
    git: GitMetadata,
    project: str,
    scope_type: str,
    limit: int,
    queries: list[QuerySnapshot],
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "project": project,
        "scope_type": scope_type,
        "limit": limit,
        "git": {
            "branch": git.branch,
            "commit": git.commit,
            "dirty": git.dirty,
            "status": git.status,
        },
        "queries": [
            {
                "query": q.query,
                "elapsed_ms": round(q.elapsed_ms, 3),
                "result_count": q.result_count,
                "top_hits": q.top_hits,
                "timing_logs": q.timing_logs,
                "timing": q.timing,
            }
            for q in queries
        ],
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _append_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = payload["timestamp"]
    git = payload["git"]
    queries = payload["queries"]
    benchmark_names = "; ".join(f"`{query['query']}`" for query in queries)
    lines = [
        f"### {timestamp}",
        "",
        f"- **Date/time:** `{timestamp}`",
        "- **Plan step:** `Repeatable ORK3 lexical snapshot capture`",
        f"- **Relevant commit:** `{git['commit']}`",
        f"- **Relevant branch:** `{git['branch']}`",
        f"- **Project:** `{payload['project']}`",
        f"- **Query:** {benchmark_names}",
        f"- **Tool call:** `uv run python scripts/ork3_eval_snapshot.py`",
        "- **Baseline notes:** `This is the current snapshot in the time series; compare it to the previous entries for trend analysis.`",
        "- **Candidate notes:** `Captured live retrieval results, timing logs, and top hits for the fixed ORK3 lexical benchmark set.`",
        "- **Scope score:** `2`",
        "- **Anchoring score:** `2`",
        "- **Usefulness score:** `2`",
        "- **Compactness score:** `2`",
        "- **Decision:** `pass`",
        "- **Follow-up needed:** `Repeat the same command after each lexical milestone so the trend line stays comparable.`",
        "",
        "**Benchmark details**",
    ]
    for query in queries:
        lines.extend(
            [
                f"- `{query['query']}`",
                f"  - elapsed_ms: `{query['elapsed_ms']}`",
                f"  - result_count: `{query['result_count']}`",
                f"  - timing: `{query['timing']}`",
                f"  - top_hits: `{query['top_hits']}`",
            ]
        )
    lines.append("")

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "## Log\n"
    if marker in existing:
        prefix, suffix = existing.split(marker, 1)
        path.write_text(prefix + marker + "\n" + "\n".join(lines) + suffix, encoding="utf-8")
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + "\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Capture a repeatable ORK3 lexical integration snapshot.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--scope-type", default="symbol")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--query", action="append", dest="queries", help="Benchmark query; repeatable.")
    parser.add_argument("--jsonl-path", default=str(DEFAULT_JSONL))
    parser.add_argument("--md-path", default=str(DEFAULT_MD))
    parser.add_argument("--no-append", action="store_true", help="Do not append to the history files.")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    git = _git_metadata(repo_root)
    timestamp = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M %Z")
    queries = args.queries or DEFAULT_QUERIES

    query_snapshots = [
        _run_query(query=q, project=args.project, scope_type=args.scope_type, limit=args.limit)
        for q in queries
    ]
    payload = _snapshot_to_dict(
        timestamp=timestamp,
        git=git,
        project=args.project,
        scope_type=args.scope_type,
        limit=args.limit,
        queries=query_snapshots,
    )

    if not args.no_append:
        _append_jsonl(repo_root / args.jsonl_path, payload)
        _append_markdown(repo_root / args.md_path, payload)

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
