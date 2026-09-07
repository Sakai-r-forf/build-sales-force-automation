import json
from pathlib import Path
import pytest
from app import create_app
from services.ng_companies import register_ng, matching_rule, normalize_name
from services.store import store, upsert_company, companies
from services.playwright_submit import Result, submit_contact

RULES=json.loads((Path(__file__).parents[1]/'data/ng_companies_initial.json').read_text())


def register_all():
    for rule in RULES:
        register_ng(rule['name'],domains=rule['domains'],aliases=rule.get('aliases'))


@pytest.mark.parametrize('name',['株式会社ベースインテリア','（株） 東栄住宅 営業部','ポラス 株式会社','ﾎﾟﾗﾃｯｸ株式会社','株式会社サン・マット','株式会社Ｓａｎ・Ｍａｔ','（株）フロア・エイト','株式会社フロア•エイト','フロアエイト'])
def test_ng_variants_block_collection_and_send(app,client,payload,monkeypatch,name):
    called=[]
    monkeypatch.setattr('views.deliveries.submit_contact',lambda *a,**kw:called.append(1))
    with app.app_context():
        row=upsert_company({'company_name':name,'homepage_url':'https://example.com/profile','contact_url':'https://example.com/form'})
        register_all()
        assert companies()==[]
        assert upsert_company({'company_name':name,'homepage_url':'https://example.net/another'}) is None
        # Even a legacy record with its excluded flag reset cannot bypass policy.
        store().mutate(lambda s:s['companies'][str(row['id'])].update(excluded=False))
    r=client.post(f"/deliveries/{row['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'})
    assert r.status_code==409 and 'NG企業' in r.json['error']
    assert not called


def test_domains_and_title_guards(app):
    with app.app_context():
        register_all();state=store().read()
        for rule in RULES:
            for host in rule['domains']:
                assert matching_rule(state,{},url='https://www.'+host+'/contact')
                assert matching_rule(state,{},url='https://sales.'+host+'/contact')
                assert matching_rule(state,{},url='https://'+host+'.example.com') is None
        assert matching_rule(state,{},title='床工事 | 株式会社フロア・エイト 公式サイト')
        assert matching_rule(state,{'company_name':'株式会社ベストインテリア'}) is None
        assert matching_rule(state,{'company_name':'株式会社サンマックス'}) is None


def test_ng_recheck_while_delivery_is_running(app,client,payload,monkeypatch):
    with app.app_context():
        row=upsert_company({'company_name':'株式会社新規NG','homepage_url':'https://example.com','contact_url':'https://example.com/form'})
    clicks=[]
    def submit(url,data,before_submit,**kw):
        register_ng('株式会社新規NG')
        with pytest.raises(ValueError):before_submit()
        with pytest.raises(ValueError):kw['check_target'](url)
        return Result('failed','NG企業のため停止')
    monkeypatch.setattr('views.deliveries.submit_contact',submit)
    r=client.post(f"/deliveries/{row['id']}/send",json=payload,headers={'X-CSRF-Token':'test-csrf'})
    assert r.json['status']=='failed'
    with app.app_context():assert 'submitted_at' not in store().read()['deliveries'][str(row['id'])]


def test_ng_ui_csrf_and_restart(app,client):
    assert client.post('/companies_delete/ng',data={'name':'株式会社テストNG'}).status_code==400
    data={'name':'株式会社テストNG','website':'https://www.example.com/about','csrf_token':'test-csrf'}
    assert client.post('/companies_delete/ng',data=data).status_code==302
    assert client.post('/companies_delete/ng',data=dict(data,name='（株） テストNG')).status_code==302
    assert len(client.get('/companies_delete/ng').json['companies'])==1
    with create_app(dict(app.config)).app_context():
        assert matching_rule(store().read(),{'company_name':'テストNG'})
        assert matching_rule(store().read(),{},url='https://example.com/contact')
    html=client.get('/companies_delete/').text
    assert 'NG企業一覧（送信禁止）' in html and '株式会社テストNG' in html
    assert app.test_client().get('/companies_delete/ng',headers={'X-Requested-With':'fetch'}).status_code==401
