# src/models/subscription_model.py

from datetime import datetime
from src.models import db

class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id            = db.Column(db.Integer, primary_key=True)
    sub_id        = db.Column(db.String(128), unique=True, nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    client_state  = db.Column(db.String(64), nullable=False)
    expires_at    = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", back_populates="subscriptions")
