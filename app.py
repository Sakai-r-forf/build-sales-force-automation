import json
import os
import secrets
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, request, session, url_for
from flask_login import LoginManager, current_user
from werkzeug.security import generate_password_hash

from services.store import StateStore


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "local-development-only"),
        GCS_BUCKET=os.getenv("GCS_BUCKET", ""),
        STATE_PATH=os.getenv("STATE_PATH", str(Path(app.instance_path) / "state.json")),
        STATE_OBJECT=os.getenv("STATE_OBJECT", "app/state-v1.json"),
        MAX_CONTENT_LENGTH=256 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.getenv("K_SERVICE")),
        ALLOW_LOOPBACK=False,
        CRAWL_TIME_BUDGET=220,
    )
    if config:
        app.config.update(config)
    if os.getenv("K_SERVICE") and (not app.config["GCS_BUCKET"] or app.config["SECRET_KEY"] == "local-development-only"):
        raise RuntimeError("Cloud Run requires GCS_BUCKET and SECRET_KEY.")
    app.extensions["state_store"] = StateStore(app.config["GCS_BUCKET"], app.config["STATE_PATH"], app.config["STATE_OBJECT"])
    users_json = os.getenv("INITIAL_USERS_JSON")
    if users_json:
        users = json.loads(users_json)
        def seed(state):
            for user in users:
                email = user["email"].strip().lower()
                state["users"].setdefault(email, {"id": email, "email": email, "password_hash": user.get("password_hash") or generate_password_hash(user["password"])})
        app.extensions["state_store"].mutate(seed)

    from views.auth import auth_bp, Account
    from views.scraping import scraping_bp
    from views.companies import companies_bp
    from views.graphs import graphs_bp
    from views.faq import faq_bp
    from views.companies_delete import companies_delete_bp
    from views.deliveries import deliveries_bp
    manager = LoginManager(app)
    manager.login_view = "auth.login"

    @manager.user_loader
    def load_user(user_id):
        data = app.extensions["state_store"].read()["users"].get(user_id)
        return Account(data) if data else None

    @manager.unauthorized_handler
    def unauthorized():
        if request.is_json or request.headers.get("X-Requested-With"):
            return jsonify(error="ログインし直してください。"), 401
        return redirect(url_for("auth.login", next=request.path))

    @app.context_processor
    def csrf_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.before_request
    def csrf_check():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
                if request.is_json or request.headers.get("X-Requested-With"):
                    return jsonify(error="画面を再読み込みして操作し直してください。"), 400
                abort(400, description="画面を再読み込みして操作し直してください。")

    app.register_blueprint(auth_bp)
    app.register_blueprint(scraping_bp, url_prefix="/scraping")
    app.register_blueprint(companies_bp, url_prefix="/companies")
    app.register_blueprint(graphs_bp, url_prefix="/graphs")
    app.register_blueprint(faq_bp, url_prefix="/faq")
    app.register_blueprint(companies_delete_bp, url_prefix="/companies_delete")
    app.register_blueprint(deliveries_bp, url_prefix="/deliveries")

    @app.get("/")
    def index():
        return redirect(url_for("companies.index" if current_user.is_authenticated else "auth.login"))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        try:
            app.extensions["state_store"].read()
            return {"status": "ok", "storage": "gcs" if app.config["GCS_BUCKET"] else "local"}
        except Exception:
            app.logger.exception("Persistent storage unavailable")
            return {"status": "unavailable"}, 503

    return app


app = create_app()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "7700")))
