from models import db

class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255))
    company_site = db.Column(db.String(512), unique=True, index=True)
    inquiry_url = db.Column(db.String(512))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<Company {self.company_name or ''} {self.company_site or ''}>"
