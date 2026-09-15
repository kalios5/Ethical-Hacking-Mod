import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    UPLOAD_EXTENSIONS = ['jpg', 'png', 'gif','txt']
    TESTING = True
    ELASTICSEARCH_URL = f"http://{os.environ.get('ES_HOST')}:{os.environ.get('ES_PORT')}"
    POSTS_PER_PAGE = 12


class ProductionConfig:
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{os.environ.get('DB_USERNAME')}:{os.environ.get('DB_PASSWORD')}"
        f"@{os.environ.get('DB_IP')}:{os.environ.get('DB_PORT')}/{os.environ.get('DB_NAME')}"
    )
    UPLOAD_EXTENSIONS = ['jpg', 'png', 'gif','txt']
    ELASTICSEARCH_URL = f"http://{os.environ.get('ES_HOST')}:{os.environ.get('ES_PORT')}"
    POSTS_PER_PAGE = 12