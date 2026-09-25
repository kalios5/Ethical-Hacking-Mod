from flask import Blueprint

bp = Blueprint("storefront", __name__)

from app.storefront import routes