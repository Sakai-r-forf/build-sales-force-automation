from bs4 import BeautifulSoup
import requests
import csv
import re
import time
import random
from collections import deque, defaultdict
from urllib.parse import urljoin, urlparse
import os
import datetime
import urllib.robotparser as robotparser

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PHONE_RE = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")
POSTAL_RE = re.compile(r"〒?\s?\d{3}-?\\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}")
COMPANY_WORDS = ["株式会社", "有限会社", "合同会社", "建設", "工務店", "土木", "建築"]
CONTACT_WORDS = [
    "お問い合わせ", "お問合せ", "問合せ", "contact", "inquiry", "お問い合わせフォーム"
]
PROFILE_WORDS = ["会社概要", "企業情報", "会社案内", "company", "企業概要"]
SITE_WORDS = ["公式サイト", "公式ホームページ", "ホームページ", "website", "site"]

# === 統計 ===
from time import time as _now
REQUEST_COUNT = 0
REQUESTS_BY_DOMAIN = defaultdict(int)
LAST_RUN_STARTED_AT = None
LAST_RUN_FINISHED_AT = None

def get_stats():
    duration = None
    if LAST_RUN_STARTED_AT and LAST_RUN_FINISHED_AT:
        duration = LAST_RUN_FINISHED_AT - LAST_RUN_STARTED_AT
    return {
        "total": REQUEST_COUNT,
        "by_domain": dict(REQUESTS_BY_DOMAIN),
        "started_at": LAST_RUN_STARTED_AT,
        "finished_at": LAST_RUN_FINISHED_AT,
        "duration_seconds": duration,
    }

def can_fetch(url: str, user_agent: str = UA) -> bool:
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True

def get(url: str, timeout: int = 15) -> requests.Response | None:
    # robots.txt 禁止はスキップ
    if not can_fetch(url):
        return None
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)

        # 到達リクエストをカウント
        global REQUEST_COUNT
        REQUEST_COUNT += 1
        try:
            dom = urlparse(url).netloc
            REQUESTS_BY_DOMAIN[dom] += 1
        except Exception:
            pass

        # 進捗ログ（50件ごと）
        if REQUEST_COUNT % 50 == 0:
            print(f"[scraper] requests so far: {REQUEST_COUNT} (latest={url})")

        # HTMLのみ対象
        if "text/html" in resp.headers.get("Content-Type", ""):
            return resp
    except Exception:
        return None
    return None

def text_or_none(el):
    if not el:
        return None
    t = el.get_text(" ", strip=True)
    return t if t else None

def absol(url, link):
    return urljoin(url, link)

def same_domain(url: str, domain: str | None) -> bool:
    if not domain:
        return True
    try:
        return urlparse(url).netloc.endswith(domain)
    except Exception:
        return False

def guess_company_name(soup: BeautifulSoup) -> str | None:
    # 優先: h1, og:site_name, title
    h1 = soup.find("h1")
    if h1:
        t = text_or_none(h1)
        if t and any(w in t for w in COMPANY_WORDS):
            return t
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        c = og["content"].strip()
        if any(w in c for w in COMPANY_WORDS):
            return c
    title = soup.find("title")
    if title:
        t = text_or_none(title)
        if t:
            # 区切り記号で左側を優先
            for sep in ["｜", "|", "-", "—", "/"]:
                if sep in t:
                    left = t.split(sep)[0].strip()
                    if any(w in left for w in COMPANY_WORDS):
                        return left
            if any(w in t for w in COMPANY_WORDS):
                return t
    return None

def extract_contacts(soup: BeautifulSoup, base_url: str):
    contact_url = None
    homepage_url = None
    email = None
    phone = None
    address = None

    # メール/電話/住所（簡易）
    body_text = soup.get_text(" ", strip=True)
    m = EMAIL_RE.search(body_text)
    if m:
        email = m.group(0)
    m = PHONE_RE.search(body_text)
    if m:
        phone = m.group(0)
    m = POSTAL_RE.search(body_text)
    if m:
        # 郵便番号の前後50文字くらいを住所候補に
        idx = body_text.find(m.group(0))
        start = max(0, idx - 50)
        end = min(len(body_text), idx + 80)
        address = body_text[start:end].strip()

    # aタグからホームページ/お問い合わせを推測
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        abs_url = absol(base_url, href)
        text = text_or_none(a) or ""

        # お問い合わせ
        if any(w in text.lower() for w in ["contact", "inquiry"]) or any(w in text for w in CONTACT_WORDS):
            contact_url = abs_url if not contact_url else contact_url

        # 公式サイト/ホームページ
        if any(w in text for w in SITE_WORDS):
            homepage_url = abs_url if not homepage_url else homepage_url

    return contact_url, homepage_url, email, phone, address

def crawl_and_export(seed_url: str, allowed_domain: str | None, limit: int, max_pages: int, jp_keywords: list[str]) -> str:
    # 実行開始
    global LAST_RUN_STARTED_AT, LAST_RUN_FINISHED_AT, REQUEST_COUNT, REQUESTS_BY_DOMAIN
    LAST_RUN_STARTED_AT = _now()
    LAST_RUN_FINISHED_AT = None
    REQUEST_COUNT = 0
    REQUESTS_BY_DOMAIN.clear()

    seen = set()
    q = deque([seed_url])
    results = []
    pages_fetched = 0

    while q and len(results) < limit and pages_fetched < max_pages:
        url = q.popleft()
        if url in seen:
            continue
        seen.add(url)

        if allowed_domain and not same_domain(url, allowed_domain):
            continue

        resp = get(url)
        if not resp:
            continue

        pages_fetched += 1
        soup = BeautifulSoup(resp.text, "lxml")

        # 企業らしい断片があるページを抽出
        page_text = soup.get_text(" ", strip=True)
        score = 0
        for kw in set(jp_keywords + COMPANY_WORDS):
            if kw in page_text:
                score += 1

        if score >= 2:  # ゆるい閾値
            name = guess_company_name(soup)
            contact_url, homepage_url, email, phone, address = extract_contacts(soup, resp.url)
            row = {
                "source_url": resp.url,
                "company_name": name,
                "contact_url": contact_url,
                "homepage_url": homepage_url,
                "email": email,
                "phone": phone,
                "address": address,
            }
            # 何かしら見つかっていれば採用
            if any([name, contact_url, homepage_url, email, phone, address]):
                results.append(row)
                if len(results) >= limit:
                    break

        # 次リンクを収集
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            abs_url = absol(resp.url, href)
            parsed = urlparse(abs_url)
            if parsed.scheme in ("http", "https") and (not allowed_domain or parsed.netloc.endswith(allowed_domain)):
                if abs_url not in seen and len(seen) + len(q) < max_pages * 5:
                    q.append(abs_url)

        # ポライトネス
        time.sleep(1 + random.random() * 0.5)

    # CSV出力
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"companies_{ts}.csv"
    path = os.path.abspath(fname)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "company_name",
                "homepage_url",
                "contact_url",
                "email",
                "phone",
                "address",
                "source_url",
            ],
        )
        writer.writeheader()
        for r in results[:limit]:
            writer.writerow(r)

    # 実行終了・サマリ
    LAST_RUN_FINISHED_AT = _now()
    stats = get_stats()
    print("[scraper] ===== Crawl Summary =====")
    print(f"[scraper] total requests: {stats['total']}")
    print(f"[scraper] duration (sec): {stats['duration_seconds']}")
    print(f"[scraper] by domain: {stats['by_domain']}")

    # 参考：テキストにも保存
    try:
        with open("last_run_stats.txt", "w", encoding="utf-8") as fh:
            fh.write(f"total={stats['total']}\n")
            fh.write(f"duration_seconds={stats['duration_seconds']}\n")
            for k, v in stats["by_domain"].items():
                fh.write(f"{k}={v}\n")
    except Exception:
        pass

    return path