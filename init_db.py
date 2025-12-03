from app import app
from models import db
from models.user import User
from models.company import Company

print("Starting DB initialization...")

with app.app_context():
    db.create_all()

print("DB tables created successfully!")