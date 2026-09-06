"""Restrict server-side browsing to public HTTP(S) destinations."""
import ipaddress
import socket
from urllib.parse import urlsplit


def validate_public_url(url, allow_loopback=False):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("公開された http/https のURLを指定してください。")
    if parsed.port not in (None, 80, 443) and not allow_loopback:
        raise ValueError("標準のHTTP/HTTPSポートのURLを指定してください。")
    try:
        addresses = {r[4][0] for r in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("サイトの接続先を確認できません。URLを確認してください。") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global and not (allow_loopback and ip.is_loopback):
            raise ValueError("内部ネットワークのURLは利用できません。")
    return url
