import threading
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
run_once_lock = threading.Lock()
if backend == 'YTM':
    import MA_Scraper.YTMAPI.ytmusicapi as ytmusic
    ytm = ytmusic.YTMusic('browser.json')
else:
    ytm = None

def create_app(test_config=None):
    app = Flask(__name__)

    # Load the config
    app.config['SECRET_KEY'] = load_config('Secret_Key')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['YT_API_KEY'] = load_config('yt_api_key')

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @app.before_request
    def create_database():
        with run_once_lock:
            inspector = inspect(engine)
            if not inspector.has_table('user'): 
                Base.metadata.create_all(engine)
                print("Database tables created.")
    
    @app.teardown_appcontext
    def cleanup(resp_or_exc):
        Session.remove()

    @login_manager.user_loader
    def load_user(user_id):
        return Session.get(User, int(user_id))

    from MA_Scraper.app.routes import main as main
    app.register_blueprint(main)

    from MA_Scraper.app.auth import auth as auth
    app.register_blueprint(auth)

    from MA_Scraper.app.extension import extension as extension
    app.register_blueprint(extension)

    return app