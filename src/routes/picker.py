from flask import Blueprint, session, redirect, url_for, current_app, render_template

picker_bp = Blueprint("picker", __name__, url_prefix="/picker")

@picker_bp.route("/")
def picker():
    try:
        user_id = session.get("user_id")
        current_app.logger.debug("Picker route session user_id=%r", user_id)

        if not user_id:
            return redirect(url_for("auth.login"))

        return render_template(
            "onedrive_picker.html",
            client_id=current_app.config["CLIENT_ID"],
            redirect_uri=current_app.config["REDIRECT_URI"]
        )
    except Exception as e:
        current_app.logger.error("❗ Exception in picker route: %s", e, exc_info=True)
        return f"Internal Picker Error: {e}", 500
