import csv, os, time, requests, re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from models import db
from models.company import Company

_stats = {}

def crawl_and_export(seed_url, allowed_domain=None, limit=100, max_pages=100, jp_keywords=None):
    start = time.time()
    visited = set()
    queue = [seed_url]
    rows = []

    filename = f"companies_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = os.path.join(os.getcwd(), filename)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    keywords = []
    if isinstance(jp_keywords, list):
        keywords = [k.strip() for k in jp_keywords if k.strip()]
    elif isinstance(jp_keywords, str):
        keywords = [k.strip() for k in re.split(r"[,\\n]", jp_keywords) if k.strip()]

    seed_host = urlparse(seed_url).netloc.replace("www.", "").lower()

    while queue and len(rows) < limit and len(visited) < max_pages:
        url = queue.pop(0)
        url = _normalize_url(url)
        if url in visited:
            continue
        visited.add(url)

        html = _fetch(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        homepage_links = _extract_homepage_links(soup, url, allowed_domain, seed_host)

        for hp in homepage_links:
            info = _extract_company_info(hp)
            if not info:
                continue

            if keywords:
                combined = " ".join([
                    info.get("company_name", ""),
                    info.get("address", ""),
                    info.get("homepage_url", "")
                ])
                if not any(k in combined for k in keywords):
                    continue

            rows.append(info)

            site = info.get("homepage_url") or info.get("source_url")
            if site:
                try:
                    exists = Company.query.filter_by(company_site=site).first()
                    if not exists:
                        db.session.add(Company(
                            company_name=info.get("company_name") or "",
                            company_site=site,
                            inquiry_url=info.get("contact_url") or "",
                            email=info.get("email") or "",
                            phone=info.get("phone") or "",
                        ))
                        db.session.commit()
                        print(f"Saved to DB: {site}")
                    else:
                        print(f"Already Exists: {site}")

                except Exception as e:
                    db.session.rollback()
                    print(f"DB Error for {site}: {e}")

            if len(rows) >= limit:
                break

        for a in soup.find_all("a", href=True):
            next_url = urljoin(url, a["href"])
            next_url = _normalize_url(next_url)
            if next_url not in visited and _allowed(next_url, seed_url, allowed_domain):
                queue.append(next_url)

    dedup = {}
    for r in rows:
        key = r["homepage_url"] or r["source_url"]
        if key and key not in dedup:
            dedup[key] = r
    final_rows = list(dedup.values())

    headers = ["company_name", "homepage_url", "contact_url", "email", "phone", "address", "source_url"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in final_rows:
            w.writerow([
                r["company_name"],
                r["homepage_url"],
                r["contact_url"],
                r["email"],
                r["phone"],
                r["address"],
                r["source_url"],
            ])

    _stats["total"] = len(final_rows)
    _stats["last_file"] = csv_path
    _stats["duration_seconds"] = round(time.time() - start, 2)

    return csv_path

def _extract_homepage_links(soup, base_url, allowed_domain, seed_host):
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        host = urlparse(href).netloc.replace("www.", "").lower()

        if allowed_domain:
            if allowed_domain.replace("www.", "").lower() not in host:
                continue
        else:
            if host == seed_host:
                continue

        if ".co.jp" in host or host.endswith(".jp") or host.endswith(".com"):
            links.append(_normalize_url(href))

    return list(set(links))

def _extract_company_info(homepage_url):
    html = _fetch(homepage_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    return {
        "company_name": _company_name(soup),
        "homepage_url": homepage_url,
        "contact_url": _contact_url(soup, homepage_url),
        "email": _email(text),
        "phone": _phone(text),
        "address": _address(soup, text),
        "source_url": homepage_url,
    }

def _fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or r.encoding
            return r.text
    except:
        return None
    return None

def _normalize_url(u):
    if not u:
        return u
    u = u.split("#")[0]
    if u.endswith("/"):
        u = u[:-1]
    return u

def _allowed(next_url, seed_url, allowed_domain):
    host = urlparse(next_url).netloc.replace("www.", "").lower()

    if allowed_domain:
        return allowed_domain.replace("www.", "").lower() in host

    seed_host = urlparse(seed_url).netloc.replace("www.", "").lower()
    return seed_host in host

def _company_name(soup):
    for h in soup.find_all(["h1", "h2"]):
        t = h.get_text(" ", strip=True)
        if t:
            return t
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    return ""

def _contact_url(soup, base_url):
    labels = ["お問い合わせ", "お問合せ", "contact", "inquiry"]
    for a in soup.find_all("a", href=True):
        label = (a.get_text() or "").strip()
        href = a["href"].lower()
        if any(l.lower() in label.lower() for l in labels) or any(x in href for x in ["contact", "inquiry"]):
            return urljoin(base_url, a["href"])
    return ""

def _email(text):
    res = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return res[0] if res else ""

def _phone(text):
    res = re.findall(r"\d{2,4}-\d{2,4}-\d{3,4}", text)
    return res[0] if res else ""

def _address(soup, text):
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            k = dt.get_text(" ", strip=True)
            v = dd.get_text(" ", strip=True)
            if "住所" in k or "所在地" in k:
                return v

    for tr in soup.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            k = th.get_text(" ", strip=True)
            v = td.get_text(" ", strip=True)
            if "住所" in k or "所在地" in k:
                return v

    m = re.search(r"(〒\s*\d{3}-\d{4}[\s　]*[^\n]{0,50})", text)
    if m:
        return m.group(1)

    return ""

def get_stats():
    return _stats
