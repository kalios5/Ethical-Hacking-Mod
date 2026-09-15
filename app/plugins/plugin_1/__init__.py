from flask import Blueprint

# A blueprint lets this plugin add its own routes under /plugin1
bp = Blueprint("plugin1", __name__, url_prefix="/plugin1")


@bp.route("/")
def index():
    return "Hello from plugin 1!"


def register(app):
    """Called once at startup. Do whatever the plugin needs here."""
    app.register_blueprint(bp)
    app.logger.info("plugin1 ran its startup code")