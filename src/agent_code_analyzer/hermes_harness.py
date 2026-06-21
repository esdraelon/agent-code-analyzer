from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_SAMPLE_SOURCE = """from __future__ import annotations

class Greeter:
    def greet(self, name: str) -> str:
        return f\"hello {name}\"


def add(a: int, b: int) -> int:
    return a + b
"""


@dataclass(frozen=True, slots=True)
class FakeEmbeddingProvider:
    vector_size: int = 3

    def embed_document(self, text: str) -> list[float]:
        base = float(len(text) % 7)
        return [base, base + 1.0, base + 2.0]

    def embed_query(self, text: str) -> list[float]:
        base = float(len(text) % 5)
        return [base + 3.0, base + 4.0, base + 5.0]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collection_exists_value = False
        self.created_collections: list[dict[str, Any]] = []
        self.deleted_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_exists_value

    def create_collection(self, **kwargs: Any) -> None:
        self.collection_exists_value = True
        self.created_collections.append(kwargs)

    def delete(self, **kwargs: Any) -> None:
        self.deleted_calls.append(kwargs)

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_calls.append(kwargs)


@dataclass(frozen=True, slots=True)
class HarnessResult:
    workdir: str
    project_name: str
    project_root: str
    source_file: str
    hermes_root: str
    output_file: str
    ingest_summary: dict[str, Any]
    qdrant: dict[str, Any]
    agent_log: dict[str, Any]
    hermes_log: dict[str, Any]


class HarnessError(RuntimeError):
    pass


_DEF_HERMES_STUB = """from __future__ import annotations

import json
import os
from pathlib import Path


class AIAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.log_path = Path(os.environ.get("HERMES_STUB_LOG", Path(__file__).with_name("hermes_calls.jsonl")))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def chat(self, prompt):
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"prompt": prompt, "kwargs": self.kwargs}, ensure_ascii=False) + "\\n")
        first_line = prompt.splitlines()[0] if prompt.splitlines() else prompt
        return f"stub:{first_line}"
"""


def _write_hermes_stub(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    run_agent = root / "run_agent.py"
    run_agent.write_text(_DEF_HERMES_STUB, encoding="utf-8")
    return run_agent


def _serialise_points(points: list[Any]) -> list[dict[str, Any]]:
    serialised: list[dict[str, Any]] = []
    for point in points:
        payload = dict(getattr(point, "payload", {}) or {})
        serialised.append(
            {
                "id": str(getattr(point, "id", "")),
                "payload": {
                    "sqlite_uri": payload.get("sqlite_uri"),
                    "scope_type": payload.get("scope_type"),
                    "unit_type": payload.get("unit_type"),
                    "symbol_name": payload.get("symbol_name"),
                    "symbol_type": payload.get("symbol_type"),
                    "file_path": payload.get("file_path"),
                    "semantic_description_state": payload.get("semantic_description_state"),
                    "semantic_description_backend": payload.get("semantic_description_backend"),
                    "description_text": payload.get("description_text"),
                },
            }
        )
    return serialised


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _serialise_qdrant_call(call: dict[str, Any]) -> dict[str, Any]:
    serialised = {key: _json_safe(value) for key, value in call.items() if key != "points"}
    points = list(call.get("points", []))
    serialised["point_count"] = len(points)
    serialised["points"] = _serialise_points(points)
    return serialised


def run_one_file_harness(
    *,
    output_file: str | Path,
    project_name: str = "hermes-one-file",
    source_text: str = DEFAULT_SAMPLE_SOURCE,
    workdir: str | Path | None = None,
) -> HarnessResult:
    """Run a one-file ingestion through the Hermes semantic path.

    The harness keeps the Hermes adapter isolated behind a local run_agent.py stub
    and writes a JSON report so the request/response path is easy to validate.
    """

    from agent_code_analyzer import projects as projects_module
    from agent_code_analyzer.agents.hermes import HermesLibAgent
    from agent_code_analyzer.parsing import analyze_file
    from agent_code_analyzer.projects import add_project, ingest_project_tree
    from agent_code_analyzer.semantic_agent import AgentSemanticWriter
    from agent_code_analyzer.vector_index import QdrantVectorIndex
    import agent_code_analyzer.vector_index as vector_index_module

    base_dir = Path(workdir).expanduser().resolve() if workdir is not None else Path(
        tempfile.mkdtemp(prefix="agent-code-analyzer-hermes-harness-")
    )
    base_dir.mkdir(parents=True, exist_ok=True)

    state_dir = base_dir / "state"
    project_root = base_dir / "project"
    hermes_root = base_dir / "hermes"
    report_dir = base_dir / "report"
    project_root.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_path = project_root / "src" / "demo.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_text, encoding="utf-8")

    _write_hermes_stub(hermes_root)
    hermes_log = hermes_root / "hermes_calls.jsonl"
    os.environ["HERMES_STUB_LOG"] = str(hermes_log)
    sys.modules.pop("run_agent", None)

    projects_module.DATA_DIR = state_dir
    projects_module.METADATA_DB = state_dir / "metadata.sqlite3"
    projects_module.PROJECTS_DIR = state_dir / "projects"

    hermes_agent = HermesLibAgent(
        hermes_repo_root=hermes_root,
        log_dir=report_dir / "agent-log",
        source="agent-code-analyzer-harness",
    )
    semantic_writer = AgentSemanticWriter(hermes_agent)
    qdrant = FakeQdrantClient()
    vector_index = QdrantVectorIndex(
        url="http://example.invalid",
        embedding_provider=FakeEmbeddingProvider(),
        semantic_writer=semantic_writer,
    )
    object.__setattr__(vector_index, "_client", qdrant)

    vector_index_module._VECTOR_INDEX = vector_index
    vector_index_module.get_vector_index = lambda: vector_index  # type: ignore[assignment]

    add_project(project_name, str(project_root), mode="file", description="Hermes harness project")
    ingest_summary = ingest_project_tree(project_name, refresh=True)

    agent_log = report_dir / "agent-log" / "requests.jsonl"
    agent_requests = []
    if agent_log.exists():
        agent_requests = [json.loads(line) for line in agent_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    hermes_requests = []
    if hermes_log.exists():
        hermes_requests = [json.loads(line) for line in hermes_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    if not qdrant.upsert_calls:
        raise HarnessError("Qdrant harness did not receive any upsert calls")

    first_upsert = qdrant.upsert_calls[0]
    points = list(first_upsert.get("points", []))
    report = HarnessResult(
        workdir=str(base_dir),
        project_name=project_name,
        project_root=str(project_root),
        source_file=str(source_path),
        hermes_root=str(hermes_root),
        output_file=str(Path(output_file).expanduser().resolve()),
        ingest_summary=ingest_summary,
        qdrant={
            "created_collections": [_serialise_qdrant_call(call) for call in qdrant.created_collections],
            "deleted_calls": [_serialise_qdrant_call(call) for call in qdrant.deleted_calls],
            "upsert_count": len(qdrant.upsert_calls),
            "point_count": len(points),
            "points": _serialise_points(points),
        },
        agent_log={
            "path": str(agent_log),
            "count": len(agent_requests),
            "requests": agent_requests,
        },
        hermes_log={
            "path": str(hermes_log),
            "count": len(hermes_requests),
            "requests": hermes_requests,
        },
    )

    output_path = Path(output_file).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = [
    "DEFAULT_SAMPLE_SOURCE",
    "FakeEmbeddingProvider",
    "FakeQdrantClient",
    "HarnessError",
    "HarnessResult",
    "run_one_file_harness",
]
