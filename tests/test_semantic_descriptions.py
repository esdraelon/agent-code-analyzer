from __future__ import annotations

import pytest

from agent_code_analyzer.semantic_descriptions import (
    SCOPE_LEVELS,
    UPDATE_MODES,
    SemanticDescriptionMapper,
    SemanticDescriptionRecord,
    build_semantic_description_record,
    build_semantic_scope_id,
    normalize_scope_type,
)


def test_scope_levels_and_update_modes_are_explicit() -> None:
    assert SCOPE_LEVELS == ("package", "module", "file", "class", "method", "chunk")
    assert UPDATE_MODES == ("mass_ingestion", "fswatch_diff")
    assert normalize_scope_type("FILE") == "file"


@pytest.mark.parametrize("scope_type", SCOPE_LEVELS)
def test_scope_ids_are_stable_across_description_changes(scope_type: str) -> None:
    base = build_semantic_scope_id(
        project="demo",
        scope_type=scope_type,
        file_path="src/app.py",
        symbol_path="App.run",
        line_start=10,
        line_end=20,
        parent_scope_id="semantic://demo/file/parent",
    )
    changed_description = build_semantic_scope_id(
        project="demo",
        scope_type=scope_type,
        file_path="src/app.py",
        symbol_path="App.run",
        line_start=10,
        line_end=20,
        parent_scope_id="semantic://demo/file/parent",
    )
    assert base == changed_description
    assert base.startswith("semantic://demo/")


def test_scope_id_changes_when_lineage_changes() -> None:
    original = build_semantic_scope_id(
        project="demo",
        scope_type="method",
        file_path="src/app.py",
        symbol_path="App.run",
        line_start=10,
        line_end=20,
        parent_scope_id="semantic://demo/class/parent-a",
    )
    renamed = build_semantic_scope_id(
        project="demo",
        scope_type="method",
        file_path="src/app.py",
        symbol_path="App.run",
        line_start=10,
        line_end=20,
        parent_scope_id="semantic://demo/class/parent-b",
    )
    assert original != renamed


def test_semantic_record_defaults_and_payload_round_trip() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="method",
        file_path="src/app.py",
        description_text="Builds the response object.",
        source_fingerprint="abc123",
        symbol_name="run",
        symbol_path="App.run",
        line_start=10,
        line_end=24,
        parent_scope_id="semantic://demo/class/parent",
        update_mode="fswatch_diff",
        metadata={"language": "python", "confidence": 0.91},
    )

    assert isinstance(record, SemanticDescriptionRecord)
    assert record.scope_type == "method"
    assert record.update_mode == "fswatch_diff"
    assert record.has_line_anchors is True
    assert record.scope_id is not None
    assert record.scope_id.startswith("semantic://demo/method/")

    payload = SemanticDescriptionMapper.to_payload(record)
    assert payload["project"] == "demo"
    assert payload["scope_type"] == "method"
    assert payload["scope_id"] == record.scope_id
    assert payload["symbol_name"] == "run"
    assert payload["line_start"] == 10
    assert payload["line_end"] == 24
    assert payload["parent_scope_id"] == "semantic://demo/class/parent"
    assert payload["description_text"] == "Builds the response object."
    assert payload["update_mode"] == "fswatch_diff"
    assert payload["metadata"] == {"language": "python", "confidence": 0.91}

    round_tripped = SemanticDescriptionMapper.from_payload(payload)
    assert round_tripped == record
    assert round_tripped.metadata == {"language": "python", "confidence": 0.91}


def test_semantic_record_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        build_semantic_description_record(
            project="demo",
            scope_type="not-a-scope",
            file_path="src/app.py",
            description_text="x",
            source_fingerprint="abc123",
        )

    with pytest.raises(ValueError):
        build_semantic_description_record(
            project="demo",
            scope_type="file",
            file_path="src/app.py",
            description_text="x",
            source_fingerprint="abc123",
            update_mode="manual",
        )


def test_metadata_is_decoupled_from_identity() -> None:
    record = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="File overview.",
        source_fingerprint="hash-1",
        metadata={"source": "first"},
    )
    alt = build_semantic_description_record(
        project="demo",
        scope_type="file",
        file_path="src/app.py",
        description_text="Changed overview.",
        source_fingerprint="hash-1",
        metadata={"source": "second"},
    )
    assert record.scope_id == alt.scope_id
    assert record != alt
