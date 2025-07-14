# src/routes/notifications.py

from flask import Blueprint, request, current_app
from src.controllers.ingest_controller import start_user_ingestion_async
from src.models.user_model import User

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@notifications_bp.route("", methods=["POST"])
def handle_notifications():
    data = request.get_json()

    # 1) Microsoft Graph validation challenge
    if "validationToken" in data:
        return data["validationToken"], 200

    # 2) Process change notifications
    for change in data.get("value", []):
        # verify the subscription
        user = User.query.filter_by(subscription_id=change["subscriptionId"]).first()
        if not user or str(user.id) != change.get("clientState"):
            current_app.logger.warning("Ignoring invalid notification")
            continue

        current_app.logger.info(f"▶️ Notified of change for user {user.id}; enqueuing delta-sync")
        start_user_ingestion_async(user.id)

    return "", 202
