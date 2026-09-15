"""
logging_setup/app_logging.py  -  application logging.

Sets up python's logging so that:
  * everything goes to logs/app.log (rotating, so it can't fill the EC2 disk)
  * a copy goes to the console / docker logs
  * every HTTP request is logged with method, path, status, client IP

The logs/ folder is bind-mounted to the host in docker-compose, so the logs
survive container restarts and are available to the blue-team (and to the
Docker-Escape PoC, which reads the logs folder).
"""
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from flask import g, request

LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(app):
    """Attach handlers to the Flask app logger and install request hooks."""
    os.makedirs(LOG_DIR, exist_ok=True)

    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Rotating file: 5 files x 2 MB each.
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)

    # Configure the root logger so our modules AND werkzeug/sqlalchemy flow in.
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if configure_logging() is called twice.
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in root.handlers):
        root.addHandler(console)

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

    @app.errorhandler(Exception)
    def _log_exception(err):
        log.exception("Unhandled exception on %s %s", request.method, request.path)
        raise err
