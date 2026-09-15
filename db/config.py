"""
db/config.py  -  Database configuration for the Flask app.

Reads connection details from environment variables (populated from the .env
file in deployment/). Builds a MySQL SQLAlchemy URI using the pure-python
PyMySQL driver, so no system libraries are needed in the app container.
"""
import os


def _mysql_uri() -> str:
    user = os.environ.get("DB_USERNAME", "eh_app")
    pwd = os.environ.get("DB_PASSWORD", "app_change_me")
    host = os.environ.get("DB_HOST", "db")          # docker service name
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "eh_shop")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4"


class DBConfig:
    """Mix into the Flask app config (app.config.from_object(DBConfig))."""

    # Allow a full override (handy for local sqlite dev), else build MySQL URI.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or _mysql_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Reconnect politely - MySQL drops idle connections; pre_ping avoids the
    # "MySQL server has gone away" error after the app sits idle.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Which password hashing scheme new users get. Read by db/security.py.
    #   secure | weak | md5   (see .env.example / DB_SETUP_GUIDE.md)
    PASSWORD_HASH_MODE = os.environ.get("PASSWORD_HASH_MODE", "weak")
