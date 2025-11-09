import csv, time, os
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

_stats = {}

def crawl_and_export(seed_url, allowed_domain=None, limit=100, max_pages=100, jp_keywords=None):

    start = time.time()

    options = Options()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)

    visited = set()
    queue = [seed_url]
    results = []

    filename = f"companies_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = os.path.join(os.getcwd(), "downloads", filename)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    if jp_keywords:
        keywords = [k.strip() for k in jp_keywords.split(",") if k.strip()]
    else:
        keywords = []

    while queue and len(results) < limit and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue

        visited.add(url)

        try:
            driver.get(url)
            time.sleep(1)
        except:
            continue

        soup = BeautifulSoup(driver.page_source, "html.parser")

        text = soup.get_text(" ", strip=True)

        # ★ キーワード一致判定
        if not keywords or any(k in text for k in keywords):
            title = soup.title.string if soup.title else "不明"
            email = _find_email(text)
            phone = _find_phone(text)
            results.append([title, url, email, phone])

        # ★ リンク取得
        for a in soup.find_all("a", href=True):
            next_url = urljoin(url, a["href"])
            parsed = urlparse(next_url)

            # allowed_domain があれば制限
            if allowed_domain:
                if allowed_domain.replace("www.","") not in parsed.netloc.replace("www.",""):
                    continue
            else:
                # なければ seed と同じドメインのみ
                if urlparse(seed_url).netloc.replace("www.","") not in parsed.netloc.replace("www.",""):
                    continue

            queue.append(next_url)

    driver.quit()

    # CSV 書き込み
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company_name", "url", "email", "phone"])
        writer.writerows(results)

    _stats["total"] = len(results)
    _stats["by_domain"] = {urlparse(seed_url).netloc: len(results)}
    _stats["duration_seconds"] = round(time.time() - start, 2)
    _stats["last_file"] = csv_path

    return csv_path


def _find_email(text):
    import re
    res = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return res[0] if res else ""


def _find_phone(text):
    import re
    res = re.findall(r"\d{2,4}-\d{2,4}-\d{3,4}", text)
    return res[0] if res else ""
