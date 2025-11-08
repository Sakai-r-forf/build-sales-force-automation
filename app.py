# app.py
import os
from flask import Flask
from flask_login import LoginManager
from models import init_db, db
from models.user import User
from views.auth import auth_bp
from views.scraping import scraping_bp
from views.companies import companies_bp
from views.graphs import graphs_bp
from views.faq import faq_bp

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "CHANGE_ME")
app.config.setdefault("SQLALCHEMY_DATABASE_URI", os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///app.db"))

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7700, debug=True)