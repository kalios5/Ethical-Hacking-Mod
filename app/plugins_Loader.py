import importlib
import pkgutil

from app import plugins


def register_plugins(app):
	"""Discover and register every app plugin with the Flask application."""
	for _finder, name, is_package in pkgutil.iter_modules(plugins.__path__):
		if not is_package or name.startswith("_"):
			continue

		plugin = importlib.import_module(f"app.plugins.{name}")
		register = getattr(plugin, "register", None)
		if register is not None:
			register(app)
