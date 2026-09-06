import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from services.playwright_submit import submit_contact, field_key
from services.scraper import crawl_and_export,get_stats
from services.store import companies

FORM='''<html lang="ja"><meta charset="utf-8"><h1>株式会社テスト建設</h1><form method="post" action="/thanks"><label>氏名<input name="name" required></label><label>会社名<input name="company" required></label><label>メール<input type="email" name="email" required></label><label>メール確認<input name="email_confirmation" required></label><label>電話番号<input type="tel" name="tel" required></label><label>件名<input name="subject" required></label><label>お問い合わせ内容<textarea name="message" required></textarea></label><label><input type="checkbox" name="privacy" required>個人情報に同意する</label><button type="submit">送信する</button></form></html>'''


@pytest.fixture
def server():
    submissions=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
            if self.path=='/directory':body='<a href="/company">株式会社テスト建設</a>'
            elif self.path=='/company':body='<h1>株式会社テスト建設</h1><p>床工事・東京都</p><a href="/form">お問い合わせ</a><a href="mailto:test@example.com">メール</a>'
            elif self.path=='/captcha':body='<div class="g-recaptcha" data-sitekey="test"></div>'+FORM
            elif self.path=='/missing':body=FORM.replace('<button','<input name="unknown" required><button')
            elif self.path=='/confirm':body=FORM.replace('/thanks','/confirmation')
            else:body=FORM
            self.wfile.write(body.encode())
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']));submissions.append((self.path,body))
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
            if self.path=='/confirmation':result='<meta charset="utf-8"><h1>入力内容の確認</h1><form method="POST" action="/thanks"><button>送信する</button></form>'
            else:result='<meta charset="utf-8"><h1>お問い合わせありがとうございます。送信が完了しました。</h1>'
            self.wfile.write(result.encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',submissions
    server.shutdown();server.server_close()


def test_field_mapping():
    assert field_key('email-confirm')=='email'
    assert field_key('会社名')=='company'
    assert field_key('ご担当者様のお名前')=='name'


@pytest.mark.parametrize('path,expected,posts',[('/form','sent',1),('/confirm','sent',2),('/captcha','manual_required',0),('/missing','manual_required',0)])
def test_real_browser_forms(server,payload,path,expected,posts):
    base,submissions=server
    marks=[]
    result=submit_contact(base+path,payload,lambda:marks.append(1),allow_loopback=True)
    assert result.status==expected,result
    assert len(submissions)==posts
    assert len(marks)==posts


def test_real_crawl_saves_and_exports(app,server):
    base,_=server
    with app.app_context():
        path=crawl_and_export(base+'/directory',limit=5,max_pages=5,jp_keywords='床工事,埼玉県')
        assert len(companies())>=1
        assert companies()[0]['inquiry_url']==base+'/form'
        assert get_stats()['total']>=1
        with open(path,encoding='utf-8-sig') as f:assert '株式会社テスト建設' in f.read()
        os.unlink(path)


def test_internal_targets_blocked(payload):
    result=submit_contact('http://169.254.169.254/',payload,lambda:None)
    assert result.status=='failed'
