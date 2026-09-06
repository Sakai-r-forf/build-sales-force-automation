"""Saved scrape entry points, separate from collected companies."""
import hashlib
from flask import current_app
from services.network import validate_public_url
from services.store import canonical_url, now, store


def list_sources():
    return sorted(store().read().get('sources', {}).values(), key=lambda r: r['name'].casefold())


def save_source(name, url):
    if not isinstance(name, str) or not isinstance(url, str):
        raise ValueError('登録名とURLを入力してください。')
    name = name.strip()
    if not name or len(name) > 100 or len(url) > 2048:
        raise ValueError('登録名は1〜100文字、URLは2048文字以内で入力してください。')
    url = canonical_url(url)
    validate_public_url(url, current_app.config['ALLOW_LOOPBACK'])
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    def write(state):
        sources = state.setdefault('sources', {})
        if key not in sources and len(sources) >= 200:
            raise ValueError('登録できるURLは200件までです。')
        record = {'id': key, 'name': name, 'url': url,
                  'created_at': sources.get(key, {}).get('created_at') or now(), 'updated_at': now()}
        sources[key] = record
        return dict(record)
    return store().mutate(write)


def delete_source(key):
    return store().mutate(lambda state: state.setdefault('sources', {}).pop(key, None) is not None)
