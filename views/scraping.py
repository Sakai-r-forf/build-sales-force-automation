import os
from flask import Blueprint, current_app, jsonify, render_template, request, send_file
from flask_login import login_required
from services.scraper import crawl_and_export, get_stats

scraping_bp = Blueprint("scraping", __name__)


@scraping_bp.get("/")
@login_required
def index():
    return render_template("dashboard/scraping/index.html")


@scraping_bp.post("/crawl")
@login_required
def crawl():
    seed_url = request.form.get("seed_url", "").strip()
    try:
        limit = int(request.form.get("limit") or 100)
        max_pages = int(request.form.get("max_pages") or 100)
        if not seed_url or not 1 <= limit <= 500 or not 1 <= max_pages <= 2000:
            raise ValueError("URL、最大取得件数（1〜500）、最大取得ページ数（1〜2000）を確認してください。")
        csv_path = crawl_and_export(seed_url, request.form.get("allowed_domain", "").strip(), limit, max_pages, request.form.get("jp_keywords", ""))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except Exception:
        current_app.logger.exception("Company crawl/save failed")
        return jsonify(error="取得または保存に失敗しました。すでに保存できた企業は企業情報一覧で確認できます。時間をおいて再度お試しください。"), 503
    stats = get_stats()
    if not stats["total"]:
        os.unlink(csv_path)
        return jsonify(error="該当企業を取得できませんでした。URL・キーワード・対象サイトへの接続可否を確認してください。削除済み企業は再取得されません。", stats=stats), 422
    response = send_file(csv_path, as_attachment=True, download_name=os.path.basename(csv_path))
    response.headers["X-Saved-Count"] = str(stats["total"])
    response.headers["X-Crawl-Partial"] = str(stats["partial"]).lower()
    response.headers["X-Crawl-Duration-Seconds"] = str(stats["duration_seconds"])
    # send_file has already opened the file; unlink prevents accumulating exports.
    os.unlink(csv_path)
    return response
