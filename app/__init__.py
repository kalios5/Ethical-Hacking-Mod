from flask import Flask
from app.config import *
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
#from flask_login import LoginManager
db = SQLAlchemy()
migrate = Migrate()
#login = LoginManager()

def create_app(config_class=TestPostgresConfig):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app,db)
    #login.init_app(app)

    #login.login_view = 'main.login'

    from app.Database import models
    from app.main import bp as main_bp
    from app.auth import bp as auth_bp
    from app.storefront import bp as storefront_bp
    from app.admin import bp as admin_bp

    app.register_blueprint(main_bp, url_prefix="/legacy")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(storefront_bp)

    @app.context_processor
    def inject_current_user():
        from app.auth.routes import current_user
        return {"current_user": current_user()}

    with app.app_context():
        db.create_all()
        _seed_development_data()
    
    return app


def _seed_development_data():
    from app.Database.models import Product, Shop, User

    shop = Shop.query.order_by(Shop.id).first()
    if shop is not None:
        return

    shop = Shop(name="Petal & Stem", domain="localhost")
    db.session.add(shop)
    db.session.flush()

    products = [
        Product(shop_id=shop.id, name="Red Rose Bouquet", description="A dozen long-stem red roses.", price_cents=2999, stock=50),
        Product(shop_id=shop.id, name="White Rose Single", description="A single white rose for a small gesture.", price_cents=399, stock=200),
        Product(shop_id=shop.id, name="Rose Gift Box", description="Fresh roses presented in a keepsake box.", price_cents=4599, stock=25),
    ]
    db.session.add_all(products)

    admin = User(shop_id=shop.id, username="admin", email="admin@localhost", role="admin", hash_mode="secure")
    admin.set_password("Admin!2026", "secure")
    customer = User(shop_id=shop.id, username="alice", email="alice@localhost", role="customer", hash_mode="secure")
    customer.set_password("Alice!2026", "secure")
    db.session.add_all([admin, customer])
    db.session.commit()

