from flask import Flask
from flask_login import LoginManager
from MA_Scraper.Env import load_config, Env
from sqlalchemy import inspect
from MA_Scraper.app.db import Session, engine
from MA_Scraper.app.CacheManager import CacheManager
from MA_Scraper.models import Base, User

website_name = 'Amplifier Worship'
backend = Env.get_instance().ytbackend

login_manager = LoginManager()
cache_manager = CacheManager()

if not inspect(engine).has_table('user'): 
    Base.metadata.create_all(engine)

def create_app(test_config=None):
    app = Flask(__name__)

    app.config['SECRET_KEY'] = load_config('Secret_Key')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @app.teardown_appcontext
    def cleanup(resp_or_exc):
        Session.remove()

    @login_manager.user_loader
    def load_user(user_id):
        return Session.get(User, int(user_id))

    from MA_Scraper.app.routes import main
    app.register_blueprint(main)

    from MA_Scraper.app.auth import auth
    app.register_blueprint(auth)

    from MA_Scraper.app.extension import extension
    app.register_blueprint(extension)

    return app