"""
app/admin/dbconsole.py  -  admin-only database console (Flask-Admin).

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

LOOK AND FEEL
-------------
/admin/db redirects to the Users table; the tab row switches between tables.
Pages render inside the site's own base.html (templates/dbconsole/
base.html is the Flask-Admin theme shell), so the topbar, flash notices and
footer match the rest of the site; DB-console specific CSS lives at the end of
static/site.css under ".dbconsole".

EXPORT
------
Every table can be exported (csv/json) from the list toolbar - that exports
the current search/filter result - or via the "Export selected (CSV)" batch
action, which exports only the ticked rows. Every export is written to the
audit log (DB_EXPORT). Exports contain whatever columns the list shows, so the
Users export includes password_hash/hash_mode, consistent with the console.
"""

import csv
import io
from datetime import datetime

from flask import Response, redirect, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.actions import action
from flask_admin.contrib.sqla import ModelView, tools
from flask_admin.theme import BootstrapTheme
from werkzeug.utils import secure_filename

from app import db
from app.auth.routes import current_user as _current_user
from app.logging.db_audit import actions, audit
from app.Database.models import (
    AuditLog, CartItem, DbChangeLog, Order, OrderItem, Plugin, Product, Shop, User,
)


def _is_admin():
    user = _current_user()
    return user is not None and user.role in ("admin", "superadmin")


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _neutralise(value):
    """Stop spreadsheet formula injection: a stored string such as
    '=HYPERLINK(...)' would run when an export is opened in Excel/Sheets."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


class GatedModelView(ModelView):
    """A ModelView only admins/superadmins may open. Full CRUD is enabled."""
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    column_display_pk = True
    export_types = ["csv", "json"]
    export_max_rows = 10000
    page_size = 50

    def get_export_value(self, model, name):
        return _neutralise(super().get_export_value(model, name))

    @expose("/export/<export_type>/")
    def export(self, export_type):
        if export_type in self.export_types:
            audit(actions.DB_EXPORT, actor=_current_user(), target_type=self.model.__tablename__,
                  detail=f"list export ({export_type}), max_rows={self.export_max_rows}")
        return super().export(export_type)

    @action("export_selected", "Export selected (CSV)")
    def action_export_selected(self, ids):
        rows = tools.get_query_for_ids(self.get_query(), self.model, ids).limit(self.export_max_rows).all()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([label for _name, label in self._export_columns])
        for row in rows:
            writer.writerow([self.get_export_value(row, name) for name, _label in self._export_columns])
        table = self.model.__tablename__
        audit(actions.DB_EXPORT, actor=_current_user(), target_type=table,
              detail=f"selected export (csv), {len(rows)} rows, ids={list(ids)[:50]}")
        filename = secure_filename(f"{table}-selected-{datetime.utcnow():%Y%m%d-%H%M%S}.csv")
        return Response(
            out.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={filename}"},
        )

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


DEFAULT_VIEW = "dbconsole_users.index_view"


class GatedAdminIndex(AdminIndexView):
    def is_visible(self):
        return False  # keep "Home" out of the model tab row

    def is_accessible(self):
        return _is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login"))

    @expose("/")
    def index(self):
        if not _is_admin():
            return redirect(url_for("auth.login"))
        audit(actions.DB_CONSOLE_ACCESS, actor=_current_user(), detail="opened DB console")
        # No landing page: open the default model (Users); the tab row in the
        # layout switches between the others.
        return redirect(url_for(DEFAULT_VIEW))


def init_db_console(app):
    """Attach the Flask-Admin DB console to an existing Flask app."""
    admin = Admin(
        app,
        name="DB Console",
        url="/admin/db",
        endpoint="dbconsole",
        index_view=GatedAdminIndex(url="/admin/db", endpoint="dbconsole"),
        theme=BootstrapTheme(folder="bootstrap4", base_template="dbconsole/base.html"),
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
