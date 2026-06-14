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


@dataclass(frozen=True)
class ParsedFile:
    file_path: str
    language: str
    source_code: str
    tree: Any


@lru_cache(maxsize=32)
def resolve_language(language_name: str):
    return tree_sitter_languages.get_language(language_name)


def detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower().lstrip(".")
    return LANGUAGE_BY_EXTENSION.get(suffix, "")


def parse_file(file_path: str) -> ParsedFile:
    language_name = detect_language(file_path)
    if not language_name:
        raise ValueError(f"Unsupported file extension for Tree-sitter: {file_path}")

    source_path = Path(file_path)
    source_code = source_path.read_text(encoding="utf-8")

    parser = Parser()
    parser.set_language(resolve_language(language_name))
    tree = parser.parse(source_code.encode("utf-8"))
    return ParsedFile(
        file_path=str(source_path),
        language=language_name,
        source_code=source_code,
        tree=tree,
    )


def _node_signature(node: Any, source_code: str) -> str:
    body = node.child_by_field_name("body")
    end = body.start_byte if body else node.end_byte
    return source_code[node.start_byte:end].strip().replace("{", "").strip()


def _node_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return name.text.decode("utf-8")

    for child in getattr(node, "named_children", []):
        if child.type in {"identifier", "type_identifier", "property_identifier"}:
            return child.text.decode("utf-8")

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


def ast_skeleton(file_path: str) -> str:
    if not detect_language(file_path):
        return ""

    parsed = parse_file(file_path)
    lines: list[str] = []

    for node, depth in _walk_tree(parsed.tree):
        if node.type in TARGET_NODE_TYPES:
            indent = "  " * depth
            lines.append(f"{indent}[{node.type}] {_node_signature(node, parsed.source_code)}")

    return "\n".join(lines)


def list_symbols(file_path: str) -> list[dict[str, object]]:
    if not detect_language(file_path):
        return []

    parsed = parse_file(file_path)
    symbols: list[dict[str, object]] = []

    for node, depth in _walk_tree(parsed.tree):
        if node.type not in TARGET_NODE_TYPES:
            continue
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
                "signature": _node_signature(node, parsed.source_code),
            }
        )

    return symbols
