"""
pluginmanager/security_plugins/temp_lockout/  -  temporary account lockout with
exponential backoff, plus admin visibility into active lockouts.

Lives under app/pluginmanager/security_plugins/, as a sibling to
app/pluginmanager/plugins/ - NOT inside plugins/, which is where the
upload feature writes and where the plugin loader blindly imports whatever
it finds. Only ever reached via a static import from app/auth/routes.py's
login() (and app/admin/routes.py's security_settings(), for visibility)
- never through dynamic plugin dispatch.

Tracks its OWN rolling window of recent failures per user, independently
of User.failed_logins (that DB column is a permanent, ever-incrementing
historical count reset only by a successful login - using it directly
caused a real bug where a single failure after a lockout expired would
instantly re-trigger the lockout, since the DB counter never actually
went back down). This module's window resets on its own once a lockout is
set, so unlocking always grants a fresh MAX_FAILED_ATTEMPTS.

EXPONENTIAL BACKOFF: each time the SAME account triggers a lockout again
without an intervening successful login, the cooldown doubles
(BASE_LOCKOUT_SECONDS, then x2, x4, ...) up to MAX_LOCKOUT_SECONDS. This
specifically targets sustained/scripted brute-forcing - a flat cooldown
barely slows an automated attacker down (fail 5, sleep, repeat forever,
at the same cost every cycle); a growing cooldown makes that cost rise
every time. A successful login clears the streak via reset_on_success().

NOTE: in-memory, single-process only - resets on app restart, and does NOT
work correctly with more than one worker process (e.g. gunicorn -w 2+),
since each worker has its own separate dict. Not a concern for this
project (single process, and the system is meant to stay running rather
than restart after Week 6), but a production version would persist this
in a small shared table or Redis instead.
"""
import time

PLUGIN_NAME = "Temporary Lockout"
PLUGIN_DESCRIPTION = (
    "Temporarily locks an account for a cooldown period after repeated "
    "failed logins. The cooldown doubles each time the same account "
    "triggers it again, to resist sustained brute-forcing rather than "
    "just a one-off mistake."
)

MAX_FAILED_ATTEMPTS = 5
BASE_LOCKOUT_SECONDS = 60
MAX_LOCKOUT_SECONDS = 30 * 60  # cap growth at 30 minutes

# {user_id: [timestamps of recent failures since the last lockout/unlock]}
_failures = {}
# {user_id: unix_timestamp_when_unlocked}
_lockouts = {}
# {user_id: number of consecutive lockouts without an intervening success}
_strikes = {}


def register(shop=None):
    pass


def render_widget(context=None):
    return ""


def record_failed_attempt(user):
    """Call after a failed login (only while NOT already locked out)."""
    now = time.time()
    attempts = _failures.get(user.id, [])
    attempts.append(now)
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        strikes = _strikes.get(user.id, 0) + 1
        _strikes[user.id] = strikes
        duration = min(BASE_LOCKOUT_SECONDS * (2 ** (strikes - 1)), MAX_LOCKOUT_SECONDS)
        _lockouts[user.id] = now + duration
        _failures[user.id] = []  # fresh slate for the next cycle
    else:
        _failures[user.id] = attempts


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


def reset_on_success(user):
    """Call after a SUCCESSFUL login. Clears the strike streak so the
    backoff doesn't keep growing for an account that just had one bad
    stretch and then got in correctly."""
    _strikes.pop(user.id, None)
    _failures.pop(user.id, None)


def current_lockouts():
    """For the admin visibility view. Returns a list of dicts for every
    CURRENTLY active lockout (already-expired ones are skipped, and lazily
    cleaned out of _lockouts here so the dict doesn't grow forever)."""
    now = time.time()
    active = []
    for uid, unlock_at in list(_lockouts.items()):
        remaining = unlock_at - now
        if remaining <= 0:
            del _lockouts[uid]
            continue
        active.append({
            "user_id": uid,
            "seconds_remaining": int(remaining),
            "strikes": _strikes.get(uid, 1),
        })
    return active
