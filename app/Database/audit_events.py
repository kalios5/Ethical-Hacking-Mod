"""
app/Database/audit_events.py  -  SQLAlchemy-level replacement for the old
MySQL trigger-based DB audit trail (deployment/db/init/03_triggers.sql).

WHY THIS EXISTS
----------------
The DB init scripts were written in MySQL/MariaDB dialect while the project
actually runs on Postgres (docker-compose.yml uses `postgres:18`), and were
never even mounted into the `db` container's init directory - so the
trigger-based `db_change_log` was never actually populated. This module
reimplements that behaviour (plus the app-level `audit_log`) as SQLAlchemy
mapper-level events, which fire for every insert/update/delete made through
this app's ORM, across every mutable table.

TRADEOFF vs. real DB triggers (documented, accepted): a real trigger fires on
ANY write to the table, including raw SQL run directly against the database
by an attacker who bypassed the Flask app entirely. These listeners only see
writes made through this app's `db.session`. Since the trigger-based version
never actually ran (dialect mismatch + missing volume mount), this is a net
improvement over the prior (non-functional) state, not a regression from a
working one. If a true "survives raw SQL access" guarantee is needed later,
replace this module with real Postgres-native triggers/functions.

IMPLEMENTATION NOTE
--------------------
These are mapper-level events (`before_update`/`before_delete`/`after_insert`),
not session-level `before_flush`. Mapper events hand us the raw `Connection`
already inside the flush's transaction, so we write with plain Core inserts
via that connection instead of `db.session.add()`/`commit()` - touching the
ORM session again from inside its own flush is exactly what SQLAlchemy's docs
warn against. `after_insert` is used (not `before_insert`) so the row's
auto-generated primary key is already populated; `before_update`/
`before_delete` are used instead of their `after_` counterparts so the
pre-write attribute history (needed to describe *what* changed) is still
intact.

WHAT GETS LOGGED
-----------------
Every insert/update/delete on any of TRACKED_MODELS writes:
  1. a `db_change_log` row (db_user/table/op/row_pk/detail) - the DB-layer
     half, independent of *why* the write happened.
  2. an `audit_log` row - the app-layer half, including the acting user (from
     the Flask session, when available), the client IP, and the request
     path/URL the action happened on.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import event, inspect, text

from app import db
from app.Database.models import (
    AuditLog, CartItem, DbChangeLog, Order, OrderItem, Plugin, Product, User,
)

_log = logging.getLogger("audit")

# Model -> human label used to build AuditLog.action, e.g. "PRODUCT_UPDATED".
TRACKED_MODELS = {
    User: "USER",
    Product: "PRODUCT",
    CartItem: "CART_ITEM",
    Order: "ORDER",
    OrderItem: "ORDER_ITEM",
    Plugin: "PLUGIN",
}

_OP_LABEL = {"insert": "CREATED", "update": "UPDATED", "delete": "DELETED"}


def _current_db_user(connection):
    """The DB-layer 'who' for db_change_log.db_user. Falls back gracefully on
    SQLite (local/dev default), which has no CURRENT_USER()."""
    try:
        return connection.execute(text("SELECT current_user")).scalar()
    except Exception:
        try:
            return connection.engine.url.username or "app"
        except Exception:
            return "app"


def _request_context():
    """Best-effort (actor_id, ip, request_path) pulled from the active Flask
    request/session. Returns (None, None, None) outside of a request
    (CLI, seeding, etc.)."""
    try:
        from flask import has_request_context, request, session
        if not has_request_context():
            return None, None, None
        return session.get("user_id"), request.remote_addr, request.full_path.rstrip("?")
    except Exception:
        return None, None, None


def _changed_columns(target):
    """{column_name: (old, new)} for columns with a pending change, read from
    attribute history - must be called BEFORE the UPDATE is emitted."""
    changed = {}
    state = inspect(target)
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if history.has_changes():
            old = history.deleted[0] if history.deleted else None
            new = history.added[0] if history.added else getattr(target, attr.key)
            changed[attr.key] = (old, new)
    return changed


def _describe(op, target, changed=None):
    if op == "update":
        return ", ".join(
            f"{col}: {old!r}->{new!r}" for col, (old, new) in (changed or {}).items()
        ) or "no field changes detected"
    # insert / delete: a short snapshot of the row.
    state = inspect(target)
    fields = {attr.key: getattr(target, attr.key) for attr in state.mapper.column_attrs}
    return ", ".join(f"{k}={v!r}" for k, v in fields.items())


def _record(connection, op, target, changed=None):
    table_name = target.__tablename__
    row_pk = getattr(target, "id", None)
    detail = _describe(op, target, changed)

    connection.execute(DbChangeLog.__table__.insert().values(
        ts=datetime.utcnow(), db_user=_current_db_user(connection),
        table_name=table_name, op=op.upper(),
        row_pk=str(row_pk) if row_pk is not None else None, detail=detail,
    ))

    actor_id, ip, path = _request_context()
    label = TRACKED_MODELS[type(target)]
    action = f"{label}_{_OP_LABEL[op]}"

    # File log line, same shape as app.logging.db_audit.audit()'s.
    _log.info(
        "action=%s actor=%s ip=%s target=%s/%s success=True path=%s detail=%s",
        action, actor_id, ip, table_name.rstrip("s"), row_pk, path, detail,
    )
    connection.execute(AuditLog.__table__.insert().values(
        ts=datetime.utcnow(), actor_user_id=actor_id, actor_ip=ip,
        action=action, target_type=table_name.rstrip("s"),
        target_id=str(row_pk) if row_pk is not None else None,
        success=True, detail=detail, request_path=path,
    ))


def _listener(op):
    def _handle(mapper, connection, target):
        try:
            changed = _changed_columns(target) if op == "update" else None
            _record(connection, op, target, changed)
        except Exception:
            _log.exception("audit_events listener failed for %s on %s", op, type(target).__name__)
    return _handle


for _model in TRACKED_MODELS:
    event.listen(_model, "after_insert", _listener("insert"))
    event.listen(_model, "before_update", _listener("update"))
    event.listen(_model, "before_delete", _listener("delete"))


def prune_old_audit_rows(days=7):
    """Delete audit_log / db_change_log rows older than `days`. Called once
    at app startup (see app/__init__.py::create_app) so both DB-side logs
    stay bounded to roughly the same retention window as the rotated
    logs/app.log file (see app/logging/app_logging.py). A real production
    deployment would run this on a schedule instead of only at boot."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        AuditLog.query.filter(AuditLog.ts < cutoff).delete(synchronize_session=False)
        DbChangeLog.query.filter(DbChangeLog.ts < cutoff).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
