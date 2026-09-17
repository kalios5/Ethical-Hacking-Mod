from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for

from app import db
from app.admin import bp
from app.auth.routes import current_user, login_required
from app.Database.models import Order, Plugin, Product, Shop, User
from app.main.loader import discover_plugins


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
        flash("Plugin settings updated.", "success")
        return redirect(url_for("admin.plugins"))

    enabled = {plugin.name for plugin in Plugin.query.filter_by(shop_id=shop.id, enabled=True).all()}
    plugin_data = [{"name": name, "display_name": getattr(module, "PLUGIN_NAME", name), "description": getattr(module, "PLUGIN_DESCRIPTION", ""), "enabled": name in enabled} for name, module in discover_plugins()]
    return render_template("admin/plugins.html", plugins=plugin_data)