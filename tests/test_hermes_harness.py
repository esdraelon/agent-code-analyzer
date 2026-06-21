from __future__ import annotations

import json
from pathlib import Path

from agent_code_analyzer.hermes_harness import run_one_file_harness


def test_one_file_hermes_harness_writes_a_report_and_logs_requests(tmp_path: Path) -> None:
    output_file = tmp_path / "report" / "harness-report.json"

    result = run_one_file_harness(output_file=output_file, workdir=tmp_path)

    assert output_file.exists()
    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["project_name"] == "hermes-one-file"
    assert report["ingest_summary"]["file_count"] == 1
    assert report["ingest_summary"]["symbol_count"] >= 1
    assert report["qdrant"]["upsert_count"] >= 1
    assert report["qdrant"]["point_count"] >= 1
    assert report["agent_log"]["count"] >= 1
    assert report["hermes_log"]["count"] >= 1

    first_request = report["agent_log"]["requests"][0]
    assert "Write a concise semantic description for file scope." in first_request["prompt"]
    assert result.ingest_summary["file_count"] == 1
    assert Path(report["agent_log"]["path"]).exists()
    assert Path(report["hermes_log"]["path"]).exists()
    assert "src/demo.py" in first_request["prompt"]
    assert report["qdrant"]["points"][0]["payload"]["semantic_description_backend"] == "hermes-lib"
    assert report["qdrant"]["points"][0]["payload"]["semantic_description_state"] in {"description", "no_response"}
