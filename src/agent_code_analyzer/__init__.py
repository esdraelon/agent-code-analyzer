"""Agent Code Analyzer: Tree-sitter MCP helpers for structural code analysis."""

from .parsing import ast_skeleton as generate_ast_skeleton

__all__ = ["__version__", "generate_ast_skeleton"]
__version__ = "0.1.0"
