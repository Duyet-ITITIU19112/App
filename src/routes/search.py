from flask import Blueprint, session, current_app, request, jsonify, redirect, url_for, render_template
from src.models.user_model import User
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.elastic_service import search_bm25

search_bp = Blueprint("files", __name__, url_prefix="/files")


def get_graph_service_for_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = User.query.get(user_id)
    if not user:
        return None
    return MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires.timestamp() if user.token_expires else 0
    )


@search_bp.route("/test")
def test_graph():
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401

    user = User.query.get(user_id)
    if not user:
        return "User not found", 404

    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires.timestamp() if user.token_expires else 0
    )

    try:
        files = svc.list_root_files()
    except OneDriveServiceError as e:
        try:
            svc._ensure_token()
            files = svc.list_root_files()
        except Exception as e2:
            current_app.logger.error(f"Graph error: {e2}")
            return f"Error listing files: {e2}", 500

    names = [f.get("name") for f in files]
    return jsonify(files=names)

@search_bp.route("/search")
def search_files():
    user_id = session.get("user_id")
    if not user_id:
        return "Not logged in", 401

    query = request.args.get("q", "")
    if not query:
        return {"error": "Missing query parameter 'q'"}, 400

    results = search_bm25(query=query, user_id=user_id, top_k=100)
    return jsonify(results=results)

@search_bp.route("/browse")
def browse():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if not user:
        return redirect(url_for("auth.login"))

    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires.timestamp() if user.token_expires else 0
    )

    query = request.args.get("q")
    folder_id = request.args.get("folder_id")

    if query:
        from src.controllers.search_controller import run_search
        items = run_search(query=query, user_id=user_id)
    else:
        try:
            items = svc.list_children(folder_id) if folder_id else svc.list_root_files()
        except OneDriveServiceError as e:
            current_app.logger.error("OneDrive list error: %s", e)
            items = []

    return render_template("onedrive_browser.html", items=items, folder_id=folder_id)

@search_bp.route("/pick", methods=["POST"])
def pick_file():
    item_id = request.form.get("item_id")
    if not item_id:
        return {"error": "Missing item_id"}, 400

    # Return the selected item ID (and optionally download link or metadata)
    return jsonify(item_id=item_id)

@search_bp.route("/preview/<item_id>")
def preview_file(item_id):
    svc = get_graph_service_for_user()
    if not svc:
        return redirect(url_for("auth.login"))
    try:
        preview_url = svc.get_embed_link(item_id)
    except OneDriveServiceError as e:
        current_app.logger.error("Preview failed", exc_info=True)
        return f"Cannot preview this file: {e}", 500
    return render_template("preview.html", preview_url=preview_url)

@search_bp.route("/preview-url/<item_id>")
def get_preview_url(item_id):
    svc = get_graph_service_for_user()
    if not svc:
        return {"error": "Not logged in"}, 401
    try:
        preview_url = svc.get_embed_link(item_id)
        return {"preview_url": preview_url}
    except OneDriveServiceError as e:
        return {"error": str(e)}, 500





