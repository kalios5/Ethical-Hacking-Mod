"""
app/pluginmanager/loader.py  -  plugin discovery.

Plugins are Python packages under app/plugins/<name>/ (see
app/plugins/_template_plugin for the required interface). Third-party
plugins are installed via the single-file .py upload path in
app/admin/routes.py (upload_plugin) - a folder is created and the uploaded
file becomes its __init__.py.

Loading a plugin means importing it, which runs its module-level code, and
rendering it calls render_widget() - executing the uploaded code with the
app's own privileges. That execution is the project's intended, documented
vulnerability (see app/logging/db_audit.py's PLUGIN_IMPORT action and
Plugin.is_third_party). The upload path applies real hardening around it
(see app/admin/validators.py and app/pluginmanager/sandbox.py) so that the
ONLY thing that gets through is that one intended vector.

NOTE: the earlier .zip import path was removed. Once third-party uploads
were restricted to a single file (the only file the validator inspects),
a multi-file archive was just extra attack surface and code with no
remaining benefit over a plain .py upload.
"""
import importlib
import pkgutil

from app import plugins  # the top-level plugins package

PLUGINS_DIR = plugins.__path__[0]

# Shipped plugins - the upload path refuses to overwrite these.
BUILTIN_PLUGIN_NAMES = {"welcome_message", "discount_banner", "newsletter_signup"}


def discover_plugins():
    """Returns [(folder_name, module), ...] for every installed plugin.
    Names starting with "_" (e.g. _template_plugin, the scaffold folder) are
    skipped - it's not a real plugin, just documentation for how to write
    one."""
    found = []
    for _finder, name, ispkg in pkgutil.iter_modules(plugins.__path__):
        if ispkg and not name.startswith("_"):
            module = importlib.import_module(f"app.plugins.{name}")
            found.append((name, module))
    return found


def get_plugin(name):
    return importlib.import_module(f"app.plugins.{name}")


def _purge_module_cache_safe(name):
    """Drop app.plugins.<name> and any submodules from sys.modules so a
    re-upload of the same name is re-imported from disk instead of
    returning Python's cached (stale) module object."""
    import sys
    prefix = f"app.plugins.{name}"
    for key in [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]:
        del sys.modules[key]
