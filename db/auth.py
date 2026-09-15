"""
db/auth.py  -  DB-backed authentication + login audit logging.

WHY THIS EXISTS
---------------
pluginmanager/routes.py currently authenticates like this:

    if username == "admin" and password == "admin123":
        session["logged_in"] = True

That hardcoded check means there is nothing in the database for an attacker to
dump, and nothing gets logged. This module replaces it with a real lookup
against the `users` table, and records every attempt (success AND failure) to
both logs/app.log and the audit_log table - which is the point of the
DB-container deliverable.

HOW THE APP MEMBER USES IT
--------------------------
In pluginmanager/routes.py, replace the hardcoded branch with:

    from db.auth import authenticate

    user = authenticate(username, password, ip=request.remote_addr)
    if user:
        session["logged_in"] = True
        session["username"] = user.username
        session["user_id"]  = user.id          # <- enables the IDOR path
        session["role"]     = user.role
        return redirect(url_for("pluginmanager.admin_dashboard"))
    return render_template("login.html", error="Invalid username or password")

Seeded logins (see deployment/db/init/02_seed.sql):
    superadmin / SuperSecret@2026   (role: superadmin)
    admin      / Admin@123          (role: admin,    shop 1 roses-4-sale)
    admin      / Petal!2026         (role: admin,    shop 2 poppies-2-buy)
    alice      / password1          (role: customer)
"""
from datetime import datetime

from . import db
from .models import User
from .security import verify_password

# Imported lazily inside functions so this module still works if the logging
# package isn't wired up yet.


def _audit(*args, **kwargs):
    try:
        from logging_setup.db_audit import audit
        audit(*args, **kwargs)
    except Exception:
        pass


def authenticate(username, password, shop_id=None, ip=None):
    """Return the User on success, or None.

    Logs LOGIN_SUCCESS / LOGIN_FAILED either way, and keeps
    users.failed_logins + users.last_login up to date so the admin console can
    show "suspicious activity" during the defender demo.
    """
    from logging_setup.db_audit import actions

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
    user.last_login = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    _audit(actions.LOGIN_SUCCESS, actor=user, ip=ip,
           detail=f"role={user.role}")
    return user


def create_user(shop_id, username, email, password, role="customer", mode=None):
    """Helper for the admin console / user-management member."""
    from logging_setup.db_audit import actions
    from .config import DBConfig

    mode = mode or DBConfig.PASSWORD_HASH_MODE
    user = User(shop_id=shop_id, username=username, email=email,
                role=role, hash_mode=mode)
    user.set_password(password, mode)
    db.session.add(user)
    db.session.commit()
    _audit(actions.USER_CREATED, actor=user, target_type="user",
           target_id=user.id, detail=f"role={role} hash_mode={mode}")
    return user
