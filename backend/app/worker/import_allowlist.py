"""Static AST import-allowlist for untrusted CAD code.

In P0 the part modules are hand-written and trusted, but the gate is built and
exercised now so it is real before any LLM-authored code arrives in P-B. The
gate is one layer of defense-in-depth alongside the OS sandbox (no-network,
write-jailed) in isolation.py.
"""
from __future__ import annotations
import ast

ALLOWED_MODULES = {
    "cadquery", "cq", "math", "json", "typing", "dataclasses",
    "functools", "itertools", "collections", "enum", "numbers", "statistics",
}

DENIED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib",
    "ctypes", "builtins", "multiprocessing", "threading", "signal", "http",
    "urllib", "requests", "ftplib", "pickle", "marshal", "tempfile", "io",
    "asyncio", "code", "pty", "platform", "resource", "fcntl",
}

DENIED_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "globals",
    "locals", "vars", "getattr", "setattr", "delattr", "breakpoint", "memoryview",
}


class AllowlistError(Exception):
    pass


def scan_source(src: str, allow_modules: set[str] | None = None) -> list[str]:
    allow = ALLOWED_MODULES | set(allow_modules or [])
    issues: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in DENIED_MODULES:
                    issues.append(f"denied import: {a.name}")
                elif top not in allow:
                    issues.append(f"non-allowlisted import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in DENIED_MODULES:
                issues.append(f"denied import-from: {node.module}")
            elif top and top not in allow:
                issues.append(f"non-allowlisted import-from: {node.module}")
        elif isinstance(node, ast.Name) and node.id in DENIED_NAMES:
            issues.append(f"denied builtin: {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                issues.append(f"dunder access: {node.attr}")

    return sorted(set(issues))


def assert_safe(src: str, allow_modules: set[str] | None = None) -> None:
    issues = scan_source(src, allow_modules)
    if issues:
        raise AllowlistError("; ".join(issues))
