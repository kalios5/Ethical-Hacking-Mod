"""
db/seed.py  -  Python re-seed helper.

In Docker the SQL init scripts already seed the data. This helper is for:
  * local dev against a fresh sqlite DB (DATABASE_URL=sqlite:///dev.db)
  * resetting demo data during development

Run standalone:
    python -m db.seed            # needs the app importable, see __main__ below
"""
from .import db
from .models import Shop, User, Product, Plugin


def seed(app):
    """Insert starter data if the users table is empty."""
    with app.app_context():
        if User.query.first():
            print("[seed] users already present - skipping")
            return

        roses = Shop(name="Roses 4 Sale", domain="roses-4-sale.com")
        poppies = Shop(name="Poppies 2 Buy", domain="poppies-2-buy.com")
        db.session.add_all([roses, poppies])
        db.session.flush()  # assign ids

        def make_user(shop, username, email, pw, role, mode="weak"):
            u = User(shop_id=shop.id, username=username, email=email,
                     role=role, hash_mode=mode)
            u.set_password(pw, mode)
            db.session.add(u)
            return u

        make_user(roses, "superadmin", "root@saas.local", "SuperSecret@2026", "superadmin")
        make_user(roses, "admin", "admin@roses-4-sale.com", "Admin@123", "admin")
        make_user(poppies, "admin", "admin@poppies-2-buy.com", "Petal!2026", "admin")
        make_user(roses, "alice", "alice@example.com", "password1", "customer")
        make_user(roses, "bob", "bob@example.com", "letmein", "customer")
        make_user(poppies, "charlie", "charlie@example.com", "sunshine", "customer")

        db.session.add_all([
            Product(shop_id=roses.id, name="Red Rose Bouquet", price_cents=2999, stock=50),
            Product(shop_id=roses.id, name="White Rose Single", price_cents=399, stock=200),
            Product(shop_id=poppies.id, name="Poppy Seed Packet", price_cents=299, stock=500),
            Plugin(shop_id=roses.id, name="welcome_message", enabled=True),
            Plugin(shop_id=roses.id, name="discount_banner", enabled=True),
            Plugin(shop_id=poppies.id, name="newsletter_signup", enabled=True),
        ])
        db.session.commit()
        print("[seed] inserted starter data")


if __name__ == "__main__":
    # Minimal standalone runner.
    from flask import Flask
    from .config import DBConfig
    from . import init_db

    app = Flask(__name__)
    app.config.from_object(DBConfig)
    init_db(app)
    seed(app)
