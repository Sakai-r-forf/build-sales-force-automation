from flask import Blueprint, render_template
from flask_login import login_required

faq_bp = Blueprint("faq", __name__)

@faq_bp.get("/")
@login_required
def index():
    return render_template("dashboard/faq/index.html")