"""
logging_setup/  -  application + DB audit logging for the vulnerable SaaS.

Two halves:
  app_logging.py  -> configures python logging to logs/app.log (+ console) and
                     logs every HTTP request.
  db_audit.py     -> audit() helper that records security events into the
                     audit_log table AND the app log.

Wire both up in the app factory:

    from logging_setup.app_logging import configure_logging
    from logging_setup.db_audit import audit

    configure_logging(app)      # after app is created
    ...
    audit("LOGIN_SUCCESS", actor=user, ip=request.remote_addr)
"""
from .app_logging import configure_logging
from .db_audit import audit

__all__ = ["configure_logging", "audit"]
