from flask import Blueprint, render_template, session, current_app
from flask_login import login_required, current_user
from src.controllers.ingest_controller import start_user_ingestion_async
from src.models.document_model import Document

files_bp = Blueprint("files", __name__, url_prefix="/files")

@files_bp.route("/browse")
@login_required
def browse():
    # enqueue a sync exactly once per session
    if not session.get("sync_started"):
        current_app.logger.info(f"▶️ Starting user sync on first /browse load for user {current_user.id}")
        start_user_ingestion_async(current_user)
        session["sync_started"] = True

    # now load whatever documents you already have indexed
    docs = Document.query.filter_by(user_id=current_user.id).all()
    return render_template("files/browse.html", documents=docs)
