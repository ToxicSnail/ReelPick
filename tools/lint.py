from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_LINE_LENGTH = 100
IGNORED_PARTS = {".git", ".venv", "venv", "__pycache__"}


class LintVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors: list[str] = []

    def error(self, node: ast.AST, message: str) -> None:
        self.errors.append(f"{self.path.relative_to(ROOT)}:{node.lineno}: {message}")

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if node.type is None:
            self.error(node, "bare except is forbidden")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if any(alias.name == "*" for alias in node.names):
            self.error(node, "wildcard import is forbidden")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            self.error(node, f"{node.func.id}() is forbidden")
        if (
            "kinotyk" in self.path.relative_to(ROOT).parts
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            self.error(node, "use logging instead of print() in application code")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._check_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._check_defaults(node)
        self.generic_visit(node)

    def _check_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.error(node, "mutable function default is forbidden")


def python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not any(part in IGNORED_PARTS for part in path.parts)
    )


def lint_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT)

    for number, line in enumerate(text.splitlines(), start=1):
        if "\t" in line:
            errors.append(f"{relative}:{number}: tab character is forbidden")
        if line.rstrip() != line:
            errors.append(f"{relative}:{number}: trailing whitespace")
        if len(line) > MAX_LINE_LENGTH:
            errors.append(
                f"{relative}:{number}: line too long ({len(line)} > {MAX_LINE_LENGTH})"
            )

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        errors.append(f"{relative}:{exc.lineno}: syntax error: {exc.msg}")
        return errors

    visitor = LintVisitor(path)
    visitor.visit(tree)
    errors.extend(visitor.errors)
    return errors


def main() -> int:
    errors: list[str] = []
    for path in python_files():
        errors.extend(lint_file(path))

    if errors:
        print("Lint failed:")
        for error in errors:
            print(f"  {error}")
        return 1

    print(f"Lint OK: {len(python_files())} Python files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
