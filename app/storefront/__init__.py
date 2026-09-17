from flask import Blueprint

bp = Blueprint("storefront", __name__, template_folder="templates")

from app.storefront import routes