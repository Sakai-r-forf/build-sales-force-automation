"""Durable application state, with generation-checked GCS writes across instances.

Local development uses a locked, atomically replaced JSON file. Production never
uses the container filesystem for company data or delivery records.
"""
import copy
import fcntl
import hashlib
import json
import os
import tempfile
import time
import random
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import current_app


def now():
    return datetime.now(timezone.utc).isoformat()


def empty_state():
    return {"version": 1, "next_id": 1, "companies": {}, "users": {}, "settings": {}, "deliveries": {}}


class StateStore:
    def __init__(self, bucket=None, path=None, object_name="app/state-v1.json", client=None):
        self._write_lock = threading.RLock()
        self.bucket = bucket
        self.path = Path(path) if path else None
        self.object_name = object_name
        self._client = client

    def blob(self):
        if self._client is None:
            from google.cloud import storage
            self._client = storage.Client()
        return self._client.bucket(self.bucket).blob(self.object_name)

    def _cloud_read(self):
        from google.api_core.exceptions import NotFound
        blob = self.blob()
        try:
            # download_as_bytes sets generation from the same HTTP response.
            raw = blob.download_as_bytes(timeout=30)
            return json.loads(raw), int(blob.generation)
        except NotFound:
            return empty_state(), 0

    def read(self):
        if self.bucket:
            return self._cloud_read()[0]
        if not self.path.exists():
            return empty_state()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def mutate(self, operation):
        with self._write_lock:
            return self._mutate(operation)

    def _mutate(self, operation):
        """operation must be repeatable: CAS retries must never perform external I/O."""
        if self.bucket:
            from google.api_core.exceptions import PreconditionFailed
            for attempt in range(12):
                state, generation = self._cloud_read()
                result = operation(state)
                try:
                    self.blob().upload_from_string(
                        json.dumps(state, ensure_ascii=False),
                        content_type="application/json; charset=utf-8",
                        if_generation_match=generation, timeout=30,
                    )
                    return result
                except PreconditionFailed:
                    time.sleep(random.uniform(.1, min(.2 * 2**attempt, 2)))
            raise RuntimeError("保存が競合しました。時間をおいて再度操作してください。")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.path) + ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.read()
            result = operation(state)
            fd, temp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(state, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, self.path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            return result


def store():
    return current_app.extensions["state_store"]


def canonical_url(url):
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("http/https のURLを指定してください。")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def upsert_company(info):
    site = canonical_url(info.get("homepage_url") or info.get("company_site") or info.get("source_url"))
    # Ignore scheme/www differences but retain profile paths for directory-only records.
    parsed = urlsplit(site)
    identity = parsed.netloc.removeprefix("www.") + parsed.path + ("?" + parsed.query if parsed.query else "")
    key = hashlib.sha256(identity.encode()).hexdigest()
    from services.ng_companies import matching_rule
    def write(state):
        existing = next((c for c in state["companies"].values() if c["key"] == key), None)
        ng = matching_rule(state, dict(info, company_site=site))
        if ng:
            if existing:
                existing.update(excluded=True, excluded_at=now(), ng_rule_id=ng['id'])
            return None
        if existing and existing.get("excluded"):
            return None
        if existing:
            record = existing
        else:
            record = {"id": state["next_id"], "key": key, "created_at": info.get("created_at") or now(), "excluded": False}
            state["next_id"] += 1
            state["companies"][str(record["id"])] = record
        record["company_site"] = site
        for field, alias in [("company_name", "company_name"), ("inquiry_url", "contact_url"), ("email", "email"), ("phone", "phone"), ("address", "address")]:
            value = str(info.get(alias) or info.get(field) or "").strip()
            if field == "inquiry_url" and value:
                try:
                    value = canonical_url(value)
                except ValueError:
                    value = ""
            if value or field not in record:
                record[field] = value
        record["updated_at"] = now()
        return copy.deepcopy(record)
    return store().mutate(write)


def companies(search="", include_excluded=False):
    from services.ng_companies import matching_rule
    state = store().read()
    result = []
    for record in state["companies"].values():
        if (record.get("excluded") or matching_rule(state, record)) and not include_excluded:
            continue
        if search.casefold() not in record.get("company_name", "").casefold():
            continue
        record = dict(record)
        record["delivery"] = state["deliveries"].get(str(record["id"]), {})
        result.append(record)
    return sorted(result, key=lambda c: c["id"], reverse=True)


def company(company_id):
    from services.ng_companies import matching_rule
    state = store().read()
    record = state["companies"].get(str(company_id))
    if not record or record.get("excluded") or matching_rule(state, record):
        return None
    return dict(record, delivery=state["deliveries"].get(str(company_id), {}))


def exclude_company(company_id):
    def write(state):
        record = state["companies"].get(str(company_id))
        if not record:
            return False
        record["excluded"] = True
        record["excluded_at"] = now()
        return True
    return store().mutate(write)
