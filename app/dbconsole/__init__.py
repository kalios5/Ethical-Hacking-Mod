"""
app/dbconsole/  -  admin-only database console (Flask-Admin).

A single read/write/edit/delete web UI over every table in the app, mounted
at /admin/db. This is the "DB Console Access" node in the attack-flow
diagram: an admin can browse and edit rows directly, INCLUDING the users
table with each account's username, email, password_hash and hash_mode -
which is the data an attacker dumps and then cracks (weak/md5 hashes).

Uses Flask-Admin (already in requirements.txt). Mounted at /admin/db so it
does NOT collide with the existing hand-written /admin blueprint.

ACCESS CONTROL
--------------
Every view is gated by GatedModelView.is_accessible(), which reuses the
same session-based check as app/admin/routes.py::admin_required
(current_user().role in {"admin","superadmin"}). How strong that gate
actually is - i.e. whether the "broken access control -> IDOR into admin
console" path on the diagram can reach it - is the intended lab
vulnerability, documented in R1, and lives in the auth layer, not here.
"""

from flask import redirect, session, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView

from app import db
from app.Database.models import (
    AuditLog, CartItem, DbChangeLog, Order, OrderItem, Plugin, Product, Shop, User,
)


def _current_user():
    # Local copy of app.auth.routes.current_user to avoid an import cycle at
    # module load (auth.routes imports from other blueprints too).
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def _is_admin():
    user = _current_user()
    return user is not None and user.role in ("admin", "superadmin")


class GatedModelView(ModelView):
    """A ModelView only admins/superadmins may open. Full CRUD is enabled."""
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 50

    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login"))


class UserAdmin(GatedModelView):
    """Users table - deliberately shows the credential columns so an admin
    (and, via the intended broken-access path, an attacker) can read every
    account's hash and hashing mode straight out of the console."""
    column_list = ("id", "shop_id", "username", "email",
                   "password_hash", "hash_mode", "role", "is_active",
                   "failed_logins", "last_login", "created_at")
    column_searchable_list = ("username", "email", "role")
    column_filters = ("role", "hash_mode", "is_active", "shop_id")
    column_labels = {"password_hash": "Password Hash", "hash_mode": "Hash Mode"}


class GatedAdminIndex(AdminIndexView):
    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login"))

    @expose("/")
    def index(self):
        if not _is_admin():
            return redirect(url_for("auth.login"))
        return super().index()


def init_db_console(app):
    """Attach the Flask-Admin DB console to an existing Flask app."""
    admin = Admin(
        app,
        name="DB Console",
        url="/admin/db",
        endpoint="dbconsole",
        index_view=GatedAdminIndex(url="/admin/db", endpoint="dbconsole"),
    )
    admin.add_view(UserAdmin(User, db, name="Users", endpoint="dbconsole_users"))
    admin.add_view(GatedModelView(Shop, db, name="Shops", endpoint="dbconsole_shops"))
    admin.add_view(GatedModelView(Product, db, name="Products", endpoint="dbconsole_products"))
    admin.add_view(GatedModelView(Order, db, name="Orders", endpoint="dbconsole_orders"))
    admin.add_view(GatedModelView(OrderItem, db, name="Order Items", endpoint="dbconsole_orderitems"))
    admin.add_view(GatedModelView(CartItem, db, name="Cart Items", endpoint="dbconsole_cartitems"))
    admin.add_view(GatedModelView(Plugin, db, name="Plugins", endpoint="dbconsole_plugins"))
    admin.add_view(GatedModelView(AuditLog, db, name="Audit Log", endpoint="dbconsole_audit"))
    admin.add_view(GatedModelView(DbChangeLog, db, name="DB Change Log", endpoint="dbconsole_dbchange"))
    return admin
