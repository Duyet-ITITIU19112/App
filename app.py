# app.py
import os
from flask import Flask, render_template
from flask_session import Session
from src.models import db
from src.config.dev_config import DevConfig
from src.services.elastic_service import create_index_if_not_exists
from src.routes.auth import auth_bp
from src.routes.search import search_bp
from src.routes.picker import picker_bp
from src.routes.main import main_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevConfig)
    app.config.setdefault("SESSION_TYPE", "filesystem")
    Session(app)

    db.init_app(app)
    with app.app_context():
        from src.models import user_model, document_model
        db.create_all()
        create_index_if_not_exists()
        app.register_blueprint(auth_bp)
        app.register_blueprint(search_bp)
        app.register_blueprint(picker_bp)
        app.register_blueprint(main_bp)

        @app.route("/")
        def index():
            return render_template("index.html")

    return app

if __name__ == "__main__":
    create_app().run(host="localhost", port=5000, debug=True)
