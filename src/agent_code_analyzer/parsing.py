from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from tree_sitter import Parser
import tree_sitter_languages

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    "c": "c",
    "cc": "cpp",
    "clj": "clojure",
    "cpp": "cpp",
    "cs": "c_sharp",
    "go": "go",
    "h": "c",
    "hpp": "cpp",
    "java": "java",
    "js": "javascript",
    "jsx": "javascript",
    "lua": "lua",
    "php": "php",
    "py": "python",
    "rb": "ruby",
    "rs": "rust",
    "sh": "bash",
    "ts": "typescript",
    "tsx": "tsx",
    "yml": "yaml",
    "yaml": "yaml",
}

TARGET_NODE_TYPES = {
    "class_declaration",
    "class_definition",
    "enum_declaration",
    "function_definition",
    "function_declaration",
    "interface_declaration",
    "method_definition",
    "method_declaration",
    "struct_declaration",
}

DEFAULT_MAX_SYMBOL_DEPTH = 6


@dataclass(frozen=True)
class ParsedFile:
    file_path: str
    language: str
    source_bytes: bytes
    source_code: str
    tree: Any


@lru_cache(maxsize=32)
def resolve_language(language_name: str):
    return tree_sitter_languages.get_language(language_name)


def detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower().lstrip(".")
    return LANGUAGE_BY_EXTENSION.get(suffix, "")


def _decode_source_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_source_text(source_path: Path) -> tuple[bytes, str]:
    raw = source_path.read_bytes()
    return raw, _decode_source_bytes(raw)


def parse_file(file_path: str) -> ParsedFile:
    language_name = detect_language(file_path)
    if not language_name:
        raise ValueError(f"Unsupported file extension for Tree-sitter: {file_path}")

    source_path = Path(file_path)
    source_bytes, source_code = _read_source_text(source_path)

    parser = Parser()
    parser.set_language(resolve_language(language_name))
    tree = parser.parse(source_bytes)
    return ParsedFile(
        file_path=str(source_path),
        language=language_name,
        source_bytes=source_bytes,
        source_code=source_code,
        tree=tree,
    )


def _node_signature(node: Any, source_bytes: bytes) -> str:
    body = node.child_by_field_name("body")
    end = body.start_byte if body else node.end_byte
    return _decode_source_bytes(source_bytes[node.start_byte:end]).strip().replace("{", "").strip()


def _node_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return _decode_source_bytes(name.text)

    for child in getattr(node, "named_children", []):
        if child.type in {"identifier", "type_identifier", "property_identifier"}:
            return _decode_source_bytes(child.text)

    return ""


def _walk_tree(tree: Any) -> Iterator[tuple[Any, int]]:
    cursor = tree.walk()
    reached_root = False
    while not reached_root:
        node = cursor.node
        yield node, cursor.depth
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        while True:
            if not cursor.goto_parent():
                reached_root = True
                break
            if cursor.goto_next_sibling():
                break


def _symbol_health_report(
    symbols: list[dict[str, object]],
    *,
    has_error: bool,
    max_depth: int = DEFAULT_MAX_SYMBOL_DEPTH,
) -> dict[str, Any]:
    issues: list[str] = []
    seen_issues: set[str] = set()
    seen_names: set[tuple[str, int, str]] = set()

    def add_issue(message: str) -> None:
        if message in seen_issues:
            return
        seen_issues.add(message)
        issues.append(message)

    if has_error:
        add_issue("parse tree contains error nodes")

    for index, symbol in enumerate(symbols):
        name = str(symbol.get("name", "")).strip()
        symbol_type = str(symbol.get("type", "")).strip() or "symbol"
        depth_value = symbol.get("depth", 0)
        depth = int(depth_value) if isinstance(depth_value, (int, str)) else 0

        if not name:
            add_issue(f"symbol #{index} is missing a name")
            continue

        if depth > max_depth:
            add_issue(
                f"symbol '{name}' at depth {depth} exceeds max depth {max_depth}"
            )

        scope_key = (symbol_type, depth, name)
        if scope_key in seen_names:
            add_issue(
                f"duplicate symbol name '{name}' in scope type={symbol_type} depth={depth}"
            )
            continue
        seen_names.add(scope_key)

    return {
        "healthy": not issues,
        "issues": issues,
        "max_depth": max_depth,
        "symbol_count": len(symbols),
    }


def analyze_file(file_path: str) -> dict[str, Any]:
    if not detect_language(file_path):
        raise ValueError(f"Unsupported file extension for Tree-sitter: {file_path}")

    parsed = parse_file(file_path)
    skeleton_lines: list[str] = []
    symbols: list[dict[str, object]] = []

    for node, depth in _walk_tree(parsed.tree):
        if node.type not in TARGET_NODE_TYPES:
            continue
        signature = _node_signature(node, parsed.source_bytes)
        skeleton_lines.append(f"{'  ' * depth}[{node.type}] {signature}")
        symbols.append(
            {
                "type": node.type,
                "name": _node_name(node),
                "depth": depth,
                "start_point": {
                    "row": node.start_point[0],
                    "column": node.start_point[1],
                },
                "end_point": {
                    "row": node.end_point[0],
                    "column": node.end_point[1],
                },
                "signature": signature,
            }
        )

    return {
        "parsed": parsed,
        "skeleton": "\n".join(skeleton_lines),
        "symbols": symbols,
        "symbol_health": _symbol_health_report(
            symbols,
            has_error=bool(parsed.tree.root_node.has_error),
        ),
    }


def ast_skeleton(file_path: str) -> str:
    if not detect_language(file_path):
        return ""
    return analyze_file(file_path)["skeleton"]


def list_symbols(file_path: str) -> list[dict[str, object]]:
    if not detect_language(file_path):
        return []
    return analyze_file(file_path)["symbols"]
