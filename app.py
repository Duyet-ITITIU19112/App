import tempfile

from src.routes.search import files_bp

tempfile.tempdir = None
from flask import Flask, render_template
from flask_session import Session
from dotenv import load_dotenv
from flask_login import LoginManager
from src.models import db
from src.config.dev_config import DevConfig
from src.routes.auth import auth_bp
from src.cli.commands import backfill_hashes
from src.models.user_model import User

load_dotenv()

login_manager = LoginManager()
login_manager.login_view = "auth.login"  # name of your login endpoint

def register_blueprints(app):
    """Attach all route blueprints."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.cli.add_command(backfill_hashes)

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevConfig)

    app.config["SESSION_TYPE"] = "filesystem"
    Session(app)

    #Initialize DB and LoginManager
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Flask-Login uses this to reload the user from the session
        return User.query.get(int(user_id))

    @app.route("/")
    def index():
        return render_template("index.html")

    with app.app_context():
        db.create_all()
        register_blueprints(app)

    return app

if __name__ == "__main__":
    create_app().run(host="localhost", port=5000, debug=True, threaded=True, use_reloader=True)
