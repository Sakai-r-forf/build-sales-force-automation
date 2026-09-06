"""Conservative contact-form submission. Ambiguous outcomes are never retried."""
import re
import os
import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin
from services.network import validate_public_url


@dataclass
class Result:
    status: str
    message: str


FIELD_RULES = [
    ("email", r"email|e-mail|メール"),
    ("phone", r"tel|phone|電話"),
    ("postal_code", r"郵便|postal|zip"),
    ("address", r"住所|所在地|address"),
    ("company", r"会社|法人|company|organization|organisation"),
    ("kana", r"フリガナ|ふりがな|カナ|kana"),
    ("subject", r"件名|subject|title|題名"),
    ("name", r"名前|氏名|担当者|your.name|full.?name|^name$"),
    ("body", r"message|本文|内容|詳細|inquiry|comment"),
]
SUCCESS = re.compile(r"送信(?:が)?完了|送信されました|送信いたしました|お問い合わせ(?:を)?受け付けました|お問い合わせ(?:いただき)?ありがとう|お問合せ(?:いただき)?ありがとう|thank you for (?:contacting|your (?:message|inquiry))|message (?:has been )?sent", re.I)
CAPTCHA = 'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .g-recaptcha, .h-captcha, [data-sitekey]'


def field_key(label, kind=""):
    if kind == "email":
        return "email"
    if kind == "tel":
        return "phone"
    # Confirmation email fields deliberately get the same reply address.
    for key, pattern in FIELD_RULES:
        if re.search(pattern, label, re.I):
            return key
    return "body" if kind == "textarea" else None


def submit_contact(url, payload, before_submit, allow_loopback=False, timeout_seconds=75):
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    clicked = False
    deadline = time.monotonic() + timeout_seconds
    try:
        validate_public_url(url, allow_loopback)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None, args=["--disable-dev-shm-usage"])
            try:
                context = browser.new_context(locale="ja-JP", service_workers="block", accept_downloads=False)
                def guard(route):
                    try:
                        validate_public_url(route.request.url, allow_loopback)
                        if route.request.resource_type in ("image", "media", "font"):
                            route.abort()
                        else:
                            route.continue_()
                    except ValueError:
                        route.abort()
                context.route("**/*", guard)
                page = context.new_page()
                page.set_default_timeout(4000)
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if page.locator(CAPTCHA).count():
                    return Result("manual_required", "CAPTCHAがあるため手動送信が必要です。")
                text = page.locator("body").inner_text()
                if re.search(r"営業(?:目的|メール|の)?(?:での)?(?:お問い合わせ|連絡|送信)?(?:は|を)?(?:お断り|禁止|ご遠慮)|セールス.*お断り", text):
                    return Result("manual_required", "営業連絡を受け付けない旨の記載があるため送信しませんでした。")
                form = None
                for candidate in page.locator("form").all():
                    if any(t.is_visible() for t in candidate.locator("textarea").all()):
                        form = candidate
                        break
                if form is None:
                    return Result("manual_required", "対応可能なお問い合わせフォームを確認できません。")
                original_text = page.locator("body").inner_text()
                filled = set()
                for control in form.locator("input, textarea, select").all():
                    if not control.is_visible() or not control.is_enabled():
                        continue
                    meta = control.evaluate("""el => ({tag:el.tagName.toLowerCase(),type:el.type||'',name:el.name||'',required:el.required,readOnly:el.readOnly,label:[el.name,el.id,el.placeholder,el.getAttribute('aria-label'),...Array.from(el.labels||[]).map(x=>x.innerText)].filter(Boolean).join(' ')})""")
                    kind = meta["type"]
                    if kind in ("hidden", "submit", "button", "reset") or meta["readOnly"]:
                        continue
                    if kind == "file":
                        if meta["required"]:
                            return Result("manual_required", "添付ファイルが必須のため手動送信が必要です。")
                        continue
                    if kind in ("checkbox", "radio"):
                        if re.search(r"プライバシー|個人情報|privacy|同意|agree|consent", meta["label"], re.I) and not re.search(r"メルマガ|配信|newsletter|marketing", meta["label"], re.I):
                            control.check()
                        elif meta["required"] and not control.is_checked():
                            return Result("manual_required", "選択が必要な項目があります。手動で内容を確認してください。")
                        continue
                    if meta["tag"] == "select":
                        if meta["required"]:
                            choices = control.locator("option").all()
                            selected = next((c.get_attribute("value") for c in choices if re.search(r"その他|お問い合わせ|一般|other|general", c.inner_text(), re.I) and c.get_attribute("value")), None)
                            if selected:
                                control.select_option(selected)
                            else:
                                return Result("manual_required", "選択必須項目に適切な値を確認できません。")
                        continue
                    key = field_key(meta["label"], "textarea" if meta["tag"] == "textarea" else kind)
                    value = payload.get(key, "") if key else ""
                    if value:
                        control.fill(value)
                        filled.add(key)
                    elif meta["required"]:
                        return Result("manual_required", "未入力の必須項目があります。送信者情報を補完するか手動送信してください。")
                if not {"email", "body"}.issubset(filled):
                    return Result("manual_required", "返信先と本文を入力できるフォームではありません。")
                if not form.evaluate("el => el.checkValidity()"):
                    return Result("manual_required", "フォームの入力条件を満たしていません。分割入力などを手動で確認してください。")
                for step in range(2):
                    if time.monotonic() >= deadline:
                        return Result("unknown" if clicked else "failed", "処理がタイムアウトしました。送信先で結果を確認してください。")
                    scope = form if step == 0 else page
                    buttons = scope.locator('button, input[type="submit"], input[type="button"]')
                    submit = None
                    for button in buttons.all():
                        if not button.is_visible() or not button.is_enabled():
                            continue
                        label = (button.inner_text() or button.get_attribute("value") or "").strip()
                        if re.search(r"送信|確認|submit|send|confirm", label, re.I) and not re.search(r"戻|back|取消|キャンセル", label, re.I):
                            submit = button
                            break
                    if submit is None:
                        return Result("unknown" if clicked else "manual_required", "送信ボタンを確認できません。送信先で結果を確認してください。")
                    before_submit()  # Durable claim and exclusion recheck before each click.
                    clicked = True
                    submit.click(timeout=10000)
                    until = min(deadline, time.monotonic() + 15)
                    while time.monotonic() < until:
                        try:
                            current_text = page.locator("body").inner_text(timeout=2000)
                            # Require new success text and disappearance/reset of the message.
                            matches = SUCCESS.findall(current_text)
                            body_values = [t.input_value() for t in page.locator("textarea").all() if t.is_visible()]
                            if matches and current_text != original_text and payload["body"] not in body_values and not SUCCESS.search(original_text):
                                return Result("sent", "フォームの送信完了表示を確認しました。")
                            if step == 0 and re.search(r"入力内容(?:の)?確認|確認画面|以下の内容で|confirm your", current_text, re.I) and not body_values:
                                break
                            if page.locator('.wpcf7-not-valid-tip, .invalid-feedback:visible, [role="alert"]:visible').count():
                                return Result("unknown", "フォームに確認メッセージがあります。送信先で結果を確認してください。")
                        except PlaywrightTimeout:
                            pass
                        page.wait_for_timeout(250)
                    else:
                        return Result("unknown", "送信完了を確認できません。重複を防ぐため再送を停止しています。")
                return Result("unknown", "送信完了を確認できません。送信先で結果を確認してください。")
            finally:
                browser.close()
    except ValueError as error:
        return Result("unknown" if clicked else "failed", str(error))
    except Exception:
        logging.getLogger(__name__).exception("Contact form operation failed; submitted=%s", clicked)
        return Result("unknown" if clicked else "failed", "送信結果を確認できません。" if clicked else "フォームへの接続またはブラウザー処理に失敗しました。")
