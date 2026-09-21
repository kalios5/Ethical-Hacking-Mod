"""
security_plugins/new_device_alert/  -  flags a login from an unrecognized IP.

Read-only: queries the audit_log table (LOGIN_SUCCESS rows carry actor_ip)
to check whether this user has ever logged in from this IP before. Static
import only from app/auth/routes.py's login().

The check runs AFTER authenticate() confirms the password, and only counts
audit rows from BEFORE this login attempt (see `before_time`) - checking
before password verification would leak whether a username exists, and not
excluding this attempt's own just-written row would always report "new".
"""


def register(shop=None):
    pass


def render_widget(context=None):
    return ""


def is_new_ip(user, ip, before_time):
    from app.Database.models import AuditLog

    if not ip:
        return False

    seen = AuditLog.query.filter(
        AuditLog.actor_user_id == user.id,
        AuditLog.action == "LOGIN_SUCCESS",
        AuditLog.actor_ip == ip,
        AuditLog.ts < before_time,
    ).first()
    return seen is None


PLUGIN_NAME = "New Device / Location Alert"
PLUGIN_DESCRIPTION = (
    "Flags a login when this account has not been seen from this IP "
    "address before."
)
