"""
app/errors/routes.py  -  one error page for every error, PRODUCTION ONLY.

register_error_handlers(app) wires two handlers app-wide:

  * HTTPException - covers every "expected" HTTP error (400/401/403/404/405/
    429/...), including abort(403) in app/admin/routes.py's admin_required
    and the first_or_404() calls throughout the storefront/admin routes.
  * Exception - anything else, i.e. a genuine unhandled bug, which would
    otherwise become a bare 500. This handler *returns* the rendered page
    instead of re-raising, which is what makes it win over Werkzeug's
    interactive debugger.

Both are registered ONLY when app.debug is False - i.e. only under
ProductionConfig (see app/config.py; TestPostgresConfig sets DEBUG=True).
Under the local/test config, register_error_handlers() is a no-op, so
Werkzeug's own interactive debugger (for real bugs) and default error pages
(for HTTPExceptions) are used instead - far more useful during development
than the styled "something went wrong" page. In production the full
traceback is still logged to logs/app.log either way, so nothing is lost,
it's just not shown in-browser.

(This supersedes app/logging/app_logging.py's old @app.errorhandler(Exception),
which only logged and re-raised - registering a second handler for the same
Exception class would just silently replace it, so that one was removed.)
"""
import logging

from flask import render_template
from werkzeug.exceptions import HTTPException

_log = logging.getLogger("request")


def _handle_http_exception(e):
    return render_template(
        "errors/error.html", code=e.code or 500, title=e.name, message=e.description,
    ), (e.code or 500)


def _handle_unexpected_exception(e):
    _log.exception("Unhandled exception")
    return render_template(
        "errors/error.html", code=500, title="Internal Server Error",
        message="Something went wrong on our end. It's been logged - please try again.",
    ), 500


def register_error_handlers(app):
    """Wire the custom error pages - production only (see module docstring)."""
    if app.debug:
        return
    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected_exception)
