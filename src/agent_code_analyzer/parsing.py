from __future__ import annotations

import html
import re
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
    "css": "css",
    "go": "go",
    "h": "c",
    "htm": "html",
    "html": "html",
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
    "sql": "sql",
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
SQL_KEYWORDS_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmbeddedLanguageBlock:
    language: str
    source_bytes: bytes
    source_code: str
    start_point: dict[str, int]
    end_point: dict[str, int]


@dataclass(frozen=True)
class TreeSitterSourceParser:
    """Small parsing facade that keeps parser construction in one place."""

    def parse_bytes(
        self,
        language_name: str,
        source_bytes: bytes,
        *,
        source_code: str,
        file_path: str,
    ) -> "ParsedFile":
        parser = Parser()
        parser.set_language(resolve_language(language_name))
        tree = parser.parse(source_bytes)
        return ParsedFile(
            file_path=file_path,
            language=language_name,
            source_bytes=source_bytes,
            source_code=source_code,
            tree=tree,
            languages=(language_name,),
        )

    def parse_text(self, language_name: str, source_text: str, file_path: str = "<memory>") -> "ParsedFile":
        source_bytes = source_text.encode("utf-8")
        return self.parse_bytes(
            language_name,
            source_bytes,
            source_code=source_text,
            file_path=file_path,
        )

    def parse_file(self, file_path: str, language_name: str) -> "ParsedFile":
        source_path = Path(file_path)
        source_bytes, source_code = _read_source_text(source_path)
        return self.parse_bytes(
            language_name,
            source_bytes,
            source_code=source_code,
            file_path=str(source_path),
        )


@dataclass(frozen=True)
class SymbolLanguageStrategy:
    """Encapsulate language attribution rules for files and embedded fragments."""

    def symbol_languages(self, base_language: str, source_text: str) -> list[str]:
        languages = [base_language]
        if base_language in {"php", "javascript", "typescript", "tsx", "jsx", "python", "ruby", "go"}:
            if SQL_KEYWORDS_RE.search(source_text) and "sql" not in languages:
                languages.append("sql")
        if base_language == "html":
            lowered = source_text.lower()
            if "<script" in lowered and "javascript" not in languages:
                languages.append("javascript")
            if "<style" in lowered and "css" not in languages:
                languages.append("css")
        return _dedupe_languages(languages)

    def iter_embedded_blocks(self, parsed: "ParsedFile") -> Iterator[EmbeddedLanguageBlock]:
        if parsed.language != "html":
            return

        for pattern, language in (
            (rb"<script\b[^>]*>(.*?)</script>", "javascript"),
            (rb"<style\b[^>]*>(.*?)</style>", "css"),
        ):
            for match in re.finditer(pattern, parsed.source_bytes, flags=re.IGNORECASE | re.DOTALL):
                content_start = match.start(1)
                content_end = match.end(1)
                block_source_bytes = parsed.source_bytes[content_start:content_end]
                block_source_text = _decode_source_bytes(block_source_bytes)
                start_row, start_column = _byte_offset_to_point(parsed.source_bytes, content_start)
                end_row, end_column = _byte_offset_to_point(parsed.source_bytes, content_end)
                yield EmbeddedLanguageBlock(
                    language=language,
                    source_bytes=block_source_bytes,
                    source_code=block_source_text,
                    start_point={"row": start_row, "column": start_column},
                    end_point={"row": end_row, "column": end_column},
                )

    def file_languages(
        self,
        parsed: "ParsedFile",
        *,
        symbol_languages: list[str],
        embedded_languages: list[str],
    ) -> list[str]:
        return _dedupe_languages([parsed.language, *embedded_languages, *symbol_languages])


SOURCE_PARSER = TreeSitterSourceParser()
LANGUAGE_STRATEGY = SymbolLanguageStrategy()


@dataclass(frozen=True)
class ParsedFile:
    file_path: str
    language: str
    source_bytes: bytes
    source_code: str
    tree: Any
    languages: tuple[str, ...] = ()


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


def parse_source_text(language_name: str, source_text: str, file_path: str = "<memory>") -> ParsedFile:
    return SOURCE_PARSER.parse_text(language_name, source_text, file_path=file_path)


def parse_file(file_path: str) -> ParsedFile:
    language_name = detect_language(file_path)
    if not language_name:
        raise ValueError(f"Unsupported file extension for Tree-sitter: {file_path}")

    return SOURCE_PARSER.parse_file(file_path, language_name)


def _byte_offset_to_point(source_bytes: bytes, offset: int) -> tuple[int, int]:
    prefix = source_bytes[:offset]
    row = prefix.count(b"\n")
    last_newline = prefix.rfind(b"\n")
    if last_newline == -1:
        column = offset
    else:
        column = offset - last_newline - 1
    return row, column


def _point_with_offset(point: tuple[int, int], row_offset: int, column_offset: int) -> dict[str, int]:
    row, column = point
    if row == 0:
        return {"row": row_offset, "column": column_offset + column}
    return {"row": row_offset + row, "column": column}


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


def _dedupe_languages(languages: list[str]) -> list[str]:
    ordered: list[str] = []
    for language in languages:
        if language and language not in ordered:
            ordered.append(language)
    return ordered


def _symbol_languages(base_language: str, signature: str, source_text: str) -> list[str]:
    return LANGUAGE_STRATEGY.symbol_languages(base_language, source_text)


def _symbol_record(
    node: Any,
    *,
    base_language: str,
    source_bytes: bytes,
    row_offset: int = 0,
    column_offset: int = 0,
) -> tuple[dict[str, Any], str]:
    signature = _node_signature(node, source_bytes)
    source_text = _decode_source_bytes(source_bytes[node.start_byte : node.end_byte])
    start_point = _point_with_offset(node.start_point, row_offset, column_offset)
    end_point = _point_with_offset(node.end_point, row_offset, column_offset)
    languages = _symbol_languages(base_language, signature, source_text)
    symbol = {
        "type": node.type,
        "name": _node_name(node),
        "depth": 0,  # filled by caller
        "start_point": start_point,
        "end_point": end_point,
        "signature": signature,
        "languages": languages,
    }
    return symbol, signature


def _collect_target_symbols(
    parsed: ParsedFile,
    *,
    row_offset: int = 0,
    column_offset: int = 0,
    base_language: str | None = None,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    skeleton_lines: list[str] = []
    symbols: list[dict[str, Any]] = []
    languages_seen: list[str] = []
    effective_language = base_language or parsed.language

    for node, depth in _walk_tree(parsed.tree):
        if node.type not in TARGET_NODE_TYPES:
            continue
        symbol, signature = _symbol_record(
            node,
            base_language=effective_language,
            source_bytes=parsed.source_bytes,
            row_offset=row_offset,
            column_offset=column_offset,
        )
        symbol["depth"] = depth
        skeleton_lines.append(f"{'  ' * depth}[{node.type}] {signature}")
        symbols.append(symbol)
        languages_seen.extend(symbol["languages"])

    return skeleton_lines, symbols, languages_seen


def _iter_html_embedded_blocks(parsed: ParsedFile) -> Iterator[dict[str, Any]]:
    if parsed.language != "html":
        return

    for block in LANGUAGE_STRATEGY.iter_embedded_blocks(parsed):
        yield {
            "language": block.language,
            "source_bytes": block.source_bytes,
            "source_code": block.source_code,
            "start_point": block.start_point,
            "end_point": block.end_point,
        }


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
    skeleton_lines, symbols, symbol_languages = _collect_target_symbols(parsed)
    embedded_languages: list[str] = []

    if parsed.language == "html":
        for block in LANGUAGE_STRATEGY.iter_embedded_blocks(parsed):
            fragment = parse_source_text(
                block.language,
                block.source_code,
                file_path=f"{parsed.file_path}::{block.language}",
            )
            fragment_skeleton, fragment_symbols, fragment_languages = _collect_target_symbols(
                fragment,
                row_offset=block.start_point["row"],
                column_offset=block.start_point["column"],
                base_language=block.language,
            )
            skeleton_lines.extend(fragment_skeleton)
            symbols.extend(fragment_symbols)
            symbol_languages.extend(fragment_languages)
            embedded_languages.append(block.language)

    file_languages = LANGUAGE_STRATEGY.file_languages(
        parsed,
        symbol_languages=symbol_languages,
        embedded_languages=embedded_languages,
    )

    return {
        "parsed": parsed,
        "skeleton": "\n".join(skeleton_lines),
        "symbols": symbols,
        "languages": file_languages,
        "symbol_health": _symbol_health_report(
            symbols,
            has_error=bool(parsed.tree.root_node.has_error),
        ),
    }


def render_ast_svg(
    *,
    file_path: str,
    language: str,
    root_type: str,
    skeleton: str,
    symbol_count: int = 0,
    node_count: int | None = None,
) -> str:
    lines = [line.rstrip() for line in skeleton.splitlines() if line.strip()]
    if not lines:
        fallback_name = Path(file_path).name or file_path or "root"
        lines = [f"[{root_type or 'root'}] {fallback_name}"]

    parsed_lines: list[tuple[int, str, str]] = []
    for raw_line in lines[:22]:
        match = re.match(r"^(?P<indent>\s*)\[(?P<type>[^\]]+)\]\s*(?P<label>.*)$", raw_line)
        if match is None:
            parsed_lines.append((0, "node", raw_line.strip()))
            continue
        depth = len(match.group("indent")) // 2
        node_type = match.group("type").strip() or "node"
        label = match.group("label").strip() or node_type
        parsed_lines.append((depth, node_type, label))

    max_depth = max((depth for depth, _, _ in parsed_lines), default=0)
    longest_label = max((len(f"[{node_type}] {label}") for _, node_type, label in parsed_lines), default=24)
    width = max(860, min(1600, int(260 + (max_depth + 1) * 44 + longest_label * 7.4)))
    row_height = 54
    header_height = 92
    footer_height = 34
    margin = 24
    height = header_height + len(parsed_lines) * row_height + footer_height + margin

    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Tree-sitter AST for {esc(file_path)}">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0%" stop-color="#f8fbff"/>',
        '<stop offset="100%" stop-color="#edf2ff"/>',
        "</linearGradient>",
        '<linearGradient id="nodeFill" x1="0" y1="0" x2="0" y2="1">',
        '<stop offset="0%" stop-color="#ffffff"/>',
        '<stop offset="100%" stop-color="#eef2ff"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="24" fill="url(#bg)"/>',
        f'<text x="28" y="36" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="22" font-weight="700" fill="#1d2433">Tree-sitter AST</text>',
        f'<text x="28" y="58" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#667085">{esc(language or "unknown")} · root: {esc(root_type or "unknown")} · symbols: {symbol_count} · nodes: {node_count if node_count is not None else len(parsed_lines)}</text>',
        f'<text x="28" y="78" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#667085">{esc(file_path)}</text>',
    ]

    last_at_depth: dict[int, tuple[float, float, float, float]] = {}
    for index, (depth, node_type, label) in enumerate(parsed_lines):
        x = float(margin + depth * 42)
        y = float(header_height + index * row_height)
        node_label = f"[{node_type}] {label}"
        box_width = min(width - int(x) - margin, max(280, int(320 + min(len(node_label), 90) * 6.2)))
        box_height = 34
        if depth > 0 and (depth - 1) in last_at_depth:
            parent_x, parent_y, parent_w, parent_h = last_at_depth[depth - 1]
            child_center_x = x + box_width / 2
            parent_center_x = parent_x + parent_w / 2
            parts.append(
                f'<path d="M {parent_center_x:.1f} {parent_y + parent_h:.1f} C {parent_center_x:.1f} {parent_y + parent_h + 10:.1f}, {child_center_x:.1f} {y - 12:.1f}, {child_center_x:.1f} {y:.1f}" stroke="#9aa7c7" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
            )
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{box_width}" height="{box_height}" rx="12" fill="url(#nodeFill)" stroke="#c9d4f5"/>',
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(92, min(box_width, 180))}" height="{box_height}" rx="12" fill="#e8eeff" opacity="0.85"/>',
                f'<text x="{x + 12:.1f}" y="{y + 14:.1f}" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace" font-size="11" font-weight="700" fill="#3244a6">{esc(node_type)}</text>',
                f'<text x="{x + 12:.1f}" y="{y + 28:.1f}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#1d2433">{esc(label[:96] + ("…" if len(label) > 96 else ""))}</text>',
            ]
        )
        last_at_depth[depth] = (x, y, float(box_width), float(box_height))
        for key in list(last_at_depth):
            if key > depth:
                del last_at_depth[key]

    parts.extend(
        [
            f'<text x="28" y="{height - 12}" font-family="Inter, ui-sans-serif, system-ui, sans-serif" font-size="12" fill="#667085">Rendered from Tree-sitter parse data</text>',
            "</svg>",
        ]
    )
    return "".join(parts)


def ast_skeleton(file_path: str) -> str:
    if not detect_language(file_path):
        return ""
    return analyze_file(file_path)["skeleton"]


def list_symbols(file_path: str) -> list[dict[str, object]]:
    if not detect_language(file_path):
        return []
    return analyze_file(file_path)["symbols"]
