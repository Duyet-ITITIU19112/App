from flask import Blueprint, session, redirect, url_for, render_template

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    return render_template("index.html")
