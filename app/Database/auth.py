"""
Database/auth.py  -  DB-backed authentication + login audit logging.

authenticate() looks the user up in the `users` table, verifies the password
with Database/security.py, keeps failed_logins/last_login current, and logs
LOGIN_SUCCESS / LOGIN_FAILED to logs/app.log and the audit_log table. It is
called from auth/routes.py::login().

Seeded logins (see app/__init__.py::_seed_development_data()):
    superadmin / SuperSecret@2026   (role: superadmin)
    admin      / admin              (role: admin,    shop 1 roses-4-sale)
    admin      / Petal!2026         (role: admin,    shop 2 poppies-2-buy)
    alice      / password1          (role: customer)
"""
from datetime import datetime

from app import db
from app.Database.models import User
from app.Database.security import verify_password


def _audit(*args, **kwargs):
    try:
        from app.logging.db_audit import audit
        audit(*args, **kwargs)
    except Exception:
        pass


def authenticate(username, password, shop_id=None, ip=None):
    """Return the User on success, or None.

    Logs LOGIN_SUCCESS / LOGIN_FAILED either way, and keeps
    users.failed_logins + users.last_login up to date so the admin console can
    show "suspicious activity" during the defender demo.
    """
    from app.logging.db_audit import actions

    q = User.query.filter_by(username=username)
    if shop_id is not None:
        q = q.filter_by(shop_id=shop_id)
    user = q.first()

    # Unknown username.
    if user is None:
        _audit(actions.LOGIN_FAILED, ip=ip, success=False,
               detail=f"unknown username={username!r}")
        return None

    # Disabled account.
    if not user.is_active:
        _audit(actions.LOGIN_FAILED, actor=user, ip=ip, success=False,
               detail="account disabled")
        return None

    # Wrong password.
    if not verify_password(password, user.password_hash, user.hash_mode):
        user.failed_logins = (user.failed_logins or 0) + 1
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        _audit(actions.LOGIN_FAILED, actor=user, ip=ip, success=False,
               detail=f"bad password (attempt #{user.failed_logins})")
        return None

    # Success.
    user.failed_logins = 0
    user.last_login = datetime.now()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    _audit(actions.LOGIN_SUCCESS, actor=user, ip=ip,
           detail=f"role={user.role}")
    return user


def create_user(shop_id, username, email, password, role="customer", mode='weak'):
    """Helper for the admin console / user-management member."""
    from app.logging.db_audit import actions

    user = User(shop_id=shop_id, username=username, email=email,
                role=role, hash_mode=mode)
    user.set_password(password, mode)
    db.session.add(user)
    db.session.commit()
    _audit(actions.USER_CREATED, actor=user, target_type="user",
           target_id=user.id, detail=f"role={role} hash_mode={mode}")
    return user
