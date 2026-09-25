import re
from functools import wraps

from datetime import datetime
from flask import abort, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for

from app import db
from app.auth import bp
from app.Database.auth import authenticate
from app.logging.db_audit import actions, audit
from app.Database.models import User, Plugin
from app.pluginmanager.security_plugins.temp_lockout import is_locked_out, record_failed_attempt, seconds_remaining, reset_on_success
from app.pluginmanager.security_plugins.new_device_alert import is_new_ip
from app.pluginmanager.security_plugins import ip_rate_limit as ip_limiter
from app.auth import twofa
from app.uploads import delete_avatar, save_avatar


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
        # pluginmanager/security_plugins/temp_lockout/__init__.py). Only enforced when
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
            # If 2FA is on for this account, DON'T complete login yet -
            # stash a pending marker and divert to the code-entry page.
            # The session stays unauthenticated (no user_id) until verified.
            if user.twofa_enabled and user.twofa_secret:
                session.clear()
                session["pending_2fa_user_id"] = user.id
                session["pending_2fa_ip"] = ip
                session["pending_2fa_check_time"] = check_time.isoformat()
                reset_on_success(user)
                audit(actions.TWOFA_CHALLENGE, actor=user, ip=ip, shop_id=user.shop_id,
                      target_type="user", target_id=user.id, success=True,
                      detail="password ok, awaiting 2FA")
                return redirect(url_for("auth.two_factor"))

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


@bp.route("/2fa", methods=["GET", "POST"])
def two_factor():
    # Second step of a 2FA login. Reachable only when login() verified the
    # password and stashed pending_2fa_user_id - session NOT yet authed.
    pending_id = session.get("pending_2fa_user_id")
    if not pending_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, pending_id)
    if user is None or not user.twofa_enabled:
        session.clear()
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = request.form.get("code", "")
        if twofa.verify_code(user, code):
            ip = session.get("pending_2fa_ip")
            check_time_raw = session.get("pending_2fa_check_time")
            session.clear()
            session["user_id"] = user.id
            audit(actions.TWOFA_SUCCESS, actor=user, ip=ip, shop_id=user.shop_id,
                  target_type="user", target_id=user.id, success=True, detail="2FA verified, login complete")
            new_device_enabled = _feature_enabled(user.shop_id, "new_device_alert")
            if new_device_enabled and check_time_raw:
                try:
                    if is_new_ip(user, ip, datetime.fromisoformat(check_time_raw)):
                        flash("New sign-in detected from an unrecognized location.", "notice")
                except ValueError:
                    pass
            flash(f"Welcome back, {user.username}.", "success")
            return redirect(url_for("storefront.index"))

        audit(actions.ACCESS_DENIED, actor=user, ip=session.get("pending_2fa_ip"),
              shop_id=user.shop_id, target_type="user", target_id=user.id,
              success=False, detail="bad 2FA code")
        flash("Invalid authentication code.", "error")

    return render_template("auth/two_factor.html")


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
        avatar = request.files.get("avatar")
        if not email:
            flash("Email cannot be empty.", "error")
        else:
            if password and len(password) < 8:
                flash("A new password must have at least 8 characters.", "error")
                return render_template("auth/account.html", user=user)
            if avatar and avatar.filename:
                error = save_avatar(user, avatar)
                if error:
                    db.session.rollback()
                    flash(error, "error")
                    return render_template("auth/account.html", user=user)
            user.email = email
            if password:
                user.set_password(password, "secure")
            db.session.commit()
            audit(actions.PROFILE_UPDATED, actor=user, shop_id=user.shop_id,
                  target_type="user", target_id=user.id, success=True,
                  detail="avatar changed" if avatar and avatar.filename else "profile updated")
            flash("Account updated.", "success")
    return render_template("auth/account.html", user=user)


@bp.route("/account/avatar/remove", methods=["POST"])
@login_required
def remove_avatar():
    user = current_user()
    delete_avatar(user)
    db.session.commit()
    audit(actions.PROFILE_UPDATED, actor=user, shop_id=user.shop_id,
          target_type="user", target_id=user.id, success=True, detail="avatar removed")
    flash("Profile picture removed.", "success")
    return redirect(url_for("auth.account"))


@bp.route("/avatar/<filename>")
def avatar(filename):
    # Only names we generated ({uuid hex}.png) are ever served.
    if not re.fullmatch(r"[0-9a-f]{32}\.png", filename):
        abort(404)
    response = send_from_directory(current_app.config["UPLOADED_AVATARS_DEST"], filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def two_factor_setup():
    # Enrollment. GET generates a not-yet-activated secret + shows the QR.
    # POST confirms the user can produce a valid code, and only THEN flips
    # twofa_enabled on - so a mis-scanned QR can't lock someone out.
    user = current_user()
    if user.twofa_enabled:
        flash("Two-factor authentication is already enabled.", "notice")
        return redirect(url_for("auth.account"))

    if request.method == "POST":
        code = request.form.get("code", "")
        if twofa.verify_code(user, code):
            user.twofa_enabled = True
            db.session.commit()
            audit(actions.TWOFA_SUCCESS, actor=user, shop_id=user.shop_id,
                  target_type="user", target_id=user.id, success=True, detail="2FA enabled")
            flash("Two-factor authentication is now enabled.", "success")
            return redirect(url_for("auth.account"))
        flash("That code didn't match - try again.", "error")
    else:
        user.twofa_secret = twofa.generate_secret()
        db.session.commit()

    return render_template("auth/two_factor_setup.html",
                           qr=twofa.qr_data_uri(user), secret=user.twofa_secret)


@bp.route("/2fa/disable", methods=["POST"])
@login_required
def two_factor_disable():
    user = current_user()
    user.twofa_enabled = False
    user.twofa_secret = None
    db.session.commit()
    audit(actions.TWOFA_SUCCESS, actor=user, shop_id=user.shop_id,
          target_type="user", target_id=user.id, success=True, detail="2FA disabled")
    flash("Two-factor authentication has been disabled.", "success")
    return redirect(url_for("auth.account"))
