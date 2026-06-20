from __future__ import annotations

from pathlib import Path

from agent_code_analyzer.parsing import analyze_file
from agent_code_analyzer.semantic_chunking import build_method_chunk_spans


def test_small_method_remains_a_single_chunk(tmp_path: Path) -> None:
    file_path = tmp_path / "small.py"
    file_path.write_text(
        """def hello(name):\n    return name.upper()\n""",
        encoding="utf-8",
    )

    analysis = analyze_file(str(file_path))
    symbol = analysis["symbols"][0]

    spans = build_method_chunk_spans(analysis["parsed"], symbol)

    assert len(spans) == 1
    assert spans[0].chunk_total == 1
    assert spans[0].is_split is False
    assert spans[0].line_start == 0
    assert spans[0].line_end >= spans[0].line_start
    assert "return name.upper()" in spans[0].chunk_text


def test_long_method_splits_into_ast_aware_chunks(tmp_path: Path) -> None:
    file_path = tmp_path / "long.py"
    file_path.write_text(
        """def calculate(value):\n    total = 0\n    if value > 10:\n        total += value\n    else:\n        total -= value\n    for step in range(3):\n        total += step\n    while total < 50:\n        total += 2\n    return total\n""",
        encoding="utf-8",
    )

    analysis = analyze_file(str(file_path))
    symbol = analysis["symbols"][0]

    spans = build_method_chunk_spans(analysis["parsed"], symbol, min_split_lines=4, max_chunk_lines=5)

    assert len(spans) > 1
    assert spans[0].chunk_total == len(spans)
    assert all(span.is_split for span in spans)
    assert spans[0].line_start == 1
    assert spans[-1].line_end >= spans[0].line_start
    assert any("if value > 10" in span.chunk_text for span in spans)
    assert any("for step in range(3)" in span.chunk_text for span in spans)
    assert any("while total < 50" in span.chunk_text for span in spans)
    assert spans[0].statement_count >= 1
