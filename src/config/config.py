import os
from dotenv import load_dotenv

load_dotenv()

class BaseConfig:
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    FLASK_APP = os.getenv("FLASK_APP", "app.app")
    SECRET_KEY = os.getenv("SECRET_KEY", "your-dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "s3cur3andRand0m!")

    # PostgreSQL setup
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/your_db")
    DATABASE_URL = SQLALCHEMY_DATABASE_URI  # ✅ optional: for logging/debug visibility
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Elasticsearch setup (plain HTTP, without TLS options)
    ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME")
    ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD")
    ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_INDEX", "test-index")
    # For development over HTTP, drop TLS options like VERIFY_CERTS or CA_CERT_PATH

    # Microsoft OAuth and MSAL settings
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")
    AUTHORITY = os.getenv("AUTHORITY", f"https://login.microsoftonline.com/{MS_TENANT_ID}")
    REDIRECT_PATH = "/auth/"  # ensure your Auth blueprint uses this
    REDIRECT_URI = os.getenv("MS_REDIRECT_URI", f"http://localhost:5000{REDIRECT_PATH}")
    SCOPE = os.getenv("SCOPE", "openid profile offline_access User.Read Files.ReadWrite.All")

    AUTH_REDIRECT_URI = os.getenv("AUTH_REDIRECT_URI", f"http://localhost:5000{os.getenv('REDIRECT_PATH', '/auth/')}")
    # Microsoft Graph change-notification webhook endpoint (for /notifications)
    NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://localhost:5000/notifications")


