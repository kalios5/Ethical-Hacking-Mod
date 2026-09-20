from flask import render_template, request, redirect, url_for
from app.admin.routes import admin_required
from app.pluginmanager import bp
from app.pluginmanager.loader import discover_plugins, get_plugin
from app.Database.models import db, PluginToggle


@bp.route("/plugins", methods=["GET", "POST"])
@admin_required
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


@bp.route("/preview")
@admin_required
def storefront_preview():
    outputs = []
    for toggle in PluginToggle.query.filter_by(enabled=True).all():
        module = get_plugin(toggle.name)
        outputs.append(module.render_widget({"customer_name": "Alex"}))
    return render_template("storefront_preview.html", widgets=outputs)
