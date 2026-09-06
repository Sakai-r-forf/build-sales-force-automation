import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import create_app
from services.store import StateStore, upsert_company, companies, exclude_company
from services.scraper import parse_keywords
from services.playwright_submit import Result


def test_pages_and_anonymous_access(app,client):
    for path in ['/','/companies/','/scraping/','/companies_delete/','/graphs/','/faq/','/readyz']:
        assert client.get(path,follow_redirects=True).status_code==200, path
    anonymous=app.test_client()
    assert anonymous.get('/companies_delete/').status_code==302
    assert anonymous.post('/deliveries/1/send',json={}).status_code==400
    assert client.post('/deliveries/settings',json={}).status_code==400


def test_persists_restart_exclusion_and_unique_company(app):
    with app.app_context():
        first=upsert_company({'company_name':'株式会社サンプル','homepage_url':'https://example.com/','contact_url':'https://example.com/contact'})
        second=upsert_company({'company_name':'株式会社サンプル2','homepage_url':'http://www.example.com'})
        assert first['id']==second['id']
    restarted=create_app(dict(app.config))
    with restarted.app_context():
        assert len(companies())==1
        assert companies()[0]['company_name']=='株式会社サンプル2'
        exclude_company(first['id'])
        assert upsert_company({'company_name':'再取得','homepage_url':'https://example.com'}) is None
        assert companies()==[]


def test_parallel_local_writes_do_not_lose_data(tmp_path):
    store=StateStore(path=tmp_path/'state.json')
    def increment(_):
        store.mutate(lambda state:state.update(next_id=state['next_id']+1))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(increment,range(40)))
    assert store.read()['next_id']==41


def test_keywords():
    assert parse_keywords('建設,工務店\n東京都、埼玉県')==['建設','工務店','東京都','埼玉県']


def test_settings_saved_and_validation(client,payload):
    response=client.post('/deliveries/settings',json=payload,headers={'X-CSRF-Token':'test-csrf'})
    assert response.status_code==200
    assert client.get('/deliveries/settings').json['body']==payload['body']
    assert client.post('/deliveries/settings',json={'body':'x'},headers={'X-CSRF-Token':'test-csrf'}).status_code==400


@pytest.mark.parametrize('result_status',['sent','unknown'])
def test_duplicate_delivery_blocked(app,client,payload,monkeypatch,result_status):
    with app.app_context():
        record=upsert_company({'company_name':'テスト企業','homepage_url':'https://example.com','contact_url':'https://example.com/contact'})
    calls=[]
    def submit(url,data,before_submit,**kwargs):
        before_submit();calls.append(data);return Result(result_status,'result')
    monkeypatch.setattr('views.deliveries.submit_contact',submit)
    payload['body']='{company_name} 御中\nテストです。'
    response=client.post(f"/deliveries/{record['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'})
    assert response.json['status']==result_status
    assert calls[0]['body']=='テスト企業 御中\nテストです。'
    response=client.post(f"/deliveries/{record['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'})
    assert response.status_code==409 and len(calls)==1


def test_save_failure_does_not_send(app,client,payload,monkeypatch):
    called=[]
    monkeypatch.setattr('views.deliveries.submit_contact',lambda *a,**kw:called.append(1))
    def fail(*args):raise RuntimeError('storage down')
    monkeypatch.setattr(app.extensions['state_store'],'mutate',fail)
    assert client.post('/deliveries/1/send',json=payload,headers={'X-CSRF-Token':'test-csrf'}).status_code==503
    assert not called


def test_crawl_validation(client):
    for data in [{'seed_url':'https://example.com','limit':'bad'},{'seed_url':'https://example.com','limit':'501'},{'seed_url':'file:///etc/passwd'}]:
        assert client.post('/scraping/crawl',data=dict(data,csrf_token='test-csrf')).status_code==400


def test_search_escaping(app,client):
    with app.app_context():
        upsert_company({'company_name':'<img src=x onerror=alert(1)>','homepage_url':'https://example.com'})
    html=client.get('/companies/').text
    assert '<img src=x onerror=alert(1)>' not in html
    assert client.get('/companies/?search=notfound').status_code==200


def test_cloud_generation_conflict_retried_without_lost_updates():
    from google.api_core.exceptions import NotFound,PreconditionFailed
    class FakeBlob:
        generation=0
        state=None
        writes=0
        def download_as_bytes(self,**kwargs):
            if self.state is None:raise NotFound('missing')
            return json.dumps(self.state).encode()
        def upload_from_string(self,raw,if_generation_match,**kwargs):
            self.writes+=1
            if self.writes==1:
                self.state=json.loads(raw);self.state['next_id']=9;self.generation=1
                raise PreconditionFailed('concurrent writer')
            assert if_generation_match==self.generation
            self.state=json.loads(raw);self.generation+=1
    blob=FakeBlob();store=StateStore(bucket='fake');store.blob=lambda:blob
    store.mutate(lambda s:s.update(next_id=s['next_id']+1))
    assert store.read()['next_id']==10


def test_same_contact_form_cannot_be_sent_from_duplicate_rows(app,client,payload,monkeypatch):
    with app.app_context():
        a=upsert_company({'company_name':'A','homepage_url':'https://directory.example.com/a','contact_url':'https://example.com/contact'})
        b=upsert_company({'company_name':'B','homepage_url':'https://directory.example.com/b','contact_url':'http://www.example.com/contact/'})
    monkeypatch.setattr('views.deliveries.submit_contact',lambda *args,**kwargs:Result('sent','done'))
    assert client.post(f"/deliveries/{a['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'}).status_code==200
    assert client.post(f"/deliveries/{b['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'}).status_code==409


def test_authenticated_csrf_failure_does_not_mutate(app,client,payload):
    before=app.extensions['state_store'].read()
    assert client.post('/deliveries/settings',json=payload,headers={'X-CSRF-Token':'bad'}).status_code==400
    assert app.extensions['state_store'].read()==before


def test_japan_date(app):
    from views.companies import display_record
    assert display_record({'created_at':'2026-09-06T17:00:00+00:00'}).created_at.strftime('%Y/%m/%d')=='2026/09/07'
