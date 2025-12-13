from app import app
from models import db
from models.user import User

email = "abe@build-build.co.jp"
password = "buildpassword1201"

with app.app_context():

    existing = User.query.filter_by(email=email).first()
    if existing:
        print(f"User already exists: {email}")
    else:
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {email}")
