import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    UPLOAD_EXTENSIONS = ['jpg', 'png', 'gif','txt']
    TESTING = True


class ProductionConfig:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = f"postgresql://{os.environ.get("DB_USERNAME")}:{os.environ.get("DB_PASSWORD")}@db:5432/{os.environ.get("DB_NAME")}"
    UPLOAD_EXTENSIONS = ['jpg', 'png', 'gif','txt']
    POSTS_PER_PAGE = 12