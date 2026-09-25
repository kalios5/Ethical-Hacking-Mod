"""
logging_setup/db_audit.py  -  DB audit logging (application-written events).

audit() records a security-relevant event in TWO places:
  1. the audit_log table (queryable, survives, shown in an admin log view)
  2. logs/app.log via the 'audit' logger (grep-able, picked up by SIEM/PoC)

This is the application half of the logging deliverable. The database half is
the db_change_log table, populated by the SQLAlchemy event listeners in
app/Database/audit_events.py, which record every insert/update/delete made
through the app's ORM session (see that module's docstring for the tradeoff
vs. real DB-level triggers).

Call it from the app members' routes at the key points in the attack chain, e.g.

    audit(actions.LOGIN_SUCCESS, actor=user, ip=request.remote_addr)
    audit(actions.LOGIN_FAILED, ip=request.remote_addr, success=False,
          detail=f"username={attempted}")
    audit(actions.DB_CONSOLE_ACCESS, actor=current_user, ip=request.remote_addr)
    audit(actions.PLUGIN_IMPORT, actor=current_user, target_type="plugin",
          target_id=name, detail="third-party upload")
"""
import logging

_log = logging.getLogger("audit")


class actions:
    """Canonical action names - use these so logs are consistent & grep-able."""
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    TWOFA_CHALLENGE = "TWOFA_CHALLENGE"
    TWOFA_SUCCESS = "TWOFA_SUCCESS"
    USER_CREATED = "USER_CREATED"
    DB_CONSOLE_ACCESS = "DB_CONSOLE_ACCESS"
    PLUGIN_TOGGLE = "PLUGIN_TOGGLE"
    PLUGIN_IMPORT = "PLUGIN_IMPORT"               # malicious plugin upload
    PROFILE_UPDATED = "PROFILE_UPDATED"
    DB_EXPORT = "DB_EXPORT"
    ORDER_PLACED = "ORDER_PLACED"
    ACCESS_DENIED = "ACCESS_DENIED"


def _actor_id(actor):
    if actor is None:
        return None
    return getattr(actor, "id", actor)  # accept a User object or a raw id


def _request_defaults():
    """Best-effort (actor_id, ip, request_path) pulled from the active Flask
    request/session, for callers (e.g. the DB event listeners in
    app/Database/audit_events.py) that don't have that context handy.
    Returns (None, None, None) outside of a request (CLI, seeding, etc.)."""
    try:
        from flask import has_request_context, request, session
        if not has_request_context():
            return None, None, None
        return session.get("user_id"), request.remote_addr, request.full_path.rstrip("?")
    except Exception:
        return None, None, None


def audit(action, actor=None, ip=None, shop_id=None,
          target_type=None, target_id=None, success=True, detail=None,
          request_path=None):
    """Write one audit event. Never raises - logging must not break the app.

    Note: app/Database/audit_events.py (the per-table insert/update/delete
    listeners) writes db_change_log/audit_log rows directly via Core inserts
    instead of calling this function, because those listeners fire from
    inside an active session.flush() where nesting another commit() here
    would corrupt that outer transaction. This audit() helper remains the
    entry point for route-level, non-single-row events (logins, checkout,
    plugin toggles, etc.).
    """
    req_actor_id, req_ip, req_path = _request_defaults()
    actor_id = _actor_id(actor) if actor is not None else req_actor_id
    ip = ip if ip is not None else req_ip
    request_path = request_path if request_path is not None else req_path
    shop = shop_id if shop_id is not None else getattr(actor, "shop_id", None)

    # 1) always write to the file log first (cheapest, most reliable).
    _log.info(
        "action=%s actor=%s ip=%s shop=%s target=%s/%s success=%s path=%s detail=%s",
        action, actor_id, ip, shop, target_type, target_id, success, request_path, detail,
    )

    # 2) best-effort write to the audit_log table.
    try:
        from app import db
        from app.Database.models import AuditLog
        row = AuditLog(
            actor_user_id=actor_id, actor_ip=ip, shop_id=shop,
            action=action, target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            success=bool(success), detail=detail, request_path=request_path,
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        _log.exception("failed to persist audit row (file log still recorded)")
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
