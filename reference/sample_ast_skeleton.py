from __future__ import annotations

from pathlib import Path

from tree_sitter import Parser
import tree_sitter_languages

LANGUAGE_BY_EXTENSION = {
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


def generate_ast_skeleton(file_path: str) -> str:
    """Generate a declaration-only AST skeleton for supported source files."""
    suffix = Path(file_path).suffix.lower().lstrip(".")
    language_name = LANGUAGE_BY_EXTENSION.get(suffix, "")
    if not language_name:
        return ""

    source_code = Path(file_path).read_text(encoding="utf-8")
    parser = Parser()
    parser.set_language(tree_sitter_languages.get_language(language_name))
    tree = parser.parse(source_code.encode("utf-8"))

    cursor = tree.walk()
    skeleton_lines: list[str] = []
    reached_root = False

    while not reached_root:
        node = cursor.node
        if node.type in TARGET_NODE_TYPES:
            start = node.start_byte
            body = node.child_by_field_name("body")
            end = body.start_byte if body else node.end_byte
            sig = source_code[start:end].strip().replace("{", "").strip()
            indent = "  " * cursor.depth
            skeleton_lines.append(f"{indent}[{node.type}] {sig}")

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

    return "\n".join(skeleton_lines)
