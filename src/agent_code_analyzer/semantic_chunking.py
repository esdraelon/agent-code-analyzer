from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .parsing import ParsedFile

METHOD_NODE_TYPES: tuple[str, ...] = (
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
)

BODY_NODE_TYPES: tuple[str, ...] = (
    "block",
    "body",
    "compound_statement",
    "statement_block",
    "suite",
)

CONTROL_FLOW_NODE_TYPES: set[str] = {
    "if_statement",
    "elif_clause",
    "else_clause",
    "for_statement",
    "for_in_statement",
    "foreach_statement",
    "while_statement",
    "do_statement",
    "switch_statement",
    "match_statement",
    "case_statement",
    "try_statement",
    "catch_clause",
    "finally_clause",
    "with_statement",
}


@dataclass(frozen=True, slots=True)
class SemanticChunkSpan:
    chunk_index: int
    chunk_total: int
    line_start: int
    line_end: int
    start_byte: int
    end_byte: int
    chunk_text: str
    outline_text: str
    split_reason: str
    is_split: bool
    statement_count: int


def _decode_source_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _walk_tree(tree: Any):
    cursor = tree.walk()
    reached_root = False
    while not reached_root:
        node = cursor.node
        yield node
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


def _node_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return _decode_source_bytes(name.text)
    for child in getattr(node, "named_children", []):
        if child.type in {"identifier", "type_identifier", "property_identifier"}:
            return _decode_source_bytes(child.text)
    return ""


def _find_symbol_node(parsed: ParsedFile, symbol: dict[str, Any]) -> Any | None:
    symbol_type = str(symbol.get("type", "")).strip()
    if not symbol_type:
        return None

    expected_name = str(symbol.get("name", "")).strip()
    expected_start = symbol.get("start_point") or {}
    expected_end = symbol.get("end_point") or {}
    expected_start_row = int(expected_start.get("row", -1))
    expected_start_column = int(expected_start.get("column", -1))
    expected_end_row = int(expected_end.get("row", -1))
    expected_end_column = int(expected_end.get("column", -1))

    for node in _walk_tree(parsed.tree):
        if node.type != symbol_type:
            continue
        if expected_start_row >= 0 and int(node.start_point[0]) != expected_start_row:
            continue
        if expected_start_column >= 0 and int(node.start_point[1]) != expected_start_column:
            continue
        if expected_end_row >= 0 and int(node.end_point[0]) != expected_end_row:
            continue
        if expected_end_column >= 0 and int(node.end_point[1]) != expected_end_column:
            continue
        if expected_name and _node_name(node) and _node_name(node) != expected_name:
            continue
        return node
    return None


def _method_body_node(node: Any) -> Any | None:
    body = node.child_by_field_name("body")
    if body is not None:
        return body
    for child in getattr(node, "named_children", []):
        if child.type in BODY_NODE_TYPES:
            return child
    return None


def _statement_children(body_node: Any) -> list[Any]:
    return [child for child in getattr(body_node, "named_children", []) if child.is_named and child.type != "comment"]


def _slice_text(source_bytes: bytes, start_byte: int, end_byte: int) -> str:
    if end_byte < start_byte:
        end_byte = start_byte
    return _decode_source_bytes(source_bytes[start_byte:end_byte]).strip()


def _is_control_flow(node: Any) -> bool:
    return node.type in CONTROL_FLOW_NODE_TYPES


def _group_statement_nodes(statement_nodes: list[Any], *, max_chunk_lines: int) -> list[list[Any]]:
    if not statement_nodes:
        return []

    groups: list[list[Any]] = []
    current: list[Any] = [statement_nodes[0]]
    current_start_row = int(statement_nodes[0].start_point[0])

    for node in statement_nodes[1:]:
        prospective_lines = int(node.end_point[0]) - current_start_row + 1
        force_split = _is_control_flow(node)
        if force_split or prospective_lines > max_chunk_lines:
            groups.append(current)
            current = [node]
            current_start_row = int(node.start_point[0])
            continue
        current.append(node)

    groups.append(current)
    return groups


def build_method_chunk_spans(
    parsed: ParsedFile,
    symbol: dict[str, Any],
    *,
    max_chunk_lines: int = 12,
    min_split_lines: int = 8,
) -> list[SemanticChunkSpan]:
    """Return AST-aware chunk spans for a method/function symbol."""

    node = _find_symbol_node(parsed, symbol)
    if node is None:
        source_text = _decode_source_bytes(parsed.source_bytes)
        return [
            SemanticChunkSpan(
                chunk_index=0,
                chunk_total=1,
                line_start=int(symbol.get("start_point", {}).get("row", 0)),
                line_end=int(symbol.get("end_point", {}).get("row", 0)),
                start_byte=0,
                end_byte=len(parsed.source_bytes),
                chunk_text=source_text.strip(),
                outline_text=str(symbol.get("signature", "")).strip() or str(symbol.get("name", "")).strip() or symbol.get("type", "method"),
                split_reason="fallback-node-missing",
                is_split=False,
                statement_count=0,
            )
        ]

    body = _method_body_node(node)
    if body is None:
        return [
            SemanticChunkSpan(
                chunk_index=0,
                chunk_total=1,
                line_start=int(node.start_point[0]),
                line_end=int(node.end_point[0]),
                start_byte=int(node.start_byte),
                end_byte=int(node.end_byte),
                chunk_text=_slice_text(parsed.source_bytes, int(node.start_byte), int(node.end_byte)),
                outline_text=str(symbol.get("signature", "")).strip() or str(symbol.get("name", "")).strip() or node.type,
                split_reason="whole-method",
                is_split=False,
                statement_count=0,
            )
        ]

    statement_nodes = _statement_children(body)
    method_line_count = int(node.end_point[0]) - int(node.start_point[0]) + 1
    should_split = method_line_count > min_split_lines and len(statement_nodes) > 1
    if not should_split:
        return [
            SemanticChunkSpan(
                chunk_index=0,
                chunk_total=1,
                line_start=int(node.start_point[0]),
                line_end=int(node.end_point[0]),
                start_byte=int(node.start_byte),
                end_byte=int(node.end_byte),
                chunk_text=_slice_text(parsed.source_bytes, int(node.start_byte), int(node.end_byte)),
                outline_text=str(symbol.get("signature", "")).strip() or str(symbol.get("name", "")).strip() or node.type,
                split_reason="whole-method",
                is_split=False,
                statement_count=len(statement_nodes),
            )
        ]

    groups = _group_statement_nodes(statement_nodes, max_chunk_lines=max_chunk_lines)
    spans: list[SemanticChunkSpan] = []
    outline_text = str(symbol.get("signature", "")).strip() or str(symbol.get("name", "")).strip() or node.type
    for index, group in enumerate(groups):
        start_node = group[0]
        end_node = group[-1]
        start_byte = int(start_node.start_byte)
        end_byte = int(end_node.end_byte)
        spans.append(
            SemanticChunkSpan(
                chunk_index=index,
                chunk_total=len(groups),
                line_start=int(start_node.start_point[0]),
                line_end=int(end_node.end_point[0]),
                start_byte=start_byte,
                end_byte=end_byte,
                chunk_text=_slice_text(parsed.source_bytes, start_byte, end_byte),
                outline_text=outline_text,
                split_reason="ast-region" if any(_is_control_flow(child) for child in group) else "line-budget",
                is_split=True,
                statement_count=len(group),
            )
        )
    return spans
