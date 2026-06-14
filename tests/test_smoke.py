from __future__ import annotations

from pathlib import Path

from agent_code_analyzer.parsing import ast_skeleton, detect_language, list_symbols
from agent_code_analyzer.server import parse_source


def test_detect_language_and_skeleton(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        """
class Greeter:
    def greet(self, name):
        return f\"hello {name}\"\n

def top_level():
    return 42
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert detect_language(str(source)) == "python"

    skeleton = ast_skeleton(str(source))
    assert "[class_definition] class Greeter" in skeleton or "[class_declaration] class Greeter" in skeleton
    assert "[function_definition] def top_level()" in skeleton

    symbols = list_symbols(str(source))
    assert symbols
    assert symbols[0]["name"] == "Greeter"

    parsed = parse_source(str(source))
    assert parsed["supported"] is True
    assert parsed["language"] == "python"


def test_unsupported_extension_returns_fallback(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("plain text\n", encoding="utf-8")

    assert detect_language(str(source)) == ""
    assert ast_skeleton(str(source)) == ""
    assert list_symbols(str(source)) == []
    parsed = parse_source(str(source))
    assert parsed["supported"] is False
