from flask import Flask
from app.config import *
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
#from flask_login import LoginManager
db = SQLAlchemy()
migrate = Migrate()
#login = LoginManager()

def create_app(config_class=ProductionConfig):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app,db)
    #login.init_app(app)

    #login.login_view = 'main.login'

    from app.main import bp as main_bp
    app.register_blueprint(main_bp,url_prefix='/')
    from app import models
    
    return app

