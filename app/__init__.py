import os

from flask import Flask
from app.config import ProductionConfig, TestPostgresConfig
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel

#from flask_login import LoginManager
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
# storage_uri="memory://" silences the Flask-Limiter "in-memory storage" startup
# warning by making the in-memory backend explicit (fine for this single-process
# lab deployment; swap for redis:// if it ever runs multi-worker).
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
# main imported flask_babel.Babel and called babel.init_app(app) below but never
# instantiated the extension, so the app raised NameError on boot. Instantiate it
# here so the (groupmate-added) babel integration actually works.
babel = Babel()
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
    babel.init_app(app)
    from app.uploads import init_uploads
    init_uploads(app)

    from app.Database import models  # noqa: F401  (registers models with SQLAlchemy)
    from app.admin import bp as admin_bp
    from app.auth import bp as auth_bp
    from app.storefront import bp as storefront_bp
    from app.errors import bp as errors_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(storefront_bp)
    app.register_blueprint(errors_bp)  # no routes, only app-wide error handlers

    # admin console for database
    from app.admin.dbconsole import init_db_console
    init_db_console(app)

    # CSRF protection is enabled site-wide (csrf.init_app above). Every POST
    # form across the app carries a {{ csrf_token() }} hidden field, so no
    # route is exempted. This includes the Flask-Admin DB console at /admin/db:
    # Flask-Admin 2.2.0 auto-injects a csrf_token into its create/edit/delete
    # forms when CSRFProtect is active, so the console keeps working. It does
    # NOT touch the plugin-upload RCE path (that runs server-side on import,
    # and the browser upload form submits a valid token like any other form).

    @app.context_processor
    def inject_current_user():
        from app.auth.routes import current_user
        return {"current_user": current_user()}

    if not os.environ.get("SKIP_AUTO_INIT"):  # TEMP: unset for `flask db migrate`
        with app.app_context():
            db.create_all()
            _add_missing_columns()
            _seed_development_data()
            from app.Database.audit_events import prune_old_audit_rows
            prune_old_audit_rows(days=7)

    return app


def _add_missing_columns():
    """db.create_all() never alters an existing table, and migrations/versions
    is empty, so columns added after first deploy are added here (idempotent)."""
    from sqlalchemy import inspect, text

    if "avatar_filename" not in {c["name"] for c in inspect(db.engine).get_columns("users")}:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_filename VARCHAR(255)"))


def _seed_development_data():
    """Ports deployment/db/init/02_seed.sql's dataset into the ORM (that raw
    SQL was MySQL-dialect and never actually ran against this project's
    Postgres service - see the DB init cleanup notes). hash_mode='weak'
    (unsalted SHA-256) is used on purpose here, matching the original seed
    data, to keep the crack-the-hash lab intact."""
    from app.Database.models import Order, OrderItem, Plugin, Product, User

    if User.query.first() is not None:
        return

    def _user(username, email, password, role):
        user = User(username=username, email=email, role=role, hash_mode="weak")
        user.set_password(password, "weak")
        return user

    users = [
        _user("superadmin", "root@saas.local", "SuperSecret@2026", "superadmin"),
        _user("admin", "admin@petalandstem.local", "admin", "admin"),
        _user("alice", "alice@example.com", "password1", "customer"),
        _user("bob", "bob@example.com", "letmein", "customer"),
    ]
    db.session.add_all(users)

    products = [
        Product(name="Red Rose Bouquet", description="A dozen long-stem red roses.", price_cents=2999, stock=50),
        Product(name="White Rose Single", description="A single white rose.", price_cents=399, stock=200),
        Product(name="Rose Gift Box", description="Roses in a keepsake box.", price_cents=4599, stock=25),
        Product(name="Wild Poppy Bunch", description="Freshly cut wild poppies.", price_cents=1899, stock=40),
        Product(name="Poppy Wreath", description="A seasonal floral wreath.", price_cents=3599, stock=15),
    ]
    db.session.add_all(products)

    plugins = [
        Plugin(name="welcome_message", enabled=True),
        Plugin(name="discount_banner", enabled=True),
        Plugin(name="newsletter_signup", enabled=False),
    ]
    db.session.add_all(plugins)
    db.session.flush()

    alice = next(u for u in users if u.username == "alice")
    red_rose = next(p for p in products if p.name == "Red Rose Bouquet")
    white_rose = next(p for p in products if p.name == "White Rose Single")
    order = Order(user_id=alice.id, total_cents=3398, status="paid")
    db.session.add(order)
    db.session.flush()
    db.session.add_all([
        OrderItem(order_id=order.id, product_id=red_rose.id, quantity=1, unit_price_cents=2999),
        OrderItem(order_id=order.id, product_id=white_rose.id, quantity=1, unit_price_cents=399),
    ])
    db.session.commit()

