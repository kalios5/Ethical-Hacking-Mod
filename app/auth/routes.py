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
from app.pluginmanager.security_plugins import login_captcha
from app.auth import twofa
from app.uploads import delete_avatar, save_avatar


def _feature_enabled(name):
    toggle = Plugin.query.filter_by(name=name).first()
    return toggle.enabled if toggle else True


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def _is_safe_redirect_target(target):
    """True only for a same-site absolute path like '/cart'. Rejects absolute
    URLs ('http://evil'), protocol-relative ('//evil'), and backslash tricks
    ('/\\evil', which browsers treat as protocol-relative) - all open-redirect
    vectors a bare target.startswith('/') check lets through."""
    if not target or not target.startswith("/"):
        return False
    if target.startswith("//") or target.startswith("/\\"):
        return False
    from urllib.parse import urlparse
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "notice")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _render_login(captcha_enabled, ip):
    """Render the login page, attaching a fresh CAPTCHA challenge only when the
    feature is on AND this IP has failed enough to be armed. Otherwise the
    template shows no challenge and the login form is unchanged."""
    if captcha_enabled and login_captcha.is_required(ip):
        token, question = login_captcha.new_challenge()
        return render_template("auth/login.html", captcha_token=token, captcha_question=question)
    return render_template("auth/login.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip = request.remote_addr

        ip_limit_enabled = _feature_enabled("ip_rate_limit")
        if ip_limit_enabled and ip_limiter.is_ip_blocked(ip):
            remaining = ip_limiter.seconds_until_reset(ip)
            audit(actions.ACCESS_DENIED, ip=ip, success=False,
                  detail=f"IP rate limit, {remaining}s remaining")
            flash(f"Too many login attempts from this network. Try again in {remaining} seconds.", "error")
            return render_template("auth/login.html")

        # Login CAPTCHA (see pluginmanager/security_plugins/login_captcha/).
        # Arms only after repeated failures from this IP, so a normal login is
        # untouched. A wrong/missing answer stops the attempt before auth.
        captcha_enabled = _feature_enabled("login_captcha")
        if captcha_enabled and login_captcha.is_required(ip):
            token = request.form.get("captcha_token", "")
            answer = request.form.get("captcha_answer", "")
            if not login_captcha.verify(token, answer):
                audit(actions.ACCESS_DENIED, ip=ip, success=False,
                      detail="login CAPTCHA failed/missing")
                flash("Please answer the challenge question correctly.", "error")
                return _render_login(captcha_enabled, ip)

        existing_user = User.query.filter_by(username=username).first()

        # Prototype security plugin, statically imported (see
        # pluginmanager/security_plugins/temp_lockout/__init__.py). Only enforced when
        # enabled via /admin/security-settings.
        lockout_enabled = _feature_enabled("temp_lockout") if existing_user else True
        if existing_user and lockout_enabled and is_locked_out(existing_user):
            remaining = seconds_remaining(existing_user)
            audit(actions.ACCESS_DENIED, actor=existing_user, ip=ip,
                  target_type="user",
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
                login_captcha.reset_on_success(ip)
                audit(actions.TWOFA_CHALLENGE, actor=user, ip=ip,
                      target_type="user", target_id=user.id, success=True,
                      detail="password ok, awaiting 2FA")
                return redirect(url_for("auth.two_factor"))

            # session.clear() must run BEFORE any flash() calls for this
            # login - flash() stores messages inside the session, and
            # clear() wipes anything flashed before it runs.
            session.clear()
            session["user_id"] = user.id
            reset_on_success(user)
            login_captcha.reset_on_success(ip)

            new_device_enabled = _feature_enabled("new_device_alert")
            if new_device_enabled and is_new_ip(user, ip, check_time):
                flash("New sign-in detected from an unrecognized location.", "notice")

            flash(f"Welcome back, {user.username}.", "success")
            target = request.args.get("next")
            if not _is_safe_redirect_target(target):
                target = url_for("storefront.index")
            return redirect(target)

        if ip_limit_enabled:
            ip_limiter.record_failed_attempt(ip)
        if captcha_enabled:
            login_captcha.record_failed_attempt(ip)
        if lockout_enabled and existing_user:
            db.session.refresh(existing_user)
            record_failed_attempt(existing_user)
        flash("Invalid username or password.", "error")
        return _render_login(captcha_enabled, ip)
    # GET: if this IP is already armed from earlier failures, show the challenge.
    return _render_login(_feature_enabled("login_captcha"), request.remote_addr)


@bp.route("/logout", methods=["POST"])
def logout():
    # POST-only so a cross-site GET (e.g. <img src=".../auth/logout">) can't
    # force-log-out a user. The nav "Log out" control is a small CSRF-token
    # form (see base.html) rather than a link.
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
            audit(actions.TWOFA_SUCCESS, actor=user, ip=ip,
                  target_type="user", target_id=user.id, success=True, detail="2FA verified, login complete")
            new_device_enabled = _feature_enabled("new_device_alert")
            if new_device_enabled and check_time_raw:
                try:
                    if is_new_ip(user, ip, datetime.fromisoformat(check_time_raw)):
                        flash("New sign-in detected from an unrecognized location.", "notice")
                except ValueError:
                    pass
            flash(f"Welcome back, {user.username}.", "success")
            return redirect(url_for("storefront.index"))

        audit(actions.ACCESS_DENIED, actor=user, ip=session.get("pending_2fa_ip"),
              target_type="user", target_id=user.id,
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
            user = User(username=username, email=email, role="customer", hash_mode="secure")
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
            audit(actions.PROFILE_UPDATED, actor=user,
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
    audit(actions.PROFILE_UPDATED, actor=user,
          target_type="user", target_id=user.id, success=True, detail="avatar removed")
    flash("Profile picture removed.", "success")
    return redirect(url_for("auth.account"))


@bp.route("/avatar/<filename>")
def avatar(filename):
    # Saved files keep their upload extension (see app/uploads.py::save_avatar,
    # AVATAR_EXTENSIONS), not just .png. No "/" is permitted here regardless,
    # so a *read* of this route can't traverse out of UPLOADED_AVATARS_DEST -
    # send_from_directory's own safe_join check runs on top of this either way.
    if not re.fullmatch(r"[\w.-]+\.(?:jpg|jpeg|png|webp)", filename, re.IGNORECASE):
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
            audit(actions.TWOFA_SUCCESS, actor=user,
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
    audit(actions.TWOFA_SUCCESS, actor=user,
          target_type="user", target_id=user.id, success=True, detail="2FA disabled")
    flash("Two-factor authentication has been disabled.", "success")
    return redirect(url_for("auth.account"))
