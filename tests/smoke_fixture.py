"""Disposable deployment verification server. It never sends email or stores bodies."""
import os
import secrets
from flask import Flask, request, abort, jsonify

app=Flask(__name__)
TOKEN=os.environ.get('FIXTURE_TOKEN') or secrets.token_urlsafe(32)
received=0


def check(token):
    if not secrets.compare_digest(token,TOKEN):abort(404)


@app.get('/<token>/directory')
def directory(token):
    check(token)
    return f'<meta charset="utf-8"><a href="/{token}/company">株式会社動作確認専用</a>'


@app.get('/<token>/company')
def company(token):
    check(token)
    return f'<meta charset="utf-8"><h1>株式会社動作確認専用</h1><p>これは営業先ではなくシステム検証用です。</p><a href="/{token}/form">お問い合わせ</a>'


@app.route('/<token>/form',methods=['GET','POST'])
def form(token):
    check(token)
    global received
    if request.method=='POST':
        if request.form.get('email')!='test@example.com':abort(400)
        if not all(request.form.get(k) for k in ('name','company','message','email','phone')):abort(400)
        received+=1
        return '<meta charset="utf-8"><h1>お問い合わせありがとうございます。送信が完了しました。</h1>'
    return '''<meta charset="utf-8"><h1>検証専用フォーム</h1><form method="post">
<label>お名前<input name="name" required></label>
<label>会社名<input name="company" required></label>
<label>メール<input name="email" type="email" required></label>
<label>電話番号<input name="phone" type="tel" required></label>
<label>件名<input name="subject" required></label>
<label>お問い合わせ内容<textarea name="message" required></textarea></label>
<button type="submit">送信する</button></form>'''


@app.get('/<token>/result')
def result(token):
    check(token)
    return jsonify(received=received)


if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','8080')))
