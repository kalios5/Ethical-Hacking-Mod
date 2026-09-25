"""
pluginmanager/security_plugins/ip_rate_limit/  -  per-IP login throttling.

Different axis from temp_lockout: that plugin locks one ACCOUNT after
repeated failures against it. This blocks an IP ADDRESS after repeated
failures regardless of which username was tried, closing the gap where an
attacker sprays guesses across many accounts from one IP.

Static import only. In-memory, single-process - same limitation as
temp_lockout.
"""
import time

PLUGIN_NAME = "Per-IP Login Rate Limiting"
PLUGIN_DESCRIPTION = (
    "Blocks further login attempts from an IP address after too many "
    "failures within a short window, regardless of which username was tried."
)

MAX_ATTEMPTS_PER_IP = 10
WINDOW_SECONDS = 60

_failures = {}


def register(shop=None):
    pass


def render_widget(context=None):
    return ""


def _recent(ip):
    now = time.time()
    attempts = [t for t in _failures.get(ip, []) if now - t < WINDOW_SECONDS]
    _failures[ip] = attempts
    return attempts


def record_failed_attempt(ip):
    if not ip:
        return
    attempts = _recent(ip)
    attempts.append(time.time())
    _failures[ip] = attempts


def is_ip_blocked(ip):
    if not ip:
        return False
    return len(_recent(ip)) >= MAX_ATTEMPTS_PER_IP


def seconds_until_reset(ip):
    attempts = _recent(ip)
    if not attempts:
        return 0
    oldest = min(attempts)
    return max(0, int(WINDOW_SECONDS - (time.time() - oldest)))
