from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from services.store import companies, exclude_company
from services.ng_companies import list_ng, register_ng

companies_delete_bp = Blueprint("companies_delete", __name__)


@companies_delete_bp.get("/")
@login_required
def index():
    return render_template("dashboard/companies_delete/index.html", companies=companies(), ng_companies=list_ng(), excluded=[c for c in companies(include_excluded=True) if c.get("excluded")])


@companies_delete_bp.post("/<int:company_id>/delete")
@login_required
def delete(company_id):
    if exclude_company(company_id):
        flash("企業を一覧から削除しました。再取得・自動送信の対象からも除外されます。", "success")
    else:
        flash("対象データが存在しません。", "danger")
    return redirect(url_for("companies_delete.index"))


@companies_delete_bp.get('/ng')
@login_required
def ng_index():
    return jsonify(companies=list_ng())


@companies_delete_bp.post('/ng')
@login_required
def ng_add():
    try:
        name = request.form.get('name', '')
        website = request.form.get('website', '').strip()
        register_ng(name, domains=[website] if website else [], created_by=current_user.get_id())
        flash('NG企業を登録しました。取得・自動送信の対象から除外されます。', 'success')
    except ValueError as error:
        flash(str(error), 'danger')
    return redirect(url_for('companies_delete.index'))
