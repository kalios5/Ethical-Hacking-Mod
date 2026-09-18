"""
security_plugins/temp_lockout/  -  temporary (non-permanent) account lockout.

Top-level, sibling to app/ and logging_setup/ - NOT inside app/plugins/,
which is where the upload feature writes and where app/main/loader.py's
discover_plugins() blindly imports whatever it finds. Only ever reached via
a static import from app/auth/routes.py's login() - never through dynamic
plugin dispatch.

Locks the account for a fixed cooldown window after too many failed
attempts, then automatically allows attempts again.

NOTE: tracks lockouts in an in-memory dict, so it resets on app restart and
only works correctly with a single worker process. A persisted version
would use a small dedicated table via the shared `db` object instead.
"""
import time

PLUGIN_NAME = "Temporary Lockout"
PLUGIN_DESCRIPTION = (
    "Temporarily locks an account for a cooldown period after repeated "
    "failed logins, instead of locking it forever."
)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

_lockouts = {}


def register(shop=None):
    pass


def render_widget(context=None):
    return ""


def record_failed_attempt(user):
    if (user.failed_logins or 0) >= MAX_FAILED_ATTEMPTS:
        _lockouts[user.id] = time.time() + LOCKOUT_SECONDS


def is_locked_out(user):
    unlock_at = _lockouts.get(user.id)
    if unlock_at is None:
        return False
    if time.time() >= unlock_at:
        del _lockouts[user.id]
        return False
    return True


def seconds_remaining(user):
    unlock_at = _lockouts.get(user.id)
    if unlock_at is None:
        return 0
    return max(0, int(unlock_at - time.time()))
