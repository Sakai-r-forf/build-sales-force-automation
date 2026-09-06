import math
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from flask import Blueprint, render_template, request
from flask_login import login_required
from services.store import companies

companies_bp = Blueprint("companies", __name__)


def display_record(record):
    record = dict(record)
    try:
        record["created_at"] = datetime.fromisoformat(record["created_at"].replace("/", "-"))
        if record["created_at"].tzinfo:
            record["created_at"] = record["created_at"].astimezone(ZoneInfo("Asia/Tokyo"))
    except (ValueError, KeyError):
        record["created_at"] = None
    return SimpleNamespace(**record)


@companies_bp.get("/")
@login_required
def index():
    search = request.args.get("search", "").strip()
    all_rows = companies(search)
    pages = max(1, math.ceil(len(all_rows) / 100))
    page = min(max(1, request.args.get("page", 1, type=int)), pages)
    pagination = SimpleNamespace(page=page, pages=pages, has_prev=page>1, has_next=page<pages, prev_num=page-1, next_num=page+1)
    return render_template("dashboard/companies/index.html", companies=[display_record(c) for c in all_rows[(page-1)*100:page*100]], pagination=pagination, search=search)
