from contextlib import contextmanager
import pytest
from services.crawl_policy import PoliteFetcher, crawl_lease, CrawlBusy
from services.store import store, StateStore


class Clock:
    value = 1000.
    def time(self): return self.value
    def sleep(self, seconds): self.value += seconds


class Response:
    def __init__(self, body='', status=200, headers=None):
        self.status_code=status
        self.headers=headers or {'Content-Type':'text/html'}
        self._content=body.encode()
        self.apparent_encoding='utf-8'
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def iter_content(self,size): yield self._content
    @property
    def text(self): return self._content.decode()


def fetcher(clock, get, budget=30, duration=220):
    stats={'requests':0,'failed_requests':0,'by_domain':{},'partial':False}
    return PoliteFetcher(clock.time()+duration,budget,stats,clock=clock.time,monotonic=clock.time,sleep=clock.sleep,get=get)


def test_host_interval_cache_and_cross_instance_state(app,monkeypatch):
    monkeypatch.setattr('services.crawl_policy.validate_public_url',lambda *a:None)
    clock=Clock(); calls=[]
    def get(url,**kwargs):
        calls.append((url,clock.time()))
        return Response('User-agent: *\nCrawl-delay: 7.5\nAllow: /' if url.endswith('robots.txt') else '<h1>ok</h1>')
    with app.app_context():
        first=fetcher(clock,get)
        assert first.fetch('https://example.com/a')
        assert first.fetch('https://example.com/a')
        assert len(calls)==2
        assert calls[1][1]-calls[0][1]>=7.5
        # A separate store/fetcher simulates another process sharing persistent state.
        original=store()
        app.extensions['state_store']=StateStore(path=original.path)
        second=fetcher(clock,get)
        assert second.fetch('https://example.com/b')
        assert calls[2][1]-calls[1][1]>=7.5
        assert calls[3][1]-calls[2][1]>=7.5


@pytest.mark.parametrize('robots',['User-agent: *\nDisallow: /private', '<html>not robots</html>'])
def test_robots_denied_never_fetches_page(app,monkeypatch,robots):
    monkeypatch.setattr('services.crawl_policy.validate_public_url',lambda *a:None)
    calls=[];clock=Clock()
    def get(url,**kwargs):calls.append(url);return Response(robots)
    with app.app_context():
        f=fetcher(clock,get)
        assert f.fetch('https://example.com/private') is None
        assert calls==['https://example.com/robots.txt']
        assert f.stats['skipped_requests']==1


def test_rate_limit_persists_cooldown_no_retry(app,monkeypatch):
    monkeypatch.setattr('services.crawl_policy.validate_public_url',lambda *a:None)
    calls=[];clock=Clock()
    def get(url,**kwargs):
        calls.append(url)
        return Response('User-agent: *\nAllow: /') if url.endswith('robots.txt') else Response(status=429,headers={'Retry-After':'600'})
    with app.app_context():
        f=fetcher(clock,get)
        assert f.fetch('https://example.com/a') is None
        assert f.fetch('https://example.com/b') is None
        assert len(calls)==2
        assert store().read()['crawl_hosts']['example.com']>=clock.time()+600
        other=fetcher(clock,get)
        assert other.fetch('https://example.com/c') is None
        assert len(calls)==2


def test_redirect_budget_counts_robots(app,monkeypatch):
    monkeypatch.setattr('services.crawl_policy.validate_public_url',lambda *a:None)
    clock=Clock();calls=[]
    def get(url,**kwargs):
        calls.append(url)
        if url.endswith('robots.txt'):return Response('User-agent: *\nAllow: /')
        return Response(status=302,headers={'Location':'https://example.com/redirect'})
    with app.app_context():
        f=fetcher(clock,get,budget=3)
        assert f.fetch('https://example.com/a') is None
        assert len(calls)==3
        assert f.stats['partial']


def test_job_lease_rejects_concurrent_and_releases_after_error(app):
    with app.app_context():
        with pytest.raises(ValueError):
            with crawl_lease():
                with pytest.raises(CrawlBusy):
                    with crawl_lease():pass
                raise ValueError('test')
        with crawl_lease():pass
        assert 'crawl_lease' not in store().read()


def test_saved_sources_persist_deduplicate_delete_and_csrf(app,client):
    headers={'X-CSRF-Token':'test-csrf'}
    data={'name':'会員一覧','url':'https://example.com/list/#part'}
    assert client.post('/scraping/sources',json=data).status_code==400
    first=client.post('/scraping/sources',json=data,headers=headers)
    assert first.status_code==201
    key=first.json['source']['id']
    data.update(name='新しい名前',url='https://example.com/list')
    assert client.post('/scraping/sources',json=data,headers=headers).json['source']['id']==key
    with app.app_context():
        state=StateStore(path=store().path).read()
        assert len(state['sources'])==1 and state['sources'][key]['name']=='新しい名前'
        assert len(state['users'])==1
    assert client.get('/scraping/sources').json['sources'][0]['url']=='https://example.com/list'
    assert client.delete('/scraping/sources/'+key).status_code==400
    assert client.delete('/scraping/sources/'+key,headers=headers).status_code==200
    assert client.get('/scraping/sources').json['sources']==[]
    assert client.delete('/scraping/sources/'+key,headers=headers).status_code==404
    for invalid in [{'name':'','url':'https://example.com'}, {'name':'test','url':'http://169.254.169.254'}, {'name':'test','url':'file:///tmp/test'}, []]:
        assert client.post('/scraping/sources',json=invalid,headers=headers).status_code==400
    assert app.test_client().get('/scraping/sources',headers={'X-Requested-With':'fetch'}).status_code==401
