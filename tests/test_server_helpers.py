from __future__ import annotations

from pathlib import Path

from agent_code_analyzer import server


def test_tool_response_factory_shapes_fallback_payloads() -> None:
    factory = server.ToolResponseFactory()

    payload = factory.parse_source_error("alpha", "src/one.py", ValueError("outside project root"))
    assert payload == {
        "project": "alpha",
        "file_path": "src/one.py",
        "supported": False,
        "language": "",
        "languages": [],
        "error": "outside project root",
    }
    assert factory.empty_symbol_list() == "[]"
    assert factory.empty_language() == ""


def test_file_excerpt_renderer_clamps_and_handles_reversed_bounds(tmp_path: Path) -> None:
    renderer = server.FileExcerptRenderer()
    path = tmp_path / "sample.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    assert renderer.render(path, start_line=0, end_line=2) == "1: alpha\n2: beta"
    assert renderer.render(path, start_line=3, end_line=2) == ""
