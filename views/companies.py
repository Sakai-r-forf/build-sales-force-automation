from flask import Blueprint, render_template
from flask_login import login_required

companies_bp = Blueprint("companies", __name__)

@companies_bp.get("/")
@login_required
def index():
    return render_template("dashboard/companies/index.html")