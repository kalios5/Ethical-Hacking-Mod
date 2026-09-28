"""
pluginmanager/security_plugins/login_captcha/  -  challenge-response CAPTCHA
on the login form after repeated failures.

Same family as temp_lockout / ip_rate_limit: a security control statically
imported from app/auth/routes.py's login() and toggleable via
/admin/security-settings. Lives under app/pluginmanager/security_plugins/
(trusted, hand-written), NOT under app/pluginmanager/plugins/ (where the
upload feature writes and where the loader imports whatever it finds), so it
is never reachable through dynamic plugin dispatch.

WHY A SELF-CONTAINED ARITHMETIC CHALLENGE (not reCAPTCHA/hCaptcha)
-----------------------------------------------------------------
The graded deployment is a frozen server that must keep running and stay
reachable. A third-party CAPTCHA service would add a hard runtime dependency
on an external API (network egress, keys, an outage = nobody can log in during
the demo). A local "what is 7 + 4?" challenge needs no network and no keys.
It's a demonstrable bot-friction control, not a Turing-hard one - the honest
framing for the report.

WHY IT ONLY KICKS IN AFTER FAILURES
-----------------------------------
Showing a puzzle on every login is pointless friction and clutters the demo.
This arms the challenge for an IP only once that IP has racked up
TRIGGER_AFTER failed attempts within the window - exactly the automated-
guessing behaviour a CAPTCHA is meant to slow. A human who fails once or
twice never sees it.

RELATIONSHIP TO THE INTENDED LAB VULNERABILITIES
------------------------------------------------
None. This gates the browser login form only. The plugin-upload RCE runs
server-side after an admin is authenticated; the avatar->SSTI privesc is a
server-side file write + template render. Nothing here touches either.

STATE MODEL
-----------
In-memory, single-process - same limitation as temp_lockout/ip_rate_limit.
Fine for this single-process deployment; a production version would move the
arming set and pending answers into Redis or a table.
"""
import random
import time

PLUGIN_NAME = "Login CAPTCHA"
PLUGIN_DESCRIPTION = (
    "After repeated failed logins from the same network, adds a simple "
    "arithmetic challenge to the login form to slow automated "
    "credential-guessing. Users who log in cleanly never see it."
)

TRIGGER_AFTER = 3
WINDOW_SECONDS = 15 * 60

_failures = {}          # {ip: [failure timestamps]}
_pending = {}           # {token: {"answer": int, "expires": float}}
_CHALLENGE_TTL = 5 * 60


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


def reset_on_success(ip):
    _failures.pop(ip, None)


def is_required(ip):
    if not ip:
        return False
    return len(_recent(ip)) >= TRIGGER_AFTER


def _prune():
    now = time.time()
    for tok in [t for t, c in _pending.items() if c["expires"] <= now]:
        del _pending[tok]


def new_challenge():
    """Create a challenge; returns (token, question_text). The answer is held
    server-side keyed by an opaque token, so the client never sees it."""
    _prune()
    a, b = random.randint(1, 9), random.randint(1, 9)
    token = "%032x" % random.getrandbits(128)
    _pending[token] = {"answer": a + b, "expires": time.time() + _CHALLENGE_TTL}
    return token, f"What is {a} + {b}?"


def verify(token, supplied):
    """True only if `token` is a live, unused challenge whose answer matches
    `supplied`. The token is consumed either way, so a wrong guess forces a
    fresh challenge rather than allowing brute-force on one token."""
    _prune()
    challenge = _pending.pop(token, None)
    if challenge is None:
        return False
    try:
        return int(str(supplied).strip()) == challenge["answer"]
    except (TypeError, ValueError):
        return False
