from flask import Blueprint
bp = Blueprint('pluginmanager',__name__, template_folder="templates")
from app.pluginmanager import routes