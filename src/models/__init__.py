from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

# Re-export models here
from .user_model import User
from .document_model import Document  # if you have this
