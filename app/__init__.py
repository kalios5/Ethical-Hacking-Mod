from flask import Flask
from config import *
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from elasticsearch import Elasticsearch
from sqlalchemy import create_engine
from flask_restx import Api
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
api = Api()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app,db)
    login.init_app(app)
    api.init_app(app)

    login.login_view = 'main.login'

    from app.main import bp as main_bp
    app.register_blueprint(main_bp,url_prefix='/main')

    return app

