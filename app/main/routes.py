from flask import render_template, request, redirect, url_for
from app.main import bp
from app.main.loader import discover_plugins, get_plugin
from app.models import db, PluginToggle

@bp.route('/')
def home():
    return "<h1>hi</h1>"


@bp.route("/plugins", methods=["GET", "POST"])
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
        return redirect(url_for("main.plugin_list"))

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
def storefront_preview():
    outputs = []
    for toggle in PluginToggle.query.filter_by(enabled=True).all():
        module = get_plugin(toggle.name)
        outputs.append(module.render_widget({"customer_name": "Alex"}))
    return render_template("storefront_preview.html", widgets=outputs)
