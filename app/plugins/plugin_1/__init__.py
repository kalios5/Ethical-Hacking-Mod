from flask import Blueprint

# A blueprint lets this plugin add its own routes under /plugin1
bp = Blueprint("website", __name__)


@bp.route("/")
def index():
    return "<h1>Main Website</h1><p>The site is running! Go to <a href='/auth/login'>Login</a></p>"


@bp.route("/auth/login")
def login():
    return "<h1>Login Page</h1><p>Your user management will go here.</p>"


def register(app):
    """Called once at startup. Do whatever the plugin needs here."""
    app.register_blueprint(bp)
    app.logger.info("plugin1 ran its startup code")