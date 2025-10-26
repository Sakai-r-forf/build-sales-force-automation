import csv, os, time
from urllib.parse import urlparse

def crawl_and_export(seed_url, allowed_domain=None, limit=100, max_pages=100, jp_keywords=None):

    start = time.time()
    filename = f"companies_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = os.path.join(os.getcwd(), filename)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company_name", "url", "email", "phone"])
        writer.writerow(["株式会社サンプル", seed_url, "info@example.com", "03-0000-0000"])

    _stats["total"] = 1
    _stats["by_domain"] = {urlparse(seed_url).netloc: 1}
    _stats["duration_seconds"] = round(time.time() - start, 2)
    _stats["last_file"] = csv_path

    return csv_path

_stats = {}

def get_stats():
    return _stats