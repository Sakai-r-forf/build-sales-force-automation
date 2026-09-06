from urllib.parse import urlsplit
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import UserMixin, login_user, logout_user, current_user
from werkzeug.security import check_password_hash
from services.store import store

auth_bp = Blueprint("auth", __name__)


class Account(UserMixin):
    def __init__(self, data):
        self.id = data["id"]
        self.email = data["email"]


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("scraping.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = store().read()["users"].get(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("メールまたはパスワードが正しくありません")
            return redirect(url_for("auth.login"))
        session.clear()
        login_user(Account(user))
        next_url = request.args.get("next", "")
        parts = urlsplit(next_url)
        if not next_url.startswith("/") or next_url.startswith("//") or parts.netloc or parts.scheme or "\\" in next_url:
            next_url = url_for("scraping.index")
        return redirect(next_url)
    return render_template("auth/login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
