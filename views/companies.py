from flask import Blueprint, render_template, request
from flask_login import login_required
from models.company import Company

companies_bp = Blueprint("companies", __name__, template_folder="../templates/dashboard/companies")

@companies_bp.route("/", methods=["GET"])
@login_required
def index():
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = 100

    query = Company.query
    if search:
        query = query.filter(Company.company_name.like(f"%{search}%"))

    pagination = query.order_by(Company.id.desc()).paginate(page=page, per_page=per_page)
    
    return render_template(
        "dashboard/companies/index.html",
        companies=pagination.items,
        pagination=pagination
    )