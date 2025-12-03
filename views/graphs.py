from flask import Blueprint, render_template
from flask_login import login_required
from models.graph import GraphData

graphs_bp = Blueprint("graphs", __name__)

@graphs_bp.get("/")
@login_required
def index():
    return render_template(
        "dashboard/graphs/index.html",
        email=GraphData.email_distribution(),
        inquiry=GraphData.inquiry_distribution(),
        phone=GraphData.phone_distribution(),
        daily=GraphData.daily_scrape_counts(),
    )