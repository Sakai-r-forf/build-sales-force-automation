"""Shared crawl lease and polite, bounded HTTP access (including robots/redirects)."""
import time
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

import requests
from flask import current_app
from services.network import validate_public_url
from services.store import store

AGENT = 'BuildSalesContactTool'
MIN_INTERVAL = 5.0


class CrawlBusy(Exception):
    pass


class WaitForHost(Exception):
    def __init__(self, until):
        self.until = until


@contextmanager
def crawl_lease():
    owner = uuid.uuid4().hex
    def acquire(state):
        if state.get('crawl_lease', {}).get('until', 0) > time.time():
            raise CrawlBusy('別の取得処理が実行中です。完了後に再度お試しください。')
        state['crawl_lease'] = {'owner': owner, 'until': time.time() + 360}
    store().mutate(acquire)
    try:
        yield
    finally:
        def release(state):
            if state.get('crawl_lease', {}).get('owner') == owner:
                state.pop('crawl_lease', None)
        store().mutate(release)


class PoliteFetcher:
    def __init__(self, deadline, budget, stats, *, clock=time.time, monotonic=time.monotonic, sleep=time.sleep, get=requests.get):
        self.deadline, self.budget, self.stats = deadline, budget, stats
        self.clock, self.monotonic, self.sleep, self.get = clock, monotonic, sleep, get
        self.rules, self.cache, self.blocked = {}, {}, set()
        self.stats.setdefault('skipped_requests', 0)

    def available(self):
        if self.monotonic() >= self.deadline or self.stats['requests'] >= self.budget:
            self.stats['partial'] = True
            return False
        return True

    def cooldown(self, host, seconds):
        def update(state):
            hosts = state.setdefault('crawl_hosts', {})
            hosts[host] = max(hosts.get(host, 0), self.clock() + seconds)
        store().mutate(update)

    def slot(self, host, interval):
        while self.available():
            def reserve(state):
                hosts = state.setdefault('crawl_hosts', {})
                if hosts.get(host, 0) > self.clock():
                    raise WaitForHost(hosts[host])
                # Drop expired entries to bound long-lived state size.
                state['crawl_hosts'] = {h: t for h, t in hosts.items() if t > self.clock()}
                state['crawl_hosts'][host] = self.clock() + interval
            try:
                store().mutate(reserve)
                return self.available()
            except WaitForHost as wait:
                delay = max(0, wait.until - self.clock())
                if delay >= self.deadline - self.monotonic():
                    self.stats['partial'] = True
                    return False
                self.sleep(delay)
        return False

    def request(self, url, interval):
        validate_public_url(url, current_app.config['ALLOW_LOOPBACK'])
        host = urlsplit(url).hostname.lower().removeprefix('www.')
        if host in self.blocked or not self.slot(host, interval):
            return None
        self.stats['requests'] += 1
        self.stats['by_domain'][host] = self.stats['by_domain'].get(host, 0) + 1
        try:
            with self.get(url, headers={'User-Agent': AGENT + '/1.0'},
                          timeout=min(10, max(.1, self.deadline-self.monotonic())),
                          allow_redirects=False, stream=True) as response:
                status, headers = response.status_code, response.headers
                if status == 429 or status >= 500:
                    retry = headers.get('Retry-After', '')
                    try:
                        delay = float(retry)
                    except ValueError:
                        try:
                            delay = parsedate_to_datetime(retry).timestamp() - self.clock()
                        except (TypeError, ValueError, OverflowError):
                            delay = 300
                    self.cooldown(host, max(300, min(delay, 86400)))
                    self.blocked.add(host)
                    self.stats['failed_requests'] += 1
                    self.stats['partial'] = True
                    return None
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 3_000_000 or self.monotonic() >= self.deadline:
                        self.stats['partial'] = True
                        return None
                    chunks.append(chunk)
                response._content = b''.join(chunks)
                response.encoding = response.apparent_encoding or 'utf-8'
                return status, headers, response.text
        except requests.RequestException:
            self.blocked.add(host)
            self.cooldown(host, 300)
            self.stats['failed_requests'] += 1
            self.stats['partial'] = True
            return None
        finally:
            # The next request waits at least this long after completion, too.
            self.cooldown(host, interval)

    def policy(self, url):
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.rules:
            self.rules[origin] = (None, MIN_INTERVAL)  # Fail closed during redirects/errors.
            target = origin + '/robots.txt'
            for _ in range(6):
                result = self.request(target, MIN_INTERVAL)
                if result is None:
                    break
                status, headers, body = result
                if 300 <= status < 400 and headers.get('Location'):
                    redirected = urljoin(target, headers['Location'])
                    # A cross-origin robots redirect is skipped conservatively.
                    if urlsplit(redirected).netloc != parts.netloc:
                        break
                    target = redirected
                    continue
                if status in (404, 410):
                    body = 'User-agent: *\nAllow: /'
                elif status != 200 or body.lstrip().startswith('<'):
                    break
                parser = RobotFileParser()
                parser.parse(body.splitlines())
                delay = max(MIN_INTERVAL, parser.crawl_delay(AGENT) or 0)
                rate = parser.request_rate(AGENT)
                if rate and rate.requests:
                    delay = max(delay, rate.seconds / rate.requests)
                # Also honor fractional delays unsupported by RobotFileParser.
                for line in body.splitlines():
                    key, sep, value = line.partition(':')
                    if sep and key.strip().lower() == 'crawl-delay':
                        try:
                            delay = max(delay, float(value.split('#')[0].strip()))
                        except ValueError:
                            pass
                self.rules[origin] = (parser, delay)
                self.cooldown(parts.hostname.lower().removeprefix('www.'), delay)
                break
        return self.rules[origin]

    def fetch(self, url):
        if url in self.cache:
            return self.cache[url]
        original = url
        self.cache[original] = None
        try:
            for _ in range(6):
                if not self.available():
                    return None
                validate_public_url(url, current_app.config['ALLOW_LOOPBACK'])
                parser, delay = self.policy(url)
                if parser is None or not parser.can_fetch(AGENT, url):
                    self.stats['skipped_requests'] += 1
                    self.stats['partial'] = True
                    return None
                result = self.request(url, delay)
                if result is None:
                    return None
                status, headers, body = result
                if 300 <= status < 400 and headers.get('Location'):
                    url = urljoin(url, headers['Location'])
                    continue
                if status != 200:
                    self.stats['failed_requests'] += 1
                    self.stats['partial'] = True
                    return None
                if 'html' not in headers.get('Content-Type', 'text/html'):
                    return None
                self.cache[original] = self.cache[url] = body
                return body
            self.stats['partial'] = True
        except ValueError:
            self.stats['skipped_requests'] += 1
            self.stats['partial'] = True
        return None
