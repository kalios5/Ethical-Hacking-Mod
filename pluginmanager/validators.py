import ast

# The "format" every plugin must follow, matching what loader.py/
# discover_plugins() expects to find once a plugin is imported.
REQUIRED_NAMES = {"PLUGIN_NAME", "PLUGIN_DESCRIPTION"}
REQUIRED_FUNCS = {"register", "render_widget"}


def validate_plugin_format(source_code: str):
    """
    Confirms the uploaded plugin source defines the required interface:
    the two top-level string constants and the two required functions.

    NOTE: this is a STRUCTURAL check only. It verifies the required
    names/functions are present, but does not inspect what any of the
    code in the file actually does — including any other top-level
    statements that run immediately on import.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return False, f"File is not valid Python: {e}"

    top_level_names = set()
    top_level_funcs = set()

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
