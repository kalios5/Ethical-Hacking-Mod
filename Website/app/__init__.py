from flask import Flask

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'dev-key-for-now'

    from .main.routes import main
    from .auth.routes import auth

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix='/auth')

    return app