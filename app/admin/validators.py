"""

top-level statement whitelist: only the two required
assignments, the two required function defs, and docstrings/comments may
appear at the top level. GAP: never looks inside register()'s or
render_widget()'s function bodies.

LAYER 2 - dangerous import blocklist: scans the WHOLE file (ast.walk, not
just top level) for import/from-import of a blocked module. GAP: only
catches literal import statements - __import__('os'), dynamic string
construction, and builtin-only payloads (e.g. open(...).write(...), which
needs no import at all) all bypass this layer.
"""
import ast

REQUIRED_NAMES = {"PLUGIN_NAME", "PLUGIN_DESCRIPTION"}
REQUIRED_FUNCS = {"register", "render_widget"}
BLOCKED_MODULES = {
    "os", "subprocess", "socket", "sys", "importlib",
    "ctypes", "shutil", "pty", "pickle",
}


def validate_plugin_format(source_code: str):
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return False, f"File is not valid Python: {e}"

    ok, err = _check_required_interface(tree)
    if not ok:
        return False, err
    ok, err = _check_top_level_statements(tree)
    if not ok:
        return False, err
    ok, err = _check_dangerous_imports(tree)
    if not ok:
        return False, err
    return True, None


def _check_required_interface(tree):
    top_level_names, top_level_funcs = set(), set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    top_level_names.add(target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_funcs.add(node.name)

    missing_names = REQUIRED_NAMES - top_level_names
    missing_funcs = REQUIRED_FUNCS - top_level_funcs
    if missing_names or missing_funcs:
        missing = sorted(missing_names) + [f"{f}()" for f in sorted(missing_funcs)]
        return False, f"Plugin is missing required elements: {', '.join(missing)}"
    return True, None


def _check_top_level_statements(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if not all(isinstance(t, ast.Name) and t.id in REQUIRED_NAMES for t in node.targets):
                return False, "Only PLUGIN_NAME and PLUGIN_DESCRIPTION may be assigned at the top level."
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in REQUIRED_FUNCS:
                return False, f"Unexpected top-level function: {node.name}()"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        else:
            return False, (
                f"Unexpected top-level statement ({type(node).__name__}). "
                "Only PLUGIN_NAME, PLUGIN_DESCRIPTION, register(), and "
                "render_widget() may appear outside a function body."
            )
    return True, None


def _check_dangerous_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_MODULES:
                    return False, f"Import of '{alias.name}' is not allowed."
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in BLOCKED_MODULES:
                return False, f"Import from '{node.module}' is not allowed."
    return True, None
