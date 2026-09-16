import os

basedir = os.path.abspath(os.path.dirname(__file__))

class TestPostgresConfig:
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    TESTING = True


class ProductionConfig:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = f"postgresql://{os.environ.get("DB_USERNAME")}:{os.environ.get("DB_PASSWORD")}@db:5432/{os.environ.get("DB_NAME")}"
    POSTS_PER_PAGE = 12