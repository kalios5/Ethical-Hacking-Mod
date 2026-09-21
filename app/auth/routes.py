from functools import wraps

from datetime import datetime
from flask import flash, redirect, render_template, request, session, url_for

from app import db
from app.auth import bp
from app.Database.auth import authenticate
from app.logging.db_audit import actions, audit
from app.Database.models import User, Plugin
from app.security_plugins.temp_lockout import is_locked_out, record_failed_attempt, seconds_remaining, reset_on_success
from app.security_plugins.new_device_alert import is_new_ip
from app.security_plugins import ip_rate_limit as ip_limiter


def _feature_enabled(shop_id, name):
    toggle = Plugin.query.filter_by(shop_id=shop_id, name=name).first()
    return toggle.enabled if toggle else True


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "notice")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip = request.remote_addr

        # Shop 1 is the only shop in local/dev use - all three security
        # feature toggles below are scoped to it (see
        # /admin/security-settings).
        ip_limit_enabled = _feature_enabled(1, "ip_rate_limit")
        if ip_limit_enabled and ip_limiter.is_ip_blocked(ip):
            remaining = ip_limiter.seconds_until_reset(ip)
            audit(actions.ACCESS_DENIED, ip=ip, success=False,
                  detail=f"IP rate limit, {remaining}s remaining")
            flash(f"Too many login attempts from this network. Try again in {remaining} seconds.", "error")
            return render_template("auth/login.html")

        existing_user = User.query.filter_by(username=username).first()

        # Prototype security plugin, statically imported (see
        # security_plugins/temp_lockout/__init__.py). Only enforced when
        # this shop has it enabled via /admin/security-settings.
        lockout_enabled = _feature_enabled(existing_user.shop_id, "temp_lockout") if existing_user else True
        if existing_user and lockout_enabled and is_locked_out(existing_user):
            remaining = seconds_remaining(existing_user)
            audit(actions.ACCESS_DENIED, actor=existing_user, ip=ip,
                  shop_id=existing_user.shop_id, target_type="user",
                  target_id=existing_user.id, success=False,
                  detail=f"temporary lockout, {remaining}s remaining")
            flash(f"Too many failed attempts. Try again in {remaining} seconds.", "error")
            return render_template("auth/login.html")

        check_time = datetime.utcnow()

        # Real DB-backed auth (app/Database/auth.py) — logs LOGIN_SUCCESS /
        # LOGIN_FAILED to the audit log and keeps failed_logins current.
        user = authenticate(username, password, ip=ip)
        if user:
            # session.clear() must run BEFORE any flash() calls for this
            # login - flash() stores messages inside the session, and
            # clear() wipes anything flashed before it runs.
            session.clear()
            session["user_id"] = user.id
            reset_on_success(user)

            new_device_enabled = _feature_enabled(user.shop_id, "new_device_alert")
            if new_device_enabled and is_new_ip(user, ip, check_time):
                flash("New sign-in detected from an unrecognized location.", "notice")

            flash(f"Welcome back, {user.username}.", "success")
            target = request.args.get("next") or url_for("storefront.index")
            return redirect(target if target.startswith("/") else url_for("storefront.index"))

        if ip_limit_enabled:
            ip_limiter.record_failed_attempt(ip)
        if lockout_enabled and existing_user:
            db.session.refresh(existing_user)
            record_failed_attempt(existing_user)
        flash("Invalid username or password.", "error")
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("storefront.index"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not username or not email or len(password) < 8:
            flash("Use a username, email, and password of at least 8 characters.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already in use.", "error")
        else:
            user = User(shop_id=1, username=username, email=email, role="customer", hash_mode="secure")
            user.set_password(password, "secure")
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = current_user()
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not email:
            flash("Email cannot be empty.", "error")
        else:
            user.email = email
            if password:
                if len(password) < 8:
                    flash("A new password must have at least 8 characters.", "error")
                    return render_template("auth/account.html", user=user)
                user.set_password(password, "secure")
            db.session.commit()
            flash("Account updated.", "success")
    return render_template("auth/account.html", user=user)