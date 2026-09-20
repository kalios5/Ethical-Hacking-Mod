from functools import wraps

from flask import flash, redirect, render_template, request, session, url_for

from app import db
from app.auth import bp
from app.Database.auth import authenticate
from app.Database.models import User


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
        user = authenticate(username, password, ip=request.remote_addr)
        if user:
            session.clear()
            session["user_id"] = user.id
            flash(f"Welcome back, {user.username}.", "success")
            target = request.args.get("next") or url_for("storefront.index")
            return redirect(target if target.startswith("/") else url_for("storefront.index"))
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