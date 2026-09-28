"""
logging_setup/app_logging.py  -  application logging.

Sets up python's logging so that:
  * everything goes to a single logs/app.log file (no rotation, no console copy)
  * every HTTP request is logged with method, path, status, client IP

The logs/ folder is bind-mounted to the host in docker-compose, so the logs
survive container restarts and are available to the blue-team.
"""
import logging
import os
import time
from pathlib import Path

from flask import g, request

LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "app.log"

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(app):
    """Attach a single file handler to the root logger and install hooks."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Plain file handler: everything is appended to the one logs/app.log file.
    # No rotation (single file only) and no console/StreamHandler copy.
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Configure the root logger so our modules AND werkzeug/sqlalchemy flow in.
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if configure_logging() is called twice.
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        root.addHandler(file_handler)

    app.logger.setLevel(level)
    app.logger.info("Logging initialised -> %s (level=%s)", LOG_FILE, logging.getLevelName(level))

    _install_request_logging(app)


def _install_request_logging(app):
    log = logging.getLogger("request")

    @app.before_request
    def _start_timer():
        g._start = time.time()

    @app.after_request
    def _log_request(response):
        try:
            duration_ms = (time.time() - getattr(g, "_start", time.time())) * 1000
            ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            log.info(
                '%s %s %s -> %s (%.0fms) ua="%s"',
                ip,
                request.method,
                request.full_path.rstrip("?"),
                response.status_code,
                duration_ms,
                request.headers.get("User-Agent", "-"),
            )
        except Exception:  # never let logging break a response
            log.exception("request logging failed")
        return response

    # Unhandled-exception logging + the actual error response live in
    # app/errors/routes.py (registered as its own blueprint in
    # app/__init__.py::create_app()), which renders a page instead of
    # re-raising - a second @app.errorhandler(Exception) here would just be
    # silently overridden by that one anyway.
