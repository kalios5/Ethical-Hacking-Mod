from flask import Flask

from pluginmanager.models import db
from pluginmanager.routes import pluginmanager_bp


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
    app.config["SECRET_KEY"] = "dev-secret-key-change-later"

    db.init_app(app)
    app.register_blueprint(pluginmanager_bp)

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
