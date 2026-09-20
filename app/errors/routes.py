"""
app/errors/routes.py  -  one error page for every error.

Two handlers, registered app-wide (via @bp.app_errorhandler, not
@bp.errorhandler - these fire regardless of which blueprint raised the
error):

  * HTTPException - covers every "expected" HTTP error (400/401/403/404/405/
    429/...), including abort(403) in app/admin/routes.py's admin_required
    and the first_or_404() calls throughout the storefront/admin routes.
  * Exception - anything else, i.e. a genuine unhandled bug, which would
    otherwise become a bare 500. This handler *returns* the rendered page
    instead of re-raising, which is what makes it win over Werkzeug's
    interactive debugger even when DEBUG=True (the local/dev config) - by
    design, per the "one error page for any error" ask. The full traceback
    is still logged to logs/app.log either way, so nothing is lost, it's
    just not shown in-browser.

(This supersedes app/logging/app_logging.py's old @app.errorhandler(Exception),
which only logged and re-raised - registering a second handler for the same
Exception class would just silently replace it, so that one was removed.)
"""
import logging

from flask import render_template
from werkzeug.exceptions import HTTPException

from app.errors import bp

_log = logging.getLogger("request")


@bp.app_errorhandler(HTTPException)
def handle_http_exception(e):
    return render_template(
        "errors/error.html", code=e.code or 500, title=e.name, message=e.description,
    ), (e.code or 500)


@bp.app_errorhandler(Exception)
def handle_unexpected_exception(e):
    _log.exception("Unhandled exception")
    return render_template(
        "errors/error.html", code=500, title="Internal Server Error",
        message="Something went wrong on our end. It's been logged - please try again.",
    ), 500
