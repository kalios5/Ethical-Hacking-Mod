from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_

from app import db
from app.auth.routes import current_user, login_required
from app.Database.models import CartItem, Order, OrderItem, Plugin, Product, Shop
from app.main.loader import get_plugin
from app.storefront import bp


def current_shop():
    return Shop.query.order_by(Shop.id).first()


@bp.route("/")
def index():
    shop = current_shop()
    query = request.args.get("q", "").strip()
    products_query = Product.query.filter_by(shop_id=shop.id)
    if query:
        term = f"%{query}%"
        products_query = products_query.filter(or_(Product.name.ilike(term), Product.description.ilike(term)))
    products = products_query.order_by(Product.created_at.desc()).all()
    plugins = Plugin.query.filter_by(shop_id=shop.id, enabled=True).all()
    widgets = []
    for plugin in plugins:
        try:
            widgets.append(get_plugin(plugin.name).render_widget({"customer_name": current_user().username if current_user() else "Guest"}))
        except (ImportError, AttributeError):
            continue
    return render_template("storefront/index.html", shop=shop, products=products, query=query, widgets=widgets)


@bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=current_shop().id).first_or_404()
    return render_template("storefront/product.html", product=product)


@bp.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user().id).all()
    lines = [(item, db.session.get(Product, item.product_id)) for item in items]
    total_cents = sum(product.price_cents * item.quantity for item, product in lines)
    return render_template("storefront/cart.html", lines=lines, total_cents=total_cents)


@bp.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=current_shop().id).first_or_404()
    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except ValueError:
        quantity = 1
    item = CartItem.query.filter_by(user_id=current_user().id, product_id=product.id).first()
    new_quantity = (item.quantity if item else 0) + quantity
    if new_quantity > product.stock:
        flash("There is not enough stock for that quantity.", "error")
    else:
        if item:
            item.quantity = new_quantity
        else:
            db.session.add(CartItem(user_id=current_user().id, product_id=product.id, quantity=quantity))
        db.session.commit()
        flash(f"{product.name} added to your cart.", "success")
    return redirect(request.referrer or url_for("storefront.index"))


@bp.route("/cart/update", methods=["POST"])
@login_required
def update_cart():
    for key, value in request.form.items():
        if not key.startswith("quantity-"):
            continue
        item = db.session.get(CartItem, int(key.removeprefix("quantity-")))
        if item and item.user_id == current_user().id:
            item.quantity = max(0, int(value))
            if item.quantity == 0:
                db.session.delete(item)
    db.session.commit()
    flash("Cart updated.", "success")
    return redirect(url_for("storefront.cart"))


@bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_from_cart(item_id):
    item = db.session.get(CartItem, item_id)
    if item and item.user_id == current_user().id:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for("storefront.cart"))


@bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    user = current_user()
    items = CartItem.query.filter_by(user_id=user.id).all()
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("storefront.cart"))
    total_cents = 0
    order_items = []
    shop = current_shop()
    for item in items:
        product = Product.query.filter_by(id=item.product_id, shop_id=shop.id).with_for_update().first()
        if product is None or item.quantity > product.stock:
            db.session.rollback()
            flash("One of your items is no longer available in that quantity.", "error")
            return redirect(url_for("storefront.cart"))
        total_cents += item.quantity * product.price_cents
        product.stock -= item.quantity
        order_items.append((product, item))
    order = Order(user_id=user.id, shop_id=shop.id, total_cents=total_cents, status="paid")
    db.session.add(order)
    db.session.flush()
    for product, item in order_items:
        db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=item.quantity, unit_price_cents=product.price_cents))
        db.session.delete(item)
    db.session.commit()
    flash(f"Order #{order.id} placed successfully.", "success")
    return redirect(url_for("storefront.index"))