from flask import Blueprint, render_template, request, redirect, url_for, session

from .loader import discover_plugins, get_plugin
from .models import db, PluginToggle

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
