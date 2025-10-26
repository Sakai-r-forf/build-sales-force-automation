from flask import Flask, request, send_file, render_template_string
from scraper import crawl_and_export, get_stats
from flask import Flask, render_template, request

app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>建設業 企業情報スクレイパー</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; padding: 24px; }
      form { display: grid; gap: 12px; max-width: 680px; }
      input, button, textarea { padding: 10px; font-size: 16px; }
      label { font-weight: 600; }
      .hint { color: #666; font-size: 14px; }
    </style>
  </head>
  <body>
    <h1>建設業 企業情報スクレイパー（最大100件）</h1>
    <form method="POST" action="/crawl">
      <label>スタートURL（企業一覧や加盟団体のリスト等）</label>
      <input required name="seed_url" placeholder="https://example.com/constructors/list" />

      <label>クロール対象ドメイン（省略可：seedと同一ドメインのみ）</label>
      <input name="allowed_domain" placeholder="example.com" />

      <label>最大件数（既定：100）</label>
      <input name="limit" type="number" min="1" max="500" value="100" />

      <label>最大取得ページ数（既定：100 / 誤爆防止）</label>
      <input name="max_pages" type="number" min="1" max="2000" value="500" />

      <label>日本語のキーワード（改行区切り、見つけやすくするため）</label>
      <textarea name="jp_keywords" rows="4" placeholder="株式会社
有限会社
建設
工務店
お問い合わせ
会社概要"></textarea>

      <button type="submit">CSVを生成</button>
      <p class="hint">※ robots.txt を尊重し、1〜1.5秒の遅延を入れます。</p>
    </form>
  </body>
</html>
"""

@app.get("/")
def index():
    return render_template_string(INDEX_HTML)

@app.post("/crawl")
def crawl():
    seed_url = request.form.get("seed_url", "").strip()
    allowed_domain = request.form.get("allowed_domain", "").strip() or None
    limit = int(request.form.get("limit", 100))
    max_pages = int(request.form.get("max_pages", 100))
    jp_keywords_raw = request.form.get("jp_keywords", "").strip()
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

@app.get("/login")
def login():
    return render_template("auth/login.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7700, debug=True)
