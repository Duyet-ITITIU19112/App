from datetime import datetime
from enum import Enum
from flask_login import UserMixin
from sqlalchemy import Enum as SqlEnum
from src.models import db
from src.models.subscription_model import Subscription

class SyncStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"

class User(db.Model, UserMixin):      # ← add UserMixin here
    __tablename__ = "users"

    id               = db.Column(db.Integer, primary_key=True)
    ms_id            = db.Column(db.String(64), unique=True, nullable=False)
    name             = db.Column(db.String(120))
    email            = db.Column(db.String(120), unique=True, nullable=False)
    access_token     = db.Column(db.Text, nullable=False)
    refresh_token    = db.Column(db.Text, nullable=True)
    token_expires    = db.Column(db.DateTime, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    delta_link       = db.Column(db.String, nullable=True)

    subscriptions = db.relationship("Subscription", back_populates="user")

    # sync tracking
    sync_status      = db.Column(SqlEnum(SyncStatus), default=SyncStatus.IDLE)
    sync_updated_at  = db.Column(db.DateTime)

    def __repr__(self):
        return f"<User {self.email}>"

    @property
    def token_expired(self) -> bool:
        if not self.token_expires:
            return True
        return datetime.utcnow() >= self.token_expires
