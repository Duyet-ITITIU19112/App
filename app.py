import os
from src.routes.main import main_bp
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template
from flask_session import Session
from src.models import db
from src.config.dev_config import DevConfig
from src.services.elastic_service import create_index_if_not_exists
from src.routes.auth import auth_bp
from src.routes.search import search_bp
from src.routes.picker import picker_bp


# ✅ Load .env variables before any config is read

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevConfig)
    # 🔍 Print relevant loaded config values for debugging
    app.logger.info("📦 Loaded config:")
    for key in ["FLASK_ENV", "FLASK_APP", "SECRET_KEY", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI", "DATABASE_URL",
                "ELASTICSEARCH_URL"]:
        value = app.config.get(key)
        masked = "<hidden>" if "SECRET" in key else value
        app.logger.info(f"    {key} = {masked}")

    app.config["SESSION_TYPE"] = "filesystem"
    Session(app)

    db.init_app(app)

    with app.app_context():
        from src.models import user_model, document_model
        db.create_all()
        create_index_if_not_exists()

        app.register_blueprint(auth_bp)
        app.register_blueprint(picker_bp)
        app.register_blueprint(main_bp)
        app.register_blueprint(search_bp)

        app.logger.info("🔧 Application initialized with config: %s", app.config)



    @app.route("/")
    def index():
        return render_template("index.html")

    return app

if __name__ == "__main__":
    create_app().run(host="localhost", port=5000, debug=True, threaded=True)
