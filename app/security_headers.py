"""Security response headers (general, attack-safe hardening).

Adds a set of standard browser-side security headers to every response via an
after_request hook. None of these affect either intended lab vulnerability:
  - the plugin-upload RCE is server-side (executes on import), and
  - the avatar->SSTI privesc is entirely server-side (file write + Jinja
    render on the server);
CSP and the other headers govern what the *browser* is allowed to do, so they
cannot open or close either server-side chain. They close unintended
browser-side holes instead: XSS execution, clickjacking, MIME-sniffing,
referrer/permission leakage, and (over HTTPS) protocol downgrade.

CSP is per-path:
  - storefront + own admin pages: strict script-src 'self' (no inline JS in
    those templates, so nothing breaks).
  - /admin/db (the third-party Flask-Admin DB console): needs 'unsafe-inline'
    for its own inline scripts, scoped to that path only.
  - img-src allows 'self' (avatars are served from the auth.avatar route) and
    data: (the 2FA QR code is a data: URI).
In the test/dev config the policy is sent as Content-Security-Policy-Report-Only
so violations are reported but nothing is blocked during the demo; production
enforces it.
"""
from flask import request


# Strict policy for the storefront and the app's own admin pages.
_CSP_STRICT = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Looser policy scoped ONLY to the Flask-Admin DB console, which relies on
# inline scripts it ships itself.
_CSP_DBCONSOLE = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def _csp_for_path(path):
    if path.startswith("/admin/db"):
        return _CSP_DBCONSOLE
    return _CSP_STRICT


def init_security_headers(app):
    report_only = app.config.get("CSP_REPORT_ONLY", False)

    @app.after_request
    def _apply_security_headers(response):
        csp = _csp_for_path(request.path)
        header = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
        response.headers.setdefault(header, csp)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )

        # HSTS only over HTTPS, so the plain-http dev/demo server is untouched.
        # request.is_secure honours the proxy's X-Forwarded-Proto when the app
        # runs behind a TLS-terminating reverse proxy.
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    return app
