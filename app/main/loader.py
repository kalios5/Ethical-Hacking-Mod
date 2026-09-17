import importlib
import pkgutil

from app import plugins  # the top-level plugins package


def discover_plugins():
    """Returns [(folder_name, module), ...] for every plugin found."""
    found = []
    for _finder, name, ispkg in pkgutil.iter_modules(plugins.__path__):
        if ispkg:
            module = importlib.import_module(f"app.plugins.{name}")
            found.append((name, module))
    return found


def get_plugin(name):
    return importlib.import_module(f"plugins.{name}")
