import os
import re
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename

from .loader import discover_plugins, get_plugin
from .models import db, PluginToggle
from .validators import validate_plugin_format

PLUGIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
ALLOWED_EXTENSIONS = {".py"}
MAX_UPLOAD_SIZE = 100 * 1024  # 100 KB — plugins are small, no reason to allow more


def admin_required(view_func):
    """
    Temp placeholder, now always allows the request through.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        return view_func(*args, **kwargs)
    return wrapped


def is_safe_plugin_name(name):
    """Only allow simple folder names — blocks path traversal like '../../x'."""
    return bool(re.fullmatch(r"[a-zA-Z0-9_]+", name))

pluginmanager_bp = Blueprint(
    "pluginmanager", __name__, template_folder="templates"
)


@pluginmanager_bp.route("/")
def index():
    return render_template("home.html")


@pluginmanager_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == "admin" and password == "admin123":
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("pluginmanager.admin_dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@pluginmanager_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("pluginmanager.index"))


@pluginmanager_bp.route("/admin")
def admin_dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("pluginmanager.login"))

    total_plugins = PluginToggle.query.count()
    active_plugins = PluginToggle.query.filter_by(enabled=True).count()
    return render_template(
        "admin_dashboard.html",
        total_plugins=total_plugins,
        active_plugins=active_plugins,
    )


@pluginmanager_bp.route("/plugins", methods=["GET", "POST"])
def plugin_list():
    if request.method == "POST":
        selected = request.form.getlist("active_plugins")
        for name, _module in discover_plugins():
            toggle = PluginToggle.query.filter_by(name=name).first()
            if not toggle:
                toggle = PluginToggle(name=name)
                db.session.add(toggle)
            toggle.enabled = name in selected
        db.session.commit()
        return redirect(url_for("pluginmanager.plugin_list"))

    plugins_data = []
    for name, module in discover_plugins():
        toggle = PluginToggle.query.filter_by(name=name).first()
        if not toggle:
            toggle = PluginToggle(name=name, enabled=False)
            db.session.add(toggle)
            db.session.commit()
        plugins_data.append({
            "name": name,
            "display_name": getattr(module, "PLUGIN_NAME", name),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "enabled": toggle.enabled,
        })
    return render_template("plugin_list.html", plugins=plugins_data)


@pluginmanager_bp.route("/preview")
def storefront_preview():
    outputs = []
    for toggle in PluginToggle.query.filter_by(enabled=True).all():
        module = get_plugin(toggle.name)
        outputs.append(module.render_widget({"customer_name": "Alex"}))
    return render_template("storefront_preview.html", widgets=outputs)


@pluginmanager_bp.route("/plugins/upload", methods=["GET", "POST"])
@admin_required
def upload_plugin():
    error = None

    if request.method == "POST":
        plugin_name = request.form.get("plugin_name", "").strip()
        file = request.files.get("plugin_file")

        if not plugin_name or not is_safe_plugin_name(plugin_name):
            error = "Plugin name must contain only letters, numbers, or underscores."
        elif not file or file.filename == "":
            error = "No file selected."
        else:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()

            #extension whitelist
            if ext not in ALLOWED_EXTENSIONS:
                error = "Only .py files are accepted."
            else:
                source_bytes = file.read()

                #file size limit
                if len(source_bytes) > MAX_UPLOAD_SIZE:
                    error = "Plugin file is too large."
                else:
                    source_text = source_bytes.decode("utf-8", errors="replace")

                    #structural format validation
                    is_valid, format_error = validate_plugin_format(source_text)
                    if not is_valid:
                        error = format_error
                    else:
                        #writes the file to disk as a new plugin package
                        plugin_folder = os.path.join(PLUGIN_DIR, plugin_name)
                        os.makedirs(plugin_folder, exist_ok=True)
                        dest_path = os.path.join(plugin_folder, "__init__.py")
                        with open(dest_path, "wb") as f:
                            f.write(source_bytes)

                        return redirect(url_for("pluginmanager.plugin_list"))

    return render_template("upload_plugin.html", error=error)