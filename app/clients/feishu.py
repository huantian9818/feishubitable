from __future__ import annotations


class FeishuBitableClient:
    """Minimal Feishu Bitable client interface for sync services."""

    def get_bitable_meta(self, app_token: str) -> dict:
        raise NotImplementedError

    def get_bitable_tables(self, app_token: str) -> list[dict]:
        raise NotImplementedError

    def list_bitable_records(self, app_token: str, table_id: str) -> list[dict]:
        raise NotImplementedError

    def get_bitable_record(self, app_token: str, table_id: str, record_id: str) -> dict:
        raise NotImplementedError

    def refresh_bitable_subscription(self, app_token: str) -> dict | None:
        raise NotImplementedError

    def subscribe_bitable(self, app_token: str) -> dict | None:
        return self.refresh_bitable_subscription(app_token)
