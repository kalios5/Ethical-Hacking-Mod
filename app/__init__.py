import os

from flask import Flask
from flask.templating import Environment as FlaskEnvironment
from jinja2.sandbox import ImmutableSandboxedEnvironment, safe_range
from app.config import ProductionConfig, TestPostgresConfig
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel
from app.safe_config import SafeConfigProxy
#from flask_login import LoginManager


class SandboxedEnvironment(ImmutableSandboxedEnvironment, FlaskEnvironment):
    """ImmutableSandboxedEnvironment + Flask's app-aware Environment.

    Never constructed directly (see SandboxedFlask.create_jinja_environment
    below) - it exists only so the environment Flask already built can be
    re-classed onto something that is both. Flask's Environment.__init__
    takes `app` and calls jinja2.Environment.__init__ directly by name
    (not via super()), which would skip ImmutableSandboxedEnvironment's own
    __init__ (the part that sets up self.binop_table/self.unop_table, which
    its sandboxed operator checks rely on) if constructed the normal way -
    hence the re-class-after-the-fact approach instead.

    LAB CONFIG (kept on purpose - see Scripts/WebAttack/ployInject.py):
    the default sandbox rule blocks every attribute starting with "_",
    which also blocks SSTI payloads that only ever touch application
    objects (e.g. `user.__class__.query.session` to reach the ORM and
    create a row via `__setattr__`) - not just the os/subprocess gadgets
    this sandbox exists to stop. _ALLOWED_UNSAFE_ATTRS narrows that back
    open for exactly the two dunders that "stay within app functions"
    payload needs, while everything else underscore-prefixed - in
    particular __globals__, __subclasses__, __mro__, __bases__, __base__,
    __init__, __builtins__ - stays blocked by the default rule below. Those
    are the specific attributes every known os/subprocess gadget chain
    needs to walk from an arbitrary object back to a module's globals or
    the class hierarchy. This is a curated allowlist, not a proof: it
    closes the gadget shape demonstrated in this lab and the well-known
    dangerous dunders, not a formal guarantee against every possible
    Python object-graph trick - do not treat it as equivalent to the full
    default-deny sandbox.
    """

    _ALLOWED_UNSAFE_ATTRS = {"__class__", "__setattr__"}

    def is_safe_attribute(self, obj, attr, value):
        if attr in self._ALLOWED_UNSAFE_ATTRS:
            return True
        return super().is_safe_attribute(obj, attr, value)


class SandboxedFlask(Flask):
    def create_jinja_environment(self):
        # Build the environment the normal Flask way first (this is what
        # wires up the template loader/autoescape from `self`), then turn
        # it into a sandboxed one. Every template expression is then
        # evaluated in Jinja's sandbox: attribute access to anything
        # starting with "_" (__class__, __globals__, __subclasses__,
        # __builtins__ ...) is refused, so an SSTI cannot walk the object
        # graph to os/subprocess. See app/safe_config.py for the separate
        # secret-disclosure allowlist.
        env = super().create_jinja_environment()
        env.__class__ = SandboxedEnvironment
        env.globals["range"] = safe_range
        env.binop_table = env.default_binop_table.copy()
        env.unop_table = env.default_unop_table.copy()
        return env


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
    app = SandboxedFlask(__name__)
    app.config.from_object(config_class)
    app.jinja_env.globals.pop('config', None)
    app.jinja_env.globals['config'] = SafeConfigProxy(app.config)

    # Fail closed on a missing/placeholder SECRET_KEY in a real deployment.
    # SECRET_KEY signs session cookies AND CSRF tokens, so a fallback like
    # "TEST" in production would let anyone forge an admin session. TESTING
    # (local/dev SQLite) is exempt so `python main.py` still runs.
    if not app.config.get("TESTING"):
        secret = app.config.get("SECRET_KEY")
        if not secret or secret == "TEST":
            raise RuntimeError(
                "SECRET_KEY must be set to a strong, secret value in production "
                "(set the SECRET_KEY environment variable)."
            )

    from app.logging.app_logging import configure_logging
    configure_logging(app)

    # Trust the reverse proxy's X-Forwarded-Proto/-For in production, so
    # request.is_secure is True behind a TLS-terminating proxy. Without this,
    # HSTS (below) and the Secure session cookie would never activate in prod
    # because Flask would see every proxied request as plain http. Scoped to
    # non-testing so the dev/demo server is unchanged.
    if not app.config.get("TESTING"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # General browser-side security headers (attack-safe; see module docstring).
    from app.security_headers import init_security_headers
    init_security_headers(app)

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
    from app.errors.routes import register_error_handlers

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(storefront_bp)
    register_error_handlers(app)  # production only (DEBUG=False) - see that module's docstring

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

