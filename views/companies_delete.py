from flask import Blueprint, render_template, redirect, url_for, flash
from models.company import Company
from models import db

companies_delete_bp = Blueprint("companies_delete", __name__)

@companies_delete_bp.route("/", methods=["GET"])
def index():
    companies = Company.query.order_by(Company.id.desc()).all()
    return render_template(
        "dashboard/companies_delete/index.html",
        companies=companies
    )

@companies_delete_bp.route("/<int:company_id>/delete", methods=["POST"])
def delete(company_id):
    company = Company.query.get(company_id)

    if not company:
        flash("対象データが存在しません。", "danger")
        return redirect(url_for("companies_delete.index"))

    display_label = (
        company.company_name or
        company.email or
        company.company_site or
        f"ID:{company.id}"
    )

    db.session.delete(company)
    db.session.commit()

    flash(f"企業「{display_label}」を削除しました。", "success")
    return redirect(url_for("companies_delete.index"))
