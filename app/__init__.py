import os

from flask import Flask
from app.config import *
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from extensions import limiter
#from flask_login import LoginManager
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
#login = LoginManager()

# APP_CONFIG=production (set by docker-compose.yml) -> ProductionConfig/Postgres.
# Anything else / unset (local `python main.py`) -> TestPostgresConfig/SQLite.
CONFIG_BY_NAME = {"production": ProductionConfig, "test": TestPostgresConfig}


def create_app(config_class=None):
    if config_class is None:
        config_class = CONFIG_BY_NAME.get(os.environ.get("APP_CONFIG", "test"), TestPostgresConfig)
    app = Flask(__name__)
    app.config.from_object(config_class)

    from app.logging.app_logging import configure_logging
    configure_logging(app)

    db.init_app(app)
    migrate.init_app(app,db)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.Database import models
    # admin must import before pluginmanager: pluginmanager.routes imports
    # admin_required from app.admin.routes.
    from app.admin import bp as admin_bp
    from app.pluginmanager import bp as pluginmanager_bp
    from app.auth import bp as auth_bp
    from app.storefront import bp as storefront_bp
    from app.errors import bp as errors_bp

    app.register_blueprint(pluginmanager_bp, url_prefix="/pluginmanager")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(storefront_bp)
    app.register_blueprint(errors_bp)  # no routes, only app-wide error handlers

    # CSRF is scoped to ONLY the plugin/plugin-uploader routes rather than
    # the whole site. Everything else - login, register, account, cart,
    # checkout, product management - is explicitly exempted so this
    # doesn't touch unrelated site functionality. admin.plugins,
    # admin.import_plugin, admin.upload_plugin, admin.security_settings,
    # and the legacy pluginmanager.plugin_list stay protected.
    csrf.exempt(auth_bp)
    csrf.exempt(storefront_bp)
    csrf.exempt(app.view_functions["admin.products"])
    csrf.exempt(app.view_functions["admin.edit_product"])
    csrf.exempt(app.view_functions["admin.delete_product"])

    @app.context_processor
    def inject_current_user():
        from app.auth.routes import current_user
        return {"current_user": current_user()}

    if not os.environ.get("SKIP_AUTO_INIT"):  # TEMP: unset for `flask db migrate`
        with app.app_context():
            db.create_all()
            _seed_development_data()
            from app.Database.audit_events import prune_old_audit_rows
            prune_old_audit_rows(days=7)

    return app


def _seed_development_data():
    """Ports deployment/db/init/02_seed.sql's dataset into the ORM (that raw
    SQL was MySQL-dialect and never actually ran against this project's
    Postgres service - see the DB init cleanup notes). hash_mode='weak'
    (unsalted SHA-256) is used on purpose here, matching the original seed
    data, to keep the crack-the-hash lab intact."""
    from app.Database.models import Order, OrderItem, Plugin, Product, Shop, User

    if Shop.query.order_by(Shop.id).first() is not None:
        return

    roses = Shop(name="Roses 4 Sale", domain="roses-4-sale.com")
    poppies = Shop(name="Poppies 2 Buy", domain="poppies-2-buy.com")
    db.session.add_all([roses, poppies])
    db.session.flush()

    def _user(shop, username, email, password, role):
        user = User(shop_id=shop.id, username=username, email=email, role=role, hash_mode="weak")
        user.set_password(password, "weak")
        return user

    users = [
        _user(roses, "superadmin", "root@saas.local", "SuperSecret@2026", "superadmin"),
        _user(roses, "admin", "admin@roses-4-sale.com", "admin", "admin"),
        _user(poppies, "admin", "admin@poppies-2-buy.com", "Petal!2026", "admin"),
        _user(roses, "alice", "alice@example.com", "password1", "customer"),
        _user(roses, "bob", "bob@example.com", "letmein", "customer"),
        _user(poppies, "charlie", "charlie@example.com", "sunshine", "customer"),
    ]
    db.session.add_all(users)

    products = [
        Product(shop_id=roses.id, name="Red Rose Bouquet", description="A dozen long-stem red roses.", price_cents=2999, stock=50),
        Product(shop_id=roses.id, name="White Rose Single", description="A single white rose.", price_cents=399, stock=200),
        Product(shop_id=roses.id, name="Rose Gift Box", description="Roses in a keepsake box.", price_cents=4599, stock=25),
        Product(shop_id=poppies.id, name="Poppy Seed Packet", description="Grow your own poppies.", price_cents=299, stock=500),
        Product(shop_id=poppies.id, name="Wild Poppy Bunch", description="Freshly cut wild poppies.", price_cents=1899, stock=40),
        Product(shop_id=poppies.id, name="Poppy Wreath", description="Remembrance wreath.", price_cents=3599, stock=15),
    ]
    db.session.add_all(products)

    plugins = [
        Plugin(shop_id=roses.id, name="welcome_message", enabled=True),
        Plugin(shop_id=roses.id, name="discount_banner", enabled=True),
        Plugin(shop_id=roses.id, name="newsletter_signup", enabled=False),
        Plugin(shop_id=poppies.id, name="welcome_message", enabled=True),
        Plugin(shop_id=poppies.id, name="newsletter_signup", enabled=True),
    ]
    db.session.add_all(plugins)
    db.session.flush()

    alice = next(u for u in users if u.username == "alice")
    red_rose = next(p for p in products if p.name == "Red Rose Bouquet")
    white_rose = next(p for p in products if p.name == "White Rose Single")
    order = Order(user_id=alice.id, shop_id=roses.id, total_cents=3398, status="paid")
    db.session.add(order)
    db.session.flush()
    db.session.add_all([
        OrderItem(order_id=order.id, product_id=red_rose.id, quantity=1, unit_price_cents=2999),
        OrderItem(order_id=order.id, product_id=white_rose.id, quantity=1, unit_price_cents=399),
    ])
    db.session.commit()

