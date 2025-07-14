# routes/sync.py

from flask import Blueprint, session, jsonify
from src.models.user_model import User
from src.models import db

sync_bp = Blueprint("sync", __name__, url_prefix="/api/sync")

@sync_bp.route("/status", methods=["GET"])
def get_sync_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "status": user.sync_status,
        "updated_at": user.sync_updated_at.isoformat() if user.sync_updated_at else None
    })
