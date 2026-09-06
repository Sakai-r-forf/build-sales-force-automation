import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from werkzeug.security import generate_password_hash
from app import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "STATE_PATH": str(tmp_path / 'state.json'), "SECRET_KEY": "test-secret", "GCS_BUCKET": "", "ALLOW_LOOPBACK": True})
    app.extensions['state_store'].mutate(lambda s:s['users'].update({'test@example.com': {'id':'test@example.com','email':'test@example.com','password_hash':generate_password_hash('test-password')}}))
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id']='test@example.com';session['_fresh']=True;session['csrf_token']='test-csrf'
    return client


@pytest.fixture
def payload():
    return {'name':'テスト担当者','company':'テスト株式会社','email':'test@example.com','phone':'03-0000-0000','subject':'テスト連絡','body':'動作確認のテストです。'}
