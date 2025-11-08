import os, json
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from services.scraper import crawl_and_export, get_stats

scraping_bp = Blueprint(
    "scraping",
    __name__,
    template_folder="../templates/dashboard/scraping",
)

@scraping_bp.get("/")
@login_required
def index():
    return render_template("index.html")

@scraping_bp.post("/crawl")
@login_required
def crawl():
    seed_url = (request.form.get("seed_url") or "").strip()
    allowed_domain = (request.form.get("allowed_domain") or "").strip() or None
    limit = int(request.form.get("limit") or 100)
    max_pages = int(request.form.get("max_pages") or 100)
    jp_keywords_raw = (request.form.get("jp_keywords") or "").strip()
    jp_keywords = [x.strip() for x in jp_keywords_raw.splitlines() if x.strip()] or [
        "株式会社", "有限会社", "建設", "工務店", "お問い合わせ", "会社概要",
    ]

    if not seed_url:
        return "seed_url は必須です", 400

    csv_path = crawl_and_export(
        seed_url=seed_url,
        allowed_domain=allowed_domain,
        limit=limit,
        max_pages=max_pages,
        jp_keywords=jp_keywords,
    )

    resp = send_file(csv_path, as_attachment=True, download_name=os.path.basename(csv_path))
    stats = get_stats()
    resp.headers["X-Request-Count"] = str(stats.get("total", 0))
    resp.headers["X-Requests-By-Domain"] = json.dumps(stats.get("by_domain", {}), ensure_ascii=False)
    resp.headers["X-Crawl-Duration-Seconds"] = str(stats.get("duration_seconds", ""))
    return resp