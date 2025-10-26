from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

def init_db(app):
    app.config.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///app.db")
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)
    return db