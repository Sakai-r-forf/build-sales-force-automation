from app import app
from models import db
from models.company import Company

with app.app_context():
    db.create_all()
    print("Company table created or already exists.")