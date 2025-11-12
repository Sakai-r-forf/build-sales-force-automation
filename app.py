import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from models import init_db, db
from models.user import User
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