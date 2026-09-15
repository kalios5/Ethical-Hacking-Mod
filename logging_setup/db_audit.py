"""
logging_setup/db_audit.py  -  DB audit logging (application-written events).

audit() records a security-relevant event in TWO places:
  1. the audit_log table (queryable, survives, shown in an admin log view)
  2. logs/app.log via the 'audit' logger (grep-able, picked up by SIEM/PoC)

This is the application half of the logging deliverable. The database half is
the trigger-written db_change_log table (see 03_triggers.sql), which catches
changes made by talking to MySQL directly, behind the app's back.

Call it from the app members' routes at the key points in the attack chain, e.g.

    audit(actions.LOGIN_SUCCESS, actor=user, ip=request.remote_addr)
    audit(actions.LOGIN_FAILED, ip=request.remote_addr, success=False,
          detail=f"username={attempted}")
    audit(actions.ADMIN_CONSOLE_VIEW, actor=current_user, ip=request.remote_addr)
    audit(actions.PLUGIN_IMPORT, actor=current_user, target_type="plugin",
          target_id=name, detail="third-party upload")
"""
import logging

_log = logging.getLogger("audit")


class actions:
    """Canonical action names - use these so logs are consistent & grep-able."""
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TWOFA_CHALLENGE = "TWOFA_CHALLENGE"
    TWOFA_SUCCESS = "TWOFA_SUCCESS"
    USER_CREATED = "USER_CREATED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    ROLE_CHANGED = "ROLE_CHANGED"
    ADMIN_CONSOLE_VIEW = "ADMIN_CONSOLE_VIEW"     # IDOR target
    DB_CONSOLE_ACCESS = "DB_CONSOLE_ACCESS"
    PLUGIN_TOGGLE = "PLUGIN_TOGGLE"
    PLUGIN_IMPORT = "PLUGIN_IMPORT"               # malicious plugin upload
    ORDER_PLACED = "ORDER_PLACED"
    ACCESS_DENIED = "ACCESS_DENIED"


def _actor_id(actor):
    if actor is None:
        return None
    return getattr(actor, "id", actor)  # accept a User object or a raw id


def audit(action, actor=None, ip=None, shop_id=None,
          target_type=None, target_id=None, success=True, detail=None):
    """Write one audit event. Never raises - logging must not break the app."""
    actor_id = _actor_id(actor)
    shop = shop_id if shop_id is not None else getattr(actor, "shop_id", None)

    # 1) always write to the file log first (cheapest, most reliable).
    _log.info(
        "action=%s actor=%s ip=%s shop=%s target=%s/%s success=%s detail=%s",
        action, actor_id, ip, shop, target_type, target_id, success, detail,
    )

    # 2) best-effort write to the audit_log table.
    try:
        from db import db
        from db.models import AuditLog
        row = AuditLog(
            actor_user_id=actor_id, actor_ip=ip, shop_id=shop,
            action=action, target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            success=bool(success), detail=detail,
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        _log.exception("failed to persist audit row (file log still recorded)")
        try:
            from db import db
            db.session.rollback()
        except Exception:
            pass
