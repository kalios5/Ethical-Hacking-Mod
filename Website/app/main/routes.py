from flask import Blueprint

main = Blueprint('main', __name__)
@main.route('/')
def index():
    return "<h1>Main Website</h1><p>The site is running! Go to <a href='/auth/login'>Login</a></p>"