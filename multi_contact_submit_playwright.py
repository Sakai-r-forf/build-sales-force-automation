from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout


# ========= 設定（ここだけ書き換えれば運用できる） =============================

@dataclass
class Payload:
    name: str
    company: str
    email: str
    tel: str = ""
    subject: str = ""
    message: str = ""


@dataclass
class SiteConfig:
    name: str
    base_url: str
    # “お問い合わせ”ページへの到達方法
    contact_link_texts: Sequence[str] = ("お問い合わせ", "お問合せ", "CONTACT", "Contact")
    go_direct_contact_path: Optional[str] = None  # 例: "/contact"
    # 入力欄のヒント（ラベル/placeholder/name/id で順にマッチ）
    field_hints: Dict[str, Sequence[str]] = field(default_factory=dict)
    # ボタンの文言（1回目: 確認 2回目: 送信 の順で同じ配列を使う）
    submit_texts: Sequence[str] = ("確認", "送信", "同意して送信", "Submit", "SEND")
    # 送信成功判定（本文/URLの両方で見ると確度が上がる）
    thanks_keywords: Sequence[str] = ("ありがとうございました", "送信しました", "送信が完了", "thank you", "thanks")
    thanks_url_keywords: Sequence[str] = ("/thanks", "/complete", "/done", "/finish")
    # 画面・待ち時間
    timeout_ms: int = 12000
    slow_mo_ms: int = 60
    headless: bool = False  # 本番は True に


# --- 送信したい内容（固定値） ---
DEFAULT_PAYLOAD = Payload(
    name="山田 太郎",
    company="株式会社サンプル",
    email="taro@example.com",
    tel="03-1234-5678",
    subject="床鳴り対策のご提案",
    message="はじめまして。御社の床鳴り対策についてご提案です。..."
)

# --- サイトの設定（今は1件。将来は配列に増やせばそのまま回せる） ---
SITES: List[SiteConfig] = [
    SiteConfig(
        name="FORF",
        base_url="https://www.forf.jp/",
        # 直リンクできるなら指定（無ければコメントアウト）
        go_direct_contact_path=None,
        # サイト固有のラベル語を必要に応じて追加
        field_hints={
            "name":    ("お名前", "氏名", "担当者", "name"),
            "company": ("会社名", "御社名", "貴社名", "company"),
            "email":   ("メール", "メールアドレス", "e-mail", "email"),
            "tel":     ("電話", "電話番号", "TEL", "tel"),
            "subject": ("件名", "タイトル", "subject"),
            "message": ("お問い合わせ内容", "本文", "お問い合わせ", "メッセージ", "message"),
            "agree":   ("同意", "個人情報", "プライバシー", "規約", "agree", "consent"),
        },
        submit_texts=("確認", "送信", "同意して送信", "Submit", "SEND"),
        headless=False,  # まずは画面表示で確認
    ),
]


# ========= 共通ロジック（将来“複数サイト”そのまま対応） ========================

def _merged_hints(site: SiteConfig) -> Dict[str, Sequence[str]]:
    base = {
        "name":    ("お名前", "氏名", "ご担当者", "担当者", "name"),
        "company": ("会社名", "御社名", "貴社名", "法人名", "組織名", "company"),
        "email":   ("メール", "メールアドレス", "e-mail", "email"),
        "tel":     ("電話", "電話番号", "TEL", "tel"),
        "subject": ("件名", "タイトル", "subject"),
        "message": ("お問い合わせ内容", "本文", "内容", "メッセージ", "お問い合わせ", "message"),
        "agree":   ("同意", "個人情報", "プライバシー", "規約", "agree", "consent"),
    }
    for k, v in site.field_hints.items():
        base[k] = tuple(v)  # サイト指定で置き換え
    return base


async def _goto_contact(page: Page, site: SiteConfig) -> None:
    if site.go_direct_contact_path:
        await page.goto(site.base_url.rstrip("/") + "/" + site.go_direct_contact_path.lstrip("/"))
        return

    await page.goto(site.base_url)
    # リンクテキストで探す
    for txt in site.contact_link_texts:
        loc = page.get_by_role("link", name=txt, exact=False)
        if await loc.count() > 0:
            try:
                await loc.first.click(timeout=3000)
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
                return
            except PWTimeout:
                pass

    # aタグの実テキスト総当たり
    anchors = page.locator("a")
    n = await anchors.count()
    for i in range(min(n, 500)):
        a = anchors.nth(i)
        try:
            t = (await a.inner_text()).strip()
            if any(k in t for k in site.contact_link_texts):
                await a.click(timeout=3000)
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
                return
        except Exception:
            continue
    # 見つからない場合は現ページをフォームとみなす（LP直埋め対策）


async def _fill_candidate(page: Page, hints: Dict[str, Sequence[str]], key: str, value: str, timeout_ms: int) -> bool:
    if not value:
        return True
    words = hints.get(key, ())
    # label
    for w in words:
        try:
            loc = page.get_by_label(w, exact=False)
            if await loc.count() > 0:
                await loc.first.fill(value, timeout=timeout_ms)
                return True
        except Exception:
            pass
    # placeholder
    for w in words:
        try:
            loc = page.locator(f'input[placeholder*="{w}"], textarea[placeholder*="{w}"]')
            if await loc.count() > 0:
                await loc.first.fill(value, timeout=timeout_ms)
                return True
        except Exception:
            pass
    # name/id
    for w in words:
        try:
            loc = page.locator(
                f'input[name*="{w}"], textarea[name*="{w}"],'
                f'input[id*="{w}"], textarea[id*="{w}"]'
            )
            if await loc.count() > 0:
                await loc.first.fill(value, timeout=timeout_ms)
                return True
        except Exception:
            pass
    # 予備：最初の空欄に入れる
    try:
        cand = page.locator("form input:not([type=hidden]), form textarea")
        c = await cand.count()
        for i in range(c):
            t = cand.nth(i)
            try:
                cur = await t.input_value()
                typ = (await t.get_attribute("type")) or ""
                if not cur and typ.lower() not in {"checkbox", "radio", "submit"}:
                    await t.fill(value, timeout=timeout_ms)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def _tick_agree(page: Page, hints: Dict[str, Sequence[str]], timeout_ms: int) -> None:
    for w in hints.get("agree", ()):
        try:
            lbl = page.get_by_label(w, exact=False)
            if await lbl.count() > 0:
                try:
                    await lbl.first.check(timeout=timeout_ms)
                    return
                except Exception:
                    pass
        except Exception:
            pass
        try:
            loc = page.locator(
                f'input[type=checkbox][name*="{w}"],'
                f'input[type=checkbox][id*="{w}"],'
                f'input[type=checkbox][aria-label*="{w}"]'
            )
            if await loc.count() > 0:
                try:
                    await loc.first.check(timeout=timeout_ms)
                    return
                except Exception:
                    pass
        except Exception:
            pass


async def _click_submit(page: Page, texts: Sequence[str], timeout_ms: int) -> bool:
    for txt in texts:
        try:
            btn = page.get_by_role("button", name=txt, exact=False)
            if await btn.count() > 0:
                await btn.first.click(timeout=timeout_ms)
                return True
        except Exception:
            pass
        try:
            btn = page.locator(f'input[type=submit][value*="{txt}"], button:has-text("{txt}")')
            if await btn.count() > 0:
                await btn.first.click(timeout=timeout_ms)
                return True
        except Exception:
            pass
    # 予備
    try:
        btn = page.locator("form button[type=submit], form input[type=submit]")
        if await btn.count() > 0:
            await btn.first.click(timeout=timeout_ms)
            return True
    except Exception:
        pass
    return False


async def submit_one(site: SiteConfig, payload: Payload) -> bool:
    """単一サイトに送信。成功なら True。"""
    hints = _merged_hints(site)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=site.headless, slow_mo=site.slow_mo_ms)
        ctx = await browser.new_context(locale="ja-JP")
        page = await ctx.new_page()
        page.set_default_timeout(site.timeout_ms)

        await _goto_contact(page, site)

        ok = True
        ok &= await _fill_candidate(page, hints, "name",    payload.name,    site.timeout_ms)
        ok &= await _fill_candidate(page, hints, "company", payload.company, site.timeout_ms)
        ok &= await _fill_candidate(page, hints, "email",   payload.email,   site.timeout_ms)
        ok &= await _fill_candidate(page, hints, "tel",     payload.tel,     site.timeout_ms)
        ok &= await _fill_candidate(page, hints, "subject", payload.subject, site.timeout_ms)
        ok &= await _fill_candidate(page, hints, "message", payload.message, site.timeout_ms)
        await _tick_agree(page, hints, site.timeout_ms)

        # 確認→送信（2段階想定。サイトによっては1回で終わる）
        submitted = await _click_submit(page, site.submit_texts, site.timeout_ms)
        if submitted:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=site.timeout_ms)
            except PWTimeout:
                pass
            submitted = await _click_submit(page, site.submit_texts, site.timeout_ms) or submitted

        # 成功判定（本文 or URL）
        try:
            await page.wait_for_load_state("networkidle", timeout=site.timeout_ms)
        except PWTimeout:
            pass
        html = (await page.content()).lower()
        url = page.url.lower()
        success = ok and submitted and (
            any(k.lower() in html for k in site.thanks_keywords) or
            any(k in url for k in site.thanks_url_keywords)
        )

        await ctx.close(); await browser.close()
        return bool(success)


# ========= エントリポイント（コード内の値で自動送信） ===========================

async def _amain() -> int:
    # 将来: SITES に複数並べれば for で回る
    site = SITES[0]
    print(f"[TRY] {site.name} ({site.base_url})")
    success = await submit_one(site, DEFAULT_PAYLOAD)
    print(" ->", "SUCCESS" if success else "FAILED")
    return 0 if success else 1


if __name__ == "__main__":
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass