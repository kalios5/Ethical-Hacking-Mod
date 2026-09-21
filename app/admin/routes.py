import os
import re
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app import db
from app.admin import bp
from app.admin.validators import validate_plugin_format
from app.auth.routes import current_user, login_required
from app.Database.models import Order, Plugin, Product, Shop, User
from app.logging.db_audit import actions, audit
from extensions import limiter
# NOT imported at module level: app.pluginmanager.routes imports
# admin_required from this module, so importing app.pluginmanager here too
# (even indirectly, via app.pluginmanager.loader triggering
# app/pluginmanager/__init__.py) would be a circular import before
# admin_required is defined below. Imported lazily inside plugins() instead.

PLUGIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
ALLOWED_EXTENSIONS = {".py"}
MAX_UPLOAD_SIZE = 100 * 1024


def is_safe_plugin_name(name):
    return bool(re.fullmatch(r"[a-zA-Z0-9_]+", name))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user().role not in ("admin", "superadmin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def current_shop():
    return Shop.query.order_by(Shop.id).first()


@bp.route("/")
@admin_required
def dashboard():
    shop = current_shop()
    return render_template(
        "admin/dashboard.html",
        shop=shop,
        product_count=Product.query.filter_by(shop_id=shop.id).count(),
        order_count=Order.query.filter_by(shop_id=shop.id).count(),
        customer_count=User.query.filter_by(shop_id=shop.id, role="customer").count(),
    )


@bp.route("/products", methods=["GET", "POST"])
@admin_required
def products():
    shop = current_shop()
    if request.method == "POST":
        try:
            price_cents = round(float(request.form.get("price", "0")) * 100)
            stock = int(request.form.get("stock", "0"))
        except ValueError:
            flash("Price and stock must be valid numbers.", "error")
        else:
            name = request.form.get("name", "").strip()
            if not name or price_cents < 0 or stock < 0:
                flash("Provide a product name, non-negative price, and non-negative stock.", "error")
            else:
                db.session.add(Product(shop_id=shop.id, name=name, description=request.form.get("description", "").strip(), price_cents=price_cents, stock=stock))
                db.session.commit()
                flash("Product created.", "success")
                return redirect(url_for("admin.products"))
    return render_template("admin/products.html", products=Product.query.filter_by(shop_id=shop.id).order_by(Product.created_at.desc()).all())


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=current_shop().id).first_or_404()
    if request.method == "POST":
        product.name = request.form.get("name", "").strip()
        product.description = request.form.get("description", "").strip()
        product.price_cents = round(float(request.form.get("price", "0")) * 100)
        product.stock = int(request.form.get("stock", "0"))
        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_edit.html", product=product)


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=current_shop().id).first_or_404()
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin.products"))


@bp.route("/plugins", methods=["GET", "POST"])
@admin_required
def plugins():
    from app.pluginmanager.loader import BUILTIN_PLUGIN_NAMES, discover_plugins

    shop = current_shop()
    if request.method == "POST":
        selected = set(request.form.getlist("active_plugins"))
        for name, _module in discover_plugins():
            plugin = Plugin.query.filter_by(shop_id=shop.id, name=name).first()
            if plugin is None:
                plugin = Plugin(shop_id=shop.id, name=name)
                db.session.add(plugin)
            plugin.enabled = name in selected
        db.session.commit()
        audit(actions.PLUGIN_TOGGLE, actor=current_user(), shop_id=shop.id,
              detail=f"active_plugins={sorted(selected)}")
        flash("Plugin settings updated.", "success")
        return redirect(url_for("admin.plugins"))

    rows = {row.name: row for row in Plugin.query.filter_by(shop_id=shop.id).all()}
    plugin_data = [
        {
            "name": name,
            "display_name": getattr(module, "PLUGIN_NAME", name),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "enabled": rows[name].enabled if name in rows else False,
            "is_third_party": rows[name].is_third_party if name in rows else name not in BUILTIN_PLUGIN_NAMES,
        }
        for name, module in discover_plugins()
    ]
    return render_template("admin/plugins.html", plugins=plugin_data)


@bp.route("/plugins/import", methods=["POST"])
@admin_required
@limiter.limit("5 per minute")
def import_plugin():
    from app.pluginmanager.loader import PluginValidationError, import_third_party_plugin

    shop = current_shop()
    name = request.form.get("name", "").strip().lower()
    file = request.files.get("file")

    try:
        module = import_third_party_plugin(name, file)
    except PluginValidationError as exc:
        audit(actions.PLUGIN_IMPORT, actor=current_user(), shop_id=shop.id,
              target_type="plugin", target_id=name, success=False, detail=str(exc))
        flash(f"Could not import plugin: {exc}", "error")
        return redirect(url_for("admin.plugins"))

    plugin = Plugin.query.filter_by(shop_id=shop.id, name=name).first()
    if plugin is None:
        plugin = Plugin(shop_id=shop.id, name=name)
        db.session.add(plugin)
    plugin.is_third_party = True
    plugin.enabled = False
    db.session.commit()

    display_name = getattr(module, "PLUGIN_NAME", name)
    audit(actions.PLUGIN_IMPORT, actor=current_user(), shop_id=shop.id,
          target_type="plugin", target_id=name, success=True, detail=f"display_name={display_name!r}")
    flash(f'Imported "{display_name}" - enable it below to show it on your storefront.', "success")
    return redirect(url_for("admin.plugins"))


@bp.route("/plugins/upload", methods=["GET", "POST"])
@admin_required
@limiter.limit("5 per minute")
def upload_plugin():
    from app.pluginmanager.loader import BUILTIN_PLUGIN_NAMES

    error = None
    shop = current_shop()

    if request.method == "POST":
        plugin_name = request.form.get("plugin_name", "").strip()
        file = request.files.get("plugin_file")

        if not plugin_name or not is_safe_plugin_name(plugin_name):
            error = "Plugin name must contain only letters, numbers, or underscores."
        elif plugin_name.lower() in BUILTIN_PLUGIN_NAMES:
            error = f'"{plugin_name}" is a built-in plugin and cannot be overwritten.'
        elif not file or file.filename == "":
            error = "No file selected."
        else:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()

            if ext not in ALLOWED_EXTENSIONS:
                error = "Only .py files are accepted."
            else:
                source_bytes = file.read()
                if len(source_bytes) > MAX_UPLOAD_SIZE:
                    error = "Plugin file is too large."
                else:
                    source_text = source_bytes.decode("utf-8", errors="replace")
                    is_valid, format_error = validate_plugin_format(source_text)
                    if not is_valid:
                        error = format_error
                    else:
                        plugin_folder = os.path.join(PLUGIN_DIR, plugin_name)
                        os.makedirs(plugin_folder, exist_ok=True)
                        with open(os.path.join(plugin_folder, "__init__.py"), "wb") as f:
                            f.write(source_bytes)

                        # Mark it as third-party in the model
                        plugin_row = Plugin.query.filter_by(shop_id=shop.id, name=plugin_name).first()
                        if not plugin_row:
                            plugin_row = Plugin(shop_id=shop.id, name=plugin_name)
                            db.session.add(plugin_row)
                        plugin_row.is_third_party = True
                        plugin_row.enabled = False
                        db.session.commit()

                        audit(actions.PLUGIN_IMPORT, actor=current_user(), shop_id=shop.id,
                              target_type="plugin", target_id=plugin_name, success=True,
                              detail="single-file upload")
                        flash("Plugin uploaded - enable it on the plugins page to show it on your storefront.", "success")
                        return redirect(url_for("admin.plugins"))

    return render_template("admin/upload_plugin.html", error=error)


SECURITY_PLUGIN_NAMES = ["temp_lockout", "new_device_alert", "ip_rate_limit"]


@bp.route("/security-settings", methods=["GET", "POST"])
@admin_required
@limiter.limit("10 per minute")
def security_settings():
    # separate from /admin/plugins. That route toggles UNTRUSTED,
    # uploadable plugins (app/plugins/, discovered dynamically). This
    # toggles TRUSTED, statically-imported security features.
    import importlib

    shop = current_shop()
    toggles = []
    for name in SECURITY_PLUGIN_NAMES:
        module = importlib.import_module(f"app.security_plugins.{name}")
        row = Plugin.query.filter_by(shop_id=shop.id, name=name).first()
        if not row:
            row = Plugin(shop_id=shop.id, name=name, enabled=True, is_third_party=False)
            db.session.add(row)
            db.session.commit()
        toggles.append({
            "name": name,
            "display_name": module.PLUGIN_NAME,
            "description": module.PLUGIN_DESCRIPTION,
            "enabled": row.enabled,
        })

    if request.method == "POST":
        selected = set(request.form.getlist("enabled_features"))
        for name in SECURITY_PLUGIN_NAMES:
            row = Plugin.query.filter_by(shop_id=shop.id, name=name).first()
            row.enabled = name in selected
        db.session.commit()
        audit(actions.PLUGIN_TOGGLE, actor=current_user(), shop_id=shop.id,
              target_type="security_feature", detail=f"enabled={sorted(selected)}")
        flash("Security settings updated.", "success")
        return redirect(url_for("admin.security_settings"))

    # Admin visibility into currently active temp_lockout cooldowns —
    # reads directly from the in-memory tracker, no separate storage.
    from app.security_plugins.temp_lockout import current_lockouts
    locked_accounts = []
    for entry in current_lockouts():
        locked_user = User.query.get(entry["user_id"])
        if locked_user:
            locked_accounts.append({
                "username": locked_user.username,
                "shop_id": locked_user.shop_id,
                "seconds_remaining": entry["seconds_remaining"],
                "strikes": entry["strikes"],
            })

    return render_template("admin/security_settings.html", toggles=toggles, locked_accounts=locked_accounts)
