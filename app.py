import os
import json
import uuid
from datetime import datetime, timezone

from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user

from google.cloud import storage

from models import init_db, db
from models.user import User
from models.seed_users import seed_initial_users

from views.auth import auth_bp
from views.scraping import scraping_bp
from views.companies import companies_bp
from views.graphs import graphs_bp
from views.faq import faq_bp

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "CHANGE_ME")
app.config.setdefault(
    "SQLALCHEMY_DATABASE_URI",
    os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///app.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

init_db(app)

from models.seed_users import seed_initial_users
with app.app_context():
    seed_initial_users()

# =========================
# Cloud Storage 永続保存
# =========================
BUCKET_NAME = os.getenv("GCS_BUCKET", "build-scraping-bucket")

_storage_client = None  # ★遅延初期化（ローカル起動で落ちにくくする）

def get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client

def save_to_gcs_json(data: dict, prefix: str = "companies") -> str:
    """
    data: 保存したいdict（スクレイプ結果1件でも、まとめでもOK）
    prefix: 保存先の論理フォルダ名
    return: GCSのオブジェクトパス（例 companies/20251213/170945-xxxx.json）
    """
    client = get_storage_client()
    bucket = client.bucket(BUCKET_NAME)

    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")

    object_name = f"{prefix}/{date_part}/{time_part}-{uuid.uuid4().hex}.json"

    blob = bucket.blob(object_name)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )

    return object_name


# =========================
# Login / Blueprints
# =========================
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))

app.register_blueprint(auth_bp)
app.register_blueprint(scraping_bp, url_prefix="/scraping")
app.register_blueprint(companies_bp, url_prefix="/companies")
app.register_blueprint(graphs_bp, url_prefix="/graphs")
app.register_blueprint(faq_bp, url_prefix="/faq")
app.register_blueprint(companies_delete_bp, url_prefix="/companies_delete")

@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("companies.index"))

@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("companies.index"))

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7700))
    app.run(host="0.0.0.0", port=port, debug=True)