"""
db/  -  the database layer for the vulnerable e-commerce SaaS.

Usage from the app factory:

    from db import db, init_db
    from db.config import DBConfig

    app.config.from_object(DBConfig)
    init_db(app)          # binds SQLAlchemy + creates tables if missing

The single shared SQLAlchemy instance lives here so every module imports the
SAME object (avoids the "multiple SQLAlchemy()" bug the repo currently has,
where pluginmanager/models.py and app/__init__.py each make their own).
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_db(app):
    """Bind the db to the app and ensure tables exist.

    In Docker the tables are already created by the init SQL scripts, so
    create_all() is a harmless no-op there. It's mainly for local dev where
    someone points DATABASE_URL at a fresh sqlite file.
    """
    db.init_app(app)

    # Import models so SQLAlchemy registers them before create_all().
    from . import models  # noqa: F401

    with app.app_context():
        db.create_all()
