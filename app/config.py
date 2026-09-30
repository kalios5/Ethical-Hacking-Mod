import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Loads a local .env (or the one docker-compose bind-mounts to /.env in the
# container) into os.environ, so DB_USERNAME/DB_PASSWORD/DB_NAME/SECRET_KEY
# below are actually populated outside of docker-compose's own interpolation.
load_dotenv()


class BaseConfig:
    """Settings shared by every environment. Resolved here, as class
    attributes on a shared base, rather than as module-level variables
    computed before the classes and then copied into each one."""

    BASEDIR = Path(__file__).resolve().parent

    SECRET_KEY = os.environ.get("SECRET_KEY") or "TEST"

    # Caps the whole request body Werkzeug will read (e.g. the plugin-import
    # zip upload in app/admin/routes.py) - complements the in-app zip
    # entry/size checks in app/pluginmanager/loader.py, which only run after
    # a request body has already been read.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

    # Profile pictures live outside app/static so they are only reachable
    # through the auth.avatar route. AVATAR_MAX_BYTES is the tighter
    # per-image cap.
    UPLOADED_AVATARS_DEST = os.environ.get("AVATAR_DIR") or (BASEDIR.parent / "uploads" / "avatars")
    AVATAR_MAX_BYTES = 2 * 1024 * 1024
    AVATAR_SIZE = 256

    # Normally Flask only sets this True when DEBUG is True, so under
    # ProductionConfig (DEBUG=False) Jinja compiles each template once and
    # never rechecks it on disk - a template overwritten after that first
    # render (e.g. via the avatar-upload path traversal, see app/uploads.py)
    # would sit there unused until the process restarts. Forcing it True
    # here means a template landed on disk takes effect on the very next
    # request that renders it, in every environment.
    TEMPLATES_AUTO_RELOAD = True

    # --- session cookie hardening (general, attack-safe) ------------------
    # HttpOnly: JS can't read the session cookie (limits XSS session theft).
    # SameSite=Lax: cookie not sent on cross-site POSTs (CSRF depth).
    # Keep idle sessions brief and impose a hard absolute cap so a stolen
    # session stays useful for only a short window even if the user never logs
    # out.
    # SESSION_COOKIE_SECURE is set per-environment below (needs HTTPS in prod,
    # off for the plain-http dev/demo server).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=15)
    SESSION_IDLE_TIMEOUT_SECONDS = 15 * 60
    SESSION_ABSOLUTE_TIMEOUT_SECONDS = 12 * 60 * 60


class TestPostgresConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BaseConfig.BASEDIR / 'app.db'}"
    TESTING = True
    SESSION_COOKIE_SECURE = False   # dev/demo runs over plain http
    CSP_REPORT_ONLY = True          # report violations, block nothing during demo


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True    # requires HTTPS (TLS terminator / reverse proxy)
    CSP_REPORT_ONLY = False         # enforce the policy in production
    DB_USERNAME = os.environ.get("DB_USERNAME")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")
    DB_NAME = os.environ.get("DB_NAME")
    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@db:5432/{DB_NAME}"
    POSTS_PER_PAGE = 12
