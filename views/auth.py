# views/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from models import db
from models.user import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("scraping.index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        user = db.session.query(User).filter_by(email=email).first()
        if not user or not user.verify_password(password):
            flash("メールまたはパスワードが正しくありません")
            return redirect(url_for("auth.login"))

        login_user(user)
        next_url = request.args.get("next")
        return redirect(next_url or url_for("scraping.index"))

    return render_template("auth/login.html")

@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("auth.login"))