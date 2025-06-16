from datetime import datetime
from src.models import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    ms_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True, nullable=False)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.email}>"

    @property
    def token_expired(self) -> bool:
        """
        Check if the access token has expired.
        """
        if not self.token_expires:
            return True
        return datetime.utcnow() >= self.token_expires
