
from flask import Blueprint, current_app, request, redirect, url_for, render_template, flash, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from src.controllers.ingest_controller import start_user_ingestion_async
from src.controllers.search_controller import full_search_pipeline
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.elastic_service import ingest_single_onedrive_file

files_bp = Blueprint("files", __name__, url_prefix="/files")


def get_graph_service_for_user() -> MicrosoftGraphService:
    """Returns a Graph client for the logged-in user."""
    user = current_user
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires or 0,
        user_id=user.id
    )
    return svc


@files_bp.route("/")
def index():
    return redirect(url_for("files.browse"))


@files_bp.route("/search")
@login_required
def full_pipeline_search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("files.browse"))
    return redirect(url_for("files.browse", q=q))


@files_bp.route("/browse", methods=["GET", "POST"])
@login_required
def browse():
    user = current_user
    svc = get_graph_service_for_user()

    # 1) Immediate upload & index-on-upload
    if request.method == "POST":
        file = request.files.get("file")
        folder_id = request.form.get("folder_id") or None

        if not file or not file.filename:
            flash("No file selected", "warning")
        else:
            filename = secure_filename(file.filename)
            content = file.read()
            try:
                new_item = svc.upload_file(
                    filename=filename,
                    content=content,
                    parent_folder_id=folder_id
                )
                ingest_single_onedrive_file(user, new_item)
                flash(f"Uploaded & indexed {filename} successfully.", "success")
            except OneDriveServiceError as e:
                current_app.logger.error("Upload failed: %s", e)
                flash(f"Upload failed: {e}", "danger")

    # 2) One-time background delta-sync on first browse after login
    if not session.get("sync_started"):
        current_app.logger.info(f"▶️ Enqueueing background delta-sync for user {user.id}")
        start_user_ingestion_async(user.id)
        session["sync_started"] = True

    # 3) Decide: full-text search or folder listing
    q = request.args.get("q", "").strip()
    folder_id = request.args.get("folder_id")

    if q:
        current_app.logger.info(f"User {user.id} searching for “{q}”")
        items = full_search_pipeline(user_query=q, user_id=user.id)
    else:
        try:
            items = (
                svc.list_children(folder_id)
                if folder_id
                else svc.list_root_files()
            )
        except OneDriveServiceError as e:
            current_app.logger.error("OneDrive list error: %s", e)
            items = []

    return render_template(
        "onedrive_browser.html",
        items=items,
        folder_id=folder_id,
        search_query=q
    )


@files_bp.route("/preview/<item_id>")
@login_required
def preview_file(item_id):
    svc = get_graph_service_for_user()
    svc.ensure_valid_token()

    try:
        meta = svc.get_item(item_id)
        weburl = meta.get("webUrl")
        if not weburl:
            raise OneDriveServiceError("No webUrl available for this item")
        return redirect(weburl)
    except OneDriveServiceError as e:
        current_app.logger.error("Preview/Edit redirect failed: %s", e)
        return redirect(url_for("files.browse"))
