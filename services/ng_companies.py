"""Persistent do-not-contact rules, shared by collection and delivery."""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit
from services.store import now, store


def normalize_name(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r'株式会社|有限会社|合同会社|合資会社|合名会社|\(\s*(?:株|有|同)\s*\)', '', value)
    return ''.join(c for c in value if not c.isspace() and unicodedata.category(c)[0] not in 'PSZC')


def domain_name(value):
    value = str(value or '').strip()
    parsed = urlsplit(value if '://' in value else 'https://' + value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('会社公式サイトのURLを確認してください。')
    host = parsed.hostname.rstrip('.').lower().removeprefix('www.')
    if '.' not in host or any(c.isspace() for c in host):
        raise ValueError('会社公式サイトのURLを確認してください。')
    return host.encode('idna').decode('ascii')


def matching_rule(state, record, *, url='', title=''):
    names = [normalize_name(record.get('company_name')), normalize_name(title)]
    hosts = []
    for value in (record.get('company_site'), record.get('homepage_url'), record.get('inquiry_url'), record.get('contact_url'), url):
        if value:
            try: hosts.append(domain_name(value))
            except ValueError: pass
    for rule in state.get('ng_companies', {}).values():
        aliases = [normalize_name(rule['name']), *[normalize_name(a) for a in rule.get('aliases', [])]]
        if any(alias and alias in name for alias in aliases for name in names):
            return rule
        if any(host == domain or host.endswith('.' + domain) for host in hosts for domain in rule.get('domains', [])):
            return rule
    return None


def list_ng():
    return sorted(store().read().get('ng_companies', {}).values(), key=lambda row: row['created_at'])


def register_ng(name, *, domains=None, aliases=None, reason='送信禁止企業', created_by=''):
    if not isinstance(name, str) or not 2 <= len(normalize_name(name)) <= 100 or len(name) > 200:
        raise ValueError('NG企業名を2〜100文字程度で入力してください。')
    name = name.strip()
    domains = sorted(set(domain_name(d) for d in (domains or []) if d))
    aliases = [a.strip() for a in (aliases or []) if a.strip()]
    key = hashlib.sha256(normalize_name(name).encode()).hexdigest()[:24]
    def write(state):
        rules = state.setdefault('ng_companies', {})
        previous = rules.get(key, {})
        if key not in rules and len(rules) >= 2000:
            raise ValueError('NG企業の登録上限に達しました。管理者へご連絡ください。')
        rule = dict(previous, id=key, name=previous.get('name') or name,
                    domains=sorted(set(previous.get('domains', []) + domains)),
                    aliases=sorted(set(previous.get('aliases', []) + aliases)),
                    reason=previous.get('reason') or reason, created_by=previous.get('created_by') or created_by,
                    created_at=previous.get('created_at') or now(), updated_at=now())
        rules[key] = rule
        # Existing records stay archived, preserving prior delivery history.
        for company in state['companies'].values():
            if matching_rule({'ng_companies': {key: rule}}, company):
                company.update(excluded=True, excluded_at=company.get('excluded_at') or now(), ng_rule_id=key)
        return dict(rule)
    return store().mutate(write)
