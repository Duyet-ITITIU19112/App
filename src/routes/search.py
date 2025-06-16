from flask import Blueprint, session, current_app, request, jsonify
from src.models.user_model import User
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.elastic_service import search_bm25

search_bp = Blueprint("search", __name__, url_prefix="/files")

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
