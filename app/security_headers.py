"""
app/security_headers.py  -  app-wide HTTP security hardening.

Adds security response headers (CSP, nosniff, frame-deny, referrer/permissions
policy, HSTS) on every response, and makes the session cookie time-bounded.

WHY THIS IS APP-WIDE, NOT A PER-SHOP SECURITY PLUGIN
----------------------------------------------------
These are transport/browser-level protections a tenant must not be able to
switch off for its own storefront, so they live here as always-on middleware
rather than in app/security_plugins/ (which is for per-shop, admin-toggled
policy features).

RELATIONSHIP TO THE INTENDED LAB VULNERABILITIES
------------------------------------------------
None of this touches them. The plugin-upload RCE runs server-side on import,
so a browser-enforced CSP cannot affect it. The crack-the-hash / DB-console
paths are GET reads of data, which CSP does not block. The storefront widget
CSP is pure defence-in-depth behind the existing bleach sanitisation.
"""
from flask import request, session

# The app's own pages (storefront, hand-written /admin, auth) contain NO inline
# <script>, so script-src can be the strict 'self'. style-src keeps
# 'unsafe-inline' for the couple of inline style="" attributes (e.g. the 2FA QR
# sizing); img-src allows data: because the 2FA QR is a data: URI.
BASE_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

# The Flask-Admin DB console at /admin/db ships inline scripts/styles with its
# bundled UI, so a strict script-src 'self' would break it. Give just that
# subtree 'unsafe-inline' for scripts so the (groupmate-owned) console works;
# everything else stays locked down.
ADMIN_CONSOLE_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


def init_security_headers(app):
    # CSP_REPORT_ONLY=True sends the policy as Content-Security-Policy-Report-Only
    # (browser reports violations but does NOT block), so you can watch the
    # console during a demo before enforcing. Flip to False to enforce.
    report_only = app.config.get("CSP_REPORT_ONLY", False)
    csp_header = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"

    @app.before_request
    def _bound_session_lifetime():
        # Marks the session permanent so Flask actually applies
        # PERMANENT_SESSION_LIFETIME (an absolute/rolling expiry). Without this
        # the cookie is an unbounded browser-session cookie.
        session.permanent = True

    @app.after_request
    def _set_security_headers(resp):
        policy = ADMIN_CONSOLE_CSP if request.path.startswith("/admin/db") else BASE_CSP
        resp.headers.setdefault(csp_header, policy)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # HSTS only when the request actually arrived over HTTPS (behind the
        # nginx TLS terminator), so local http dev is unaffected.
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            resp.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resp
