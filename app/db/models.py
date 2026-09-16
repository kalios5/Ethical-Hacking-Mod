from flask_sqlalchemy import SQLAlchemy
from app import db
from datetime import datetime


# BIGINT that still auto-increments on sqlite (local dev). On MySQL it stays a
# real BIGINT AUTO_INCREMENT; sqlite needs plain INTEGER for rowid autoincrement.
BigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")


class PluginToggle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<PluginToggle {self.name} enabled={self.enabled}>"

class Shop(db.Model):
    __tablename__ = "shops"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    domain = db.Column(db.String(190), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship("User", backref="shop", cascade="all, delete-orphan")
    products = db.relationship("Product", backref="shop", cascade="all, delete-orphan")
    plugins = db.relationship("Plugin", backref="shop", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Shop {self.id} {self.domain}>"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(190), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    hash_mode = db.Column(db.String(16), nullable=False, default="weak")
    role = db.Column(
        db.Enum("guest", "customer", "admin", "superadmin"),
        nullable=False,
        default="customer",
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    twofa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    twofa_secret = db.Column(db.String(64))
    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("shop_id", "username", name="uq_user_per_shop"),
    )

    # --- convenience helpers (hashing lives in db/security.py) --------------
    def set_password(self, plaintext, mode=None):
        from .security import hash_password
        mode = mode or self.hash_mode
        self.password_hash = hash_password(plaintext, mode)
        self.hash_mode = mode

    def check_password(self, plaintext):
        from .security import verify_password
        return verify_password(plaintext, self.password_hash, self.hash_mode)

    def __repr__(self):
        return f"<User {self.id} {self.username} ({self.role})>"


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    price_cents = db.Column(db.Integer, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def price(self):
        return self.price_cents / 100.0


class CartItem(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
    )


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(
        db.Enum("pending", "paid", "shipped", "cancelled"),
        nullable=False,
        default="pending",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price_cents = db.Column(db.Integer, nullable=False, default=0)


class Plugin(db.Model):
    __tablename__ = "plugins"
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    is_third_party = db.Column(db.Boolean, nullable=False, default=False)
    config_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("shop_id", "name", name="uq_plugin_per_shop"),
    )


class AuditLog(db.Model):
    """Application-written security events. Also written by logging_setup."""
    __tablename__ = "audit_log"
    id = db.Column(BigIntPK, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    actor_user_id = db.Column(db.Integer, index=True)
    actor_ip = db.Column(db.String(45))
    shop_id = db.Column(db.Integer)
    action = db.Column(db.String(80), nullable=False, index=True)
    target_type = db.Column(db.String(40))
    target_id = db.Column(db.String(64))
    success = db.Column(db.Boolean, nullable=False, default=True)
    detail = db.Column(db.Text)


class DbChangeLog(db.Model):
    """Read-only view of the trigger-written DB change log."""
    __tablename__ = "db_change_log"
    id = db.Column(BigIntPK, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    db_user = db.Column(db.String(128), nullable=False)
    table_name = db.Column(db.String(64), nullable=False)
    op = db.Column(db.String(10), nullable=False)
    row_pk = db.Column(db.String(64))
    detail = db.Column(db.Text)
