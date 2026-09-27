# safe_config.py
# CRITICAL: do NOT add any imports to this file.
# The SSTI scoping depends on this module's __globals__
# containing nothing dangerous.
# No os, no subprocess, no sys, no importlib.


class SafeConfigProxy:
    """
    Stripped read-only view of the app config safe to expose
    in Jinja2 template context.

    The standard SSTI chain:
        config.__class__.__init__.__globals__['os'].popen()
    reaches THIS module's globals — which contains nothing.
    Chain terminates here, os.popen() is unreachable.

    Only exposes values templates legitimately need.
    Everything else — SECRET_KEY, ENCRYPTION_KEY, DB URI,
    PLUGIN_DIR, SSRF_TIMEOUT — is hidden.
    """

    _ALLOWED_KEYS = {
        'SITE_NAME',
        'DEBUG',
        'MAX_CART_SIZE',
        'POSTS_PER_PAGE',
    }

    def __init__(self, cfg):
        # Pull only the allowed keys from the real config
        self._data = {
            k: getattr(cfg, k, None)
            for k in self._ALLOWED_KEYS
        }

    def __getitem__(self, key):
        return self._data.get(key)

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __repr__(self):
        return f"SafeConfigProxy({list(self._data.keys())})"