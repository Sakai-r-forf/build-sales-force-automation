# models/seed_users.py
from models import db
from models.user import User

def seed_initial_users():
    users = [
        {
            "email": "testadmin@example.com",
            "password": "testpassword",
        },
        {
            "email": "abe@build-build.co.jp",
            "password": "buildpassword1201",
        },
    ]

    for u in users:
        exists = User.query.filter_by(email=u["email"]).first()
        if exists:
            continue

        user = User(email=u["email"])
        user.set_password(u["password"])
        db.session.add(user)

    db.session.commit()
