from datetime import datetime
from src.models import db

class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_id = db.Column(db.String(128), unique=True, nullable=False)
    source = db.Column(db.String(20))  # e.g. "onedrive"
    content_hash = db.Column(db.String(64))  # SHA256 or similar
    indexed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime)
    size = db.Column(db.BigInteger)
    web_url = db.Column(db.String(1024))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)