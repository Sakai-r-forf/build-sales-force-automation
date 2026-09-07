import copy
import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit
from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required, current_user
from services.store import store, now
from services.ng_companies import matching_rule
from services.playwright_submit import submit_contact

deliveries_bp = Blueprint("deliveries", __name__)
FIELDS = ("name", "company", "email", "phone", "kana", "postal_code", "address", "subject", "body")


def validate_payload(raw):
    if not isinstance(raw, dict):
        raise ValueError("送信内容を入力してください。")
    data = {key: str(raw.get(key) or "").strip() for key in FIELDS}
    if any(not data[k] for k in ("name", "company", "email", "phone", "subject", "body")):
        raise ValueError("送信者名・会社名・返信先・電話番号・件名・本文を入力してください。")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", data["email"]):
        raise ValueError("返信先メールアドレスを確認してください。")
    if len(data["body"]) > 10000 or any(len(data[k]) > 500 for k in FIELDS if k != "body"):
        raise ValueError("入力内容が長すぎます。")
    return data


@deliveries_bp.get("/settings")
@login_required
def settings():
    return jsonify(store().read()["settings"])


@deliveries_bp.post("/settings")
@login_required
def save_settings():
    try:
        data = validate_payload(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    store().mutate(lambda state: state["settings"].update(data))
    return jsonify(saved=True)


@deliveries_bp.post("/<int:company_id>/send")
@login_required
def send(company_id):
    try:
        data = validate_payload(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    state_store = store()  # Playwright callbacks run outside Flask context-local state.
    attempt_id = uuid.uuid4().hex
    user_id = current_user.get_id()
    def claim(state):
        company = state["companies"].get(str(company_id))
        ng = matching_rule(state, company or {})
        if ng:
            raise ValueError('NG企業「' + ng['name'] + '」への送信は禁止されています。')
        if not company or company.get("excluded"):
            raise ValueError("対象企業が存在しないか、送信対象から除外されています。")
        if not company.get("inquiry_url"):
            raise ValueError("お問い合わせURLがありません。")
        parsed = urlsplit(company["inquiry_url"])
        target_key = parsed.netloc.lower().removeprefix("www.") + parsed.path.rstrip("/") + ("?" + parsed.query if parsed.query else "")
        for saved in state["deliveries"].values():
            if saved.get("target_key") == target_key and saved.get("status") in ("sent", "sending", "unknown"):
                raise ValueError("同じお問い合わせフォームへの送信履歴があるため、重複送信を停止しました。")
        previous = state["deliveries"].get(str(company_id), {})
        if previous.get("status") in ("sent", "sending", "unknown"):
            raise ValueError("送信済み、処理中、または結果が不明のため再送できません。")
        rendered = dict(data, body=data["body"].replace("{company_name}", company.get("company_name") or "ご担当者様"))
        state["deliveries"][str(company_id)] = {
            "id": attempt_id, "status": "sending", "started_at": now(), "user_id": user_id,
            "message": "送信処理中です。", "target_url": company["inquiry_url"], "target_key": target_key,
            "payload": rendered, "payload_hash": hashlib.sha256(json.dumps(rendered, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "history": previous.get("history", []) + ([{k:v for k,v in previous.items() if k != "history"}] if previous else []),
        }
        return copy.deepcopy(company), rendered
    try:
        company, rendered = store().mutate(claim)
    except ValueError as error:
        return jsonify(error=str(error)), 409
    except Exception:
        current_app.logger.exception("Unable to reserve delivery")
        return jsonify(error="送信記録を保存できないため、送信を開始しませんでした。"), 503

    def before_submit():
        def mark(state):
            record = state["companies"].get(str(company_id), {})
            delivery = state["deliveries"].get(str(company_id), {})
            if not record or record.get("excluded") or matching_rule(state, record) or delivery.get("id") != attempt_id or delivery.get("status") != "sending":
                raise ValueError("送信対象の状態が変わったため停止しました。")
            delivery["submitted_at"] = now()
        store().mutate(mark)

    def check_target(url, title=''):
        state = state_store.read()
        record = state['companies'].get(str(company_id), {})
        ng = matching_rule(state, record, url=url, title=title)
        if ng:
            raise ValueError('NG企業「' + ng['name'] + '」への送信は禁止されています。')
        if not record or record.get('excluded'):
            raise ValueError('送信対象から除外されたため停止しました。')

    result = submit_contact(company["inquiry_url"], rendered, before_submit,
                            allow_loopback=current_app.config["ALLOW_LOOPBACK"], check_target=check_target)
    def finish(state):
        delivery = state["deliveries"][str(company_id)]
        if delivery["id"] != attempt_id:
            raise ValueError("送信記録が競合しています。")
        delivery.update(status=result.status, message=result.message, finished_at=now())
    try:
        store().mutate(finish)
    except Exception:
        current_app.logger.exception("Unable to finalize delivery; do not retry")
        return jsonify(status="unknown", message="送信結果の保存に失敗しました。再送せず送信先で結果を確認してください。"), 503
    return jsonify(status=result.status, message=result.message)
