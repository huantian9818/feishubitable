from __future__ import annotations

from datetime import datetime, timedelta
import importlib
import json
import threading
import time

import httpx

from app.clock import utc_now


class FeishuApiError(RuntimeError):
    pass


def load_app_credentials() -> tuple[str, str]:
    from app.db import SessionLocal
    from app.models import AppSetting

    with SessionLocal() as session:
        setting = session.query(AppSetting).order_by(AppSetting.id).first()

    app_id = setting.app_id if setting is not None else None
    app_secret = setting.app_secret if setting is not None else None
    if not app_id or not app_secret:
        raise FeishuApiError("App ID / App Secret not configured")
    return app_id, app_secret


class FeishuBitableClient:
    MAX_ATTEMPTS = 3
    BASE_BACKOFF_SECONDS = 0.5
    MIN_REQUEST_INTERVAL_SECONDS = 0.1

    _shared_token_cache: dict[tuple[str, str], tuple[str, datetime]] = {}
    _cache_lock = threading.Lock()
    _rate_limit_lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(self, app_id: str | None = None, app_secret: str | None = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self._uses_dynamic_credentials = not (app_id and app_secret)
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    def _ensure_credentials(self) -> tuple[str, str]:
        if not self._uses_dynamic_credentials and self.app_id and self.app_secret:
            return self.app_id, self.app_secret

        app_id, app_secret = load_app_credentials()
        self.app_id = app_id
        self.app_secret = app_secret
        return app_id, app_secret

    def _cache_key(self) -> tuple[str, str]:
        app_id, app_secret = self._ensure_credentials()
        return (app_id, app_secret)

    def _load_cached_token(self) -> str | None:
        with self._cache_lock:
            cached = self._shared_token_cache.get(self._cache_key())

        if cached is None:
            return None

        token, expiry = cached
        if utc_now() >= expiry:
            with self._cache_lock:
                self._shared_token_cache.pop(self._cache_key(), None)
            return None

        self._token = token
        self._token_expiry = expiry
        return token

    def _store_cached_token(self, token: str, expiry: datetime) -> None:
        self._token = token
        self._token_expiry = expiry
        with self._cache_lock:
            self._shared_token_cache[self._cache_key()] = (token, expiry)

    @classmethod
    def _apply_rate_limit(cls) -> None:
        with cls._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - cls._last_request_at
            if elapsed < cls.MIN_REQUEST_INTERVAL_SECONDS:
                time.sleep(cls.MIN_REQUEST_INTERVAL_SECONDS - elapsed)
                now = time.monotonic()
            cls._last_request_at = now

    @staticmethod
    def _http_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict) and payload.get("msg"):
            return str(payload["msg"])
        return f"HTTP {response.status_code} from Feishu API"

    def _request_json(self, request_func, url: str, **kwargs) -> dict:
        backoff = self.BASE_BACKOFF_SECONDS
        last_exc = None

        for attempt in range(self.MAX_ATTEMPTS):
            self._apply_rate_limit()
            try:
                response = request_func(url, timeout=30.0, **kwargs)
                if response.status_code >= 500 or response.status_code == 429:
                    raise httpx.HTTPError(self._http_error_message(response))
                if response.status_code >= 400:
                    raise FeishuApiError(self._http_error_message(response))
                return response.json()
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == self.MAX_ATTEMPTS - 1:
                    break
                time.sleep(backoff)
                backoff *= 2

        raise FeishuApiError(str(last_exc) if last_exc else "Feishu request failed")

    def get_tenant_access_token(self) -> str:
        if self._token and self._token_expiry and utc_now() < self._token_expiry:
            return self._token

        cached_token = self._load_cached_token()
        if cached_token is not None:
            return cached_token

        app_id, app_secret = self._ensure_credentials()
        payload = self._request_json(
            httpx.post,
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        if payload.get("code") != 0:
            raise FeishuApiError(payload.get("msg", "Unable to fetch tenant_access_token"))

        token = payload["tenant_access_token"]
        expiry = utc_now() + timedelta(seconds=payload.get("expire", 7200) - 60)
        self._store_cached_token(token, expiry)
        return token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_tenant_access_token()}"}

    def _paginate_get(self, url: str, *, params: dict | None = None, error_message: str) -> list[dict]:
        merged_items = []
        next_params = dict(params or {})

        while True:
            payload = self._request_json(httpx.get, url, headers=self._headers(), params=next_params or None)
            if payload.get("code") != 0:
                raise FeishuApiError(payload.get("msg", error_message))

            data = payload.get("data", {})
            merged_items.extend(data.get("items", []))

            if not data.get("has_more"):
                return merged_items

            next_params["page_token"] = data["page_token"]

    def get_bitable_meta(self, app_token: str) -> dict:
        payload = self._request_json(
            httpx.get,
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}",
            headers=self._headers(),
        )
        if payload.get("code") != 0:
            raise FeishuApiError(payload.get("msg", "Failed to fetch bitable metadata"))
        return payload.get("data", {})

    def resolve_wiki_node(self, wiki_token: str) -> dict:
        payload = self._request_json(
            httpx.get,
            "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node",
            headers=self._headers(),
            params={"token": wiki_token},
        )
        if payload.get("code") != 0:
            raise FeishuApiError(payload.get("msg", "Failed to resolve wiki node"))
        return payload.get("data", {}).get("node", {})

    def get_bitable_tables(self, app_token: str) -> list[dict]:
        return self._paginate_get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables",
            error_message="Failed to fetch bitable tables",
        )

    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict]:
        return self._paginate_get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            error_message="Failed to fetch bitable records",
        )

    def get_bitable_record(self, app_token: str, table_id: str, record_id: str) -> dict:
        payload = self._request_json(
            httpx.get,
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers=self._headers(),
        )
        if payload.get("code") != 0:
            raise FeishuApiError(payload.get("msg", "Failed to fetch bitable record"))
        return payload.get("data", {}).get("record", {})

    def refresh_bitable_subscription(self, app_token: str) -> dict | None:
        payload = self._request_json(
            httpx.post,
            f"https://open.feishu.cn/open-apis/drive/v1/files/{app_token}/subscribe",
            headers=self._headers(),
            params={"file_type": "bitable"},
        )
        if payload.get("code") != 0:
            raise FeishuApiError(payload.get("msg", "Failed to subscribe bitable"))
        return payload

    def subscribe_bitable(self, app_token: str) -> dict | None:
        return self.refresh_bitable_subscription(app_token)

    @staticmethod
    def _load_lark_oapi():
        return importlib.import_module("lark_oapi")

    def listen_bitable_record_events(self, callback) -> None:
        lark = self._load_lark_oapi()
        app_id, app_secret = self._ensure_credentials()

        def _handle(data) -> None:
            payload = data if isinstance(data, dict) else json.loads(lark.JSON.marshal(data))
            callback(payload)

        builder = lark.EventDispatcherHandler.builder("", "")
        if hasattr(builder, "register_p2_drive_file_bitable_record_changed_v1"):
            builder = builder.register_p2_drive_file_bitable_record_changed_v1(_handle)
        if hasattr(builder, "register_p2_drive_file_bitable_field_changed_v1"):
            builder = builder.register_p2_drive_file_bitable_field_changed_v1(_handle)

        client = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=builder.build(),
            log_level=lark.LogLevel.INFO,
        )
        client.start()
