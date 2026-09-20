"""
app/pluginmanager/loader.py  -  plugin discovery + third-party plugin import.

Plugins are just Python packages under app/plugins/<name>/ (see
app/plugins/_template_plugin for the required interface). import_third_party_plugin()
lets an admin upload a .zip of one of those folders at runtime - this is the
project's "malicious plugin upload" lab scenario (see app/logging/db_audit.py's
PLUGIN_IMPORT action and Plugin.is_third_party's column comment). "Checking a
plugin is valid/working" necessarily means importing and running the
uploaded code with the app's own privileges, same as get_plugin() below
always has - that execution is the intended vulnerability, not something
this module tries to sandbox away. What IS handled here is ordinary
engineering hygiene: a safe folder/module name, a zip-slip-safe extraction,
size limits, and rolling back cleanly on a bad upload.
"""
import importlib
import os
import pkgutil
import re
import shutil
import sys
import tempfile
import zipfile

from app import plugins  # the top-level plugins package

PLUGINS_DIR = plugins.__path__[0]

# Shipped plugins - import_third_party_plugin() refuses to overwrite these.
BUILTIN_PLUGIN_NAMES = {"welcome_message", "discount_banner", "newsletter_signup"}

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")

MAX_ZIP_ENTRIES = 200
MAX_ZIP_UNCOMPRESSED_BYTES = 2 * 1024 * 1024  # 2 MB, hygiene not a hard limit


class PluginValidationError(Exception):
    """Raised for any reason an uploaded plugin was rejected."""


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


def _validate_name(name):
    if not name or not _NAME_RE.match(name):
        raise PluginValidationError(
            "Plugin name must be lowercase letters, digits, and underscores, "
            "starting with a letter (2-50 characters)."
        )


def _reject_builtin_collision(name):
    from app.Database.models import Plugin

    clash = Plugin.query.filter_by(name=name, is_third_party=False).first()
    if clash is not None:
        raise PluginValidationError(f'"{name}" is a built-in plugin and cannot be overwritten.')


def _safe_member_path(staging_dir, member_name):
    """Resolve a zip member's target path, raising if it would escape
    staging_dir (zip-slip) or uses an absolute/drive path."""
    if os.path.isabs(member_name) or (len(member_name) > 1 and member_name[1] == ":"):
        raise PluginValidationError(f"Zip contains an absolute path: {member_name!r}")
    target = os.path.realpath(os.path.join(staging_dir, member_name))
    staging_real = os.path.realpath(staging_dir)
    if target != staging_real and not target.startswith(staging_real + os.sep):
        raise PluginValidationError(f"Zip entry escapes its own folder: {member_name!r}")
    return target


def _extract_zip_safely(file_storage, staging_dir):
    """Extracts file_storage (a werkzeug FileStorage) into staging_dir,
    guarding against zip-slip and pathological archives. Returns the
    directory that actually contains __init__.py (handles a zip that wraps
    everything in one top-level folder, e.g. from "zip this folder" in a
    file browser)."""
    try:
        zf = zipfile.ZipFile(file_storage.stream)
    except zipfile.BadZipFile:
        raise PluginValidationError("That file isn't a valid .zip archive.")

    with zf:
        infos = zf.infolist()
        if not infos:
            raise PluginValidationError("The zip archive is empty.")
        if len(infos) > MAX_ZIP_ENTRIES:
            raise PluginValidationError(f"Zip has too many entries (max {MAX_ZIP_ENTRIES}).")
        total_size = sum(i.file_size for i in infos)
        if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise PluginValidationError(
                f"Zip is too large uncompressed (max {MAX_ZIP_UNCOMPRESSED_BYTES // 1024} KB)."
            )

        for info in infos:
            if info.filename.startswith("..") or "/../" in info.filename or "\\..\\" in info.filename:
                raise PluginValidationError(f"Zip entry uses a parent path: {info.filename!r}")
            target = _safe_member_path(staging_dir, info.filename)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    return _locate_plugin_root(staging_dir)


def _locate_plugin_root(staging_dir):
    if os.path.isfile(os.path.join(staging_dir, "__init__.py")):
        return staging_dir

    # Common case: the zip wraps everything in one top-level folder.
    entries = [e for e in os.listdir(staging_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1 and os.path.isdir(os.path.join(staging_dir, entries[0])):
        candidate = os.path.join(staging_dir, entries[0])
        if os.path.isfile(os.path.join(candidate, "__init__.py")):
            return candidate

    raise PluginValidationError("Zip must contain an __init__.py (at its root, or in one wrapping folder).")


def _validate_plugin_module(module):
    display_name = getattr(module, "PLUGIN_NAME", None)
    if not isinstance(display_name, str) or not display_name.strip():
        raise PluginValidationError("Plugin is missing a valid PLUGIN_NAME string.")

    description = getattr(module, "PLUGIN_DESCRIPTION", None)
    if not isinstance(description, str):
        raise PluginValidationError("Plugin is missing a valid PLUGIN_DESCRIPTION string.")

    render_widget = getattr(module, "render_widget", None)
    if not callable(render_widget):
        raise PluginValidationError("Plugin has no render_widget(context) function.")
    try:
        output = render_widget({"customer_name": "Preview"})
    except Exception as exc:
        raise PluginValidationError(f"render_widget() raised {exc!r}.")
    if not isinstance(output, str):
        raise PluginValidationError("render_widget() must return a string of HTML.")

    register = getattr(module, "register", None)
    if register is not None:
        if not callable(register):
            raise PluginValidationError("register must be a function.")
        try:
            register(shop=None)
        except Exception as exc:
            raise PluginValidationError(f"register() raised {exc!r}.")


def _purge_module_cache(name):
    """Drop app.plugins.<name> and any of its submodules from sys.modules so
    a re-upload of the same name is actually re-imported from disk, instead
    of returning Python's cached (stale) module object."""
    prefix = f"app.plugins.{name}"
    for key in [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]:
        del sys.modules[key]


def import_third_party_plugin(name, file_storage):
    """Validates and installs an uploaded plugin zip as app/plugins/<name>/.

    Returns the freshly-imported, validated module on success. Raises
    PluginValidationError (with a human-readable reason) on any failure,
    leaving app/plugins/ exactly as it was before the call.
    """
    if file_storage is None or not file_storage.filename:
        raise PluginValidationError("No file was uploaded.")
    if not file_storage.filename.lower().endswith(".zip"):
        raise PluginValidationError("Upload a .zip file.")

    _validate_name(name)
    _reject_builtin_collision(name)

    target_dir = os.path.join(PLUGINS_DIR, name)
    backup_dir = None

    with tempfile.TemporaryDirectory(prefix="plugin_import_") as staging_dir:
        plugin_root = _extract_zip_safely(file_storage, staging_dir)

        try:
            if os.path.exists(target_dir):
                backup_dir = target_dir + ".bak"
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)
                shutil.move(target_dir, backup_dir)
            shutil.copytree(plugin_root, target_dir)

            _purge_module_cache(name)
            module = importlib.import_module(f"app.plugins.{name}")
            _validate_plugin_module(module)
        except PluginValidationError:
            shutil.rmtree(target_dir, ignore_errors=True)
            if backup_dir is not None:
                shutil.move(backup_dir, target_dir)
            _purge_module_cache(name)
            raise
        else:
            if backup_dir is not None:
                shutil.rmtree(backup_dir, ignore_errors=True)
            return module
