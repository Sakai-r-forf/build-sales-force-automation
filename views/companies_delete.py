from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required
from services.store import companies, exclude_company

companies_delete_bp = Blueprint("companies_delete", __name__)


@companies_delete_bp.get("/")
@login_required
def index():
    return render_template("dashboard/companies_delete/index.html", companies=companies())


@companies_delete_bp.post("/<int:company_id>/delete")
@login_required
def delete(company_id):
    if exclude_company(company_id):
        flash("企業を一覧から削除しました。再取得・自動送信の対象からも除外されます。", "success")
    else:
        flash("対象データが存在しません。", "danger")
    return redirect(url_for("companies_delete.index"))
