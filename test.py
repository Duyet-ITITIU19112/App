import os
import logging
from flask import Flask
from flask_session import Session
from src.models import db
from src.config.dev_config import DevConfig
from src.services.elastic_service import create_index_if_not_exists
from src.routes.auth import auth_bp
from src.routes.search import search_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(DevConfig)

    # Enable server-side sessions
    app.config.setdefault("SESSION_TYPE", "filesystem")
    Session(app)

    # Setup SQLAlchemy
    db.init_app(app)

    # Setup logging
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)
    app.logger.debug("Logging initialized")

    # Provide information about env/proxies
    app.logger.debug(f"MS_REDIRECT_URI = {os.getenv('MS_REDIRECT_URI')}")
    app.logger.debug(f"HTTP_PROXY = {os.getenv('HTTP_PROXY')}")
    app.logger.debug(f"HTTPS_PROXY = {os.getenv('HTTPS_PROXY')}")

    app.register_blueprint(auth_bp)
    app.register_blueprint(search_bp)

    return app

def main():
    app = create_app()
    with app.app_context():
        # Initialize DB & ES
        db.create_all()
        create_index_if_not_exists()
        app.logger.info("✅ Database and Elasticsearch initialized")

    # Run app with SSL debugging enabled
    os.environ["PYTHONHTTPSVERIFY"] = "1"  # enforce certificate verification
    logging.debug("Starting Flask dev server…")
    app.run(host="localhost", port=5000, debug=True)

if __name__ == "__main__":
    main()
