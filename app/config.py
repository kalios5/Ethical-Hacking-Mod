import os

from dotenv import load_dotenv

# Loads a local .env (or the one docker-compose bind-mounts to /.env in the
# container) into os.environ, so DB_USERNAME/DB_PASSWORD/DB_NAME/SECRET_KEY
# below are actually populated outside of docker-compose's own interpolation.
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

# Caps the whole request body Werkzeug will read (e.g. the plugin-import zip
# upload in app/admin/routes.py) - complements the in-app zip entry/size
# checks in app/pluginmanager/loader.py, which only run after a request body
# has already been read.
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

# Profile pictures live outside app/static so they are only reachable through
# the auth.avatar route. AVATAR_MAX_BYTES is the tighter per-image cap.
UPLOADED_AVATARS_DEST = os.environ.get("AVATAR_DIR") or os.path.join(os.path.dirname(basedir), "uploads", "avatars")
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = 256


class TestPostgresConfig:
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    TESTING = True
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    UPLOADED_AVATARS_DEST = UPLOADED_AVATARS_DEST
    AVATAR_MAX_BYTES = AVATAR_MAX_BYTES
    AVATAR_SIZE = AVATAR_SIZE


class ProductionConfig:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"
    DB_USERNAME = os.environ.get("DB_USERNAME")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")
    DB_NAME = os.environ.get("DB_NAME")
    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@db:5432/{DB_NAME}"
    POSTS_PER_PAGE = 12
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    UPLOADED_AVATARS_DEST = UPLOADED_AVATARS_DEST
    AVATAR_MAX_BYTES = AVATAR_MAX_BYTES
    AVATAR_SIZE = AVATAR_SIZE
