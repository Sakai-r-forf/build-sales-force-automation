from flask import Blueprint, render_template
from flask_login import login_required

graphs_bp = Blueprint("graphs", __name__)

@graphs_bp.get("/")
@login_required
def index():
    return render_template("dashboard/graphs/index.html")