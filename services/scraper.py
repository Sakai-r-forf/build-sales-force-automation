import csv
import os
import re
import tempfile
import time
from collections import deque
from contextvars import ContextVar
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
from flask import current_app
from services.crawl_policy import PoliteFetcher
from services.network import validate_public_url
from services.store import canonical_url, upsert_company

_stats = ContextVar("crawl_stats", default=None)


def parse_keywords(value):
    if isinstance(value, list):
        value = ",".join(value)
    return [k.strip() for k in re.split(r"[,、\r\n]+", value or "") if k.strip()]


def crawl_and_export(seed_url, allowed_domain=None, limit=100, max_pages=30, jp_keywords=None):
    start = time.monotonic()
    deadline = start + current_app.config["CRAWL_TIME_BUDGET"]
    stats = {"total": 0, "requests": 0, "failed_requests": 0, "by_domain": {}, "partial": False}
    _stats.set(stats)
    seed_url = canonical_url(seed_url)
    validate_public_url(seed_url, current_app.config["ALLOW_LOOPBACK"])
    seed_host = urlparse(seed_url).hostname
    allowed_domain = (allowed_domain or seed_host).lower().removeprefix("www.")
    if "://" in allowed_domain:
        allowed_domain = urlparse(allowed_domain).hostname or ""
    keywords = parse_keywords(jp_keywords)
    visited = set()
    extracted = set()
    queue = deque([seed_url])
    rows = {}

    fetcher = PoliteFetcher(deadline, max_pages, stats)
    fetch = fetcher.fetch

    def save_candidate(url, html=None, source=None):
        if url in extracted or len(rows) >= limit:
            return
        extracted.add(url)
        html = html or fetch(url)
        if not html:
            return
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        info = {"company_name": _company_name(soup), "homepage_url": url,
                "contact_url": _contact_url(soup, url), "email": _email(text),
                "phone": _phone(text), "address": _address(soup, text), "source_url": source or url}
        if keywords and not any(k.casefold() in text.casefold() for k in keywords):
            return
        # mailto addresses may not be visible in page text.
        mailto = soup.select_one('a[href^="mailto:"]')
        if mailto and not info["email"]:
            info["email"] = mailto["href"][7:].split("?")[0]
        if not info["company_name"]:
            return
        record = upsert_company(info)  # Errors propagate: never report a failed save as success.
        if record:
            rows[record["key"]] = info
            stats["total"] = len(rows)

    while queue and len(rows) < limit:
        if time.monotonic() >= deadline or stats["requests"] >= max_pages:
            stats["partial"] = True
            break
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        html = fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        candidates = []
        internal = []
        for a in soup.find_all("a", href=True):
            try:
                target = canonical_url(urljoin(url, a["href"]))
            except ValueError:
                continue
            host = urlparse(target).hostname.lower().removeprefix("www.")
            label = a.get_text(" ", strip=True)
            if host == allowed_domain or host.endswith("." + allowed_domain):
                if target not in visited:
                    internal.append(target)
                if re.search(r"株式会社|有限会社|合同会社", label) or "c-companies-profile-list-member__name" in a.get("class", []):
                    candidates.append((target, None))
            elif host not in {"facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "line.me", "google.com"}:
                candidates.append((target, None))
        # A company's own URL is also a valid seed; do not require an external link.
        title = _company_name(soup)
        if url == seed_url and not candidates and re.search(r"株式会社|有限会社|合同会社", title):
            candidates.append((url, html))
        for target, cached in dict(candidates).items():
            if time.monotonic() >= deadline or (not cached and stats["requests"] >= max_pages):
                stats["partial"] = True
                break
            save_candidate(target, cached, url)
            if len(rows) >= limit:
                break
        queue.extend(t for t in dict.fromkeys(internal) if t not in visited)

    fd, csv_path = tempfile.mkstemp(prefix="companies_", suffix=".csv")
    headers = ["company_name", "homepage_url", "contact_url", "email", "phone", "address", "source_url"]
    with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows.values():
            writer.writerow([_csv_value(row.get(key, "")) for key in headers])
    stats["duration_seconds"] = round(time.monotonic() - start, 2)
    return csv_path


def _csv_value(value):
    value = str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


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
    return dict(_stats.get() or {})
