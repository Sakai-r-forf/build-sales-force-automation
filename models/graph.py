from models.company import Company
from sqlalchemy import func
from models import db

class GraphData:

    @staticmethod
    def email_distribution():
        total = db.session.query(func.count(Company.id)).scalar()
        email_yes = db.session.query(func.count(Company.id)).filter(
            Company.email.isnot(None),
            Company.email != ""
        ).scalar()
        return {
            "labels": ["Emailあり", "Emailなし"],
            "data": [email_yes, total - email_yes]
        }

    @staticmethod
    def inquiry_distribution():
        total = db.session.query(func.count(Company.id)).scalar()
        inquiry_yes = db.session.query(func.count(Company.id)).filter(
            Company.inquiry_url.isnot(None),
            Company.inquiry_url != ""
        ).scalar()
        return {
            "labels": ["問い合わせURLあり", "問い合わせURLなし"],
            "data": [inquiry_yes, total - inquiry_yes]
        }

    @staticmethod
    def phone_distribution():
        total = db.session.query(func.count(Company.id)).scalar()
        phone_yes = db.session.query(func.count(Company.id)).filter(
            Company.phone.isnot(None),
            Company.phone != ""
        ).scalar()
        return {
            "labels": ["電話あり", "電話なし"],
            "data": [phone_yes, total - phone_yes]
        }

    @staticmethod
    def daily_scrape_counts():
        rows = db.session.query(
            func.date(Company.created_at),
            func.count(Company.id)
        ).group_by(func.date(Company.created_at)).all()

        labels = [str(r[0]) for r in rows]
        data = [r[1] for r in rows]

        return {"labels": labels, "data": data}
