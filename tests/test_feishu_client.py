def test_get_tenant_access_token_fetches_and_caches(monkeypatch):
    from app.clients.feishu import FeishuBitableClient

    FeishuBitableClient._shared_token_cache = {}
    FeishuBitableClient._last_request_at = 0.0
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 0, "tenant_access_token": "tenant-token", "expire": 7200}

    def fake_post(url, timeout, json):
        calls.append((url, json))
        return FakeResponse()

    monkeypatch.setattr("app.clients.feishu.httpx.post", fake_post)

    client = FeishuBitableClient(app_id="cli_x", app_secret="secret_x")

    assert client.get_tenant_access_token() == "tenant-token"
    assert client.get_tenant_access_token() == "tenant-token"
    assert len(calls) == 1


def test_get_bitable_tables_follows_pagination(monkeypatch):
    from app.clients.feishu import FeishuBitableClient

    FeishuBitableClient._shared_token_cache = {}
    FeishuBitableClient._last_request_at = 0.0
    request_params = []
    payloads = [
        {
            "code": 0,
            "data": {
                "items": [{"table_id": "tbl1", "name": "员工表"}],
                "has_more": True,
                "page_token": "next-token",
            },
        },
        {
            "code": 0,
            "data": {
                "items": [{"table_id": "tbl2", "name": "资产表"}],
                "has_more": False,
            },
        },
    ]

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, timeout, headers=None, params=None):
        request_params.append(params or {})
        return FakeResponse(payloads.pop(0))

    monkeypatch.setattr("app.clients.feishu.httpx.get", fake_get)

    client = FeishuBitableClient(app_id="cli_x", app_secret="secret_x")
    monkeypatch.setattr(client, "get_tenant_access_token", lambda: "tenant-token")

    tables = client.get_bitable_tables("app_123")

    assert tables == [
        {"table_id": "tbl1", "name": "员工表"},
        {"table_id": "tbl2", "name": "资产表"},
    ]
    assert request_params == [{}, {"page_token": "next-token"}]


def test_resolve_wiki_node(monkeypatch):
    from app.clients.feishu import FeishuBitableClient

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "code": 0,
                "data": {
                    "node": {
                        "title": "账号管理",
                        "obj_type": "bitable",
                        "obj_token": "app_from_wiki",
                    }
                },
            }

    def fake_get(url, timeout, headers=None, params=None):
        assert params == {"token": "wiki-token"}
        return FakeResponse()

    monkeypatch.setattr("app.clients.feishu.httpx.get", fake_get)

    client = FeishuBitableClient(app_id="cli_x", app_secret="secret_x")
    monkeypatch.setattr(client, "get_tenant_access_token", lambda: "tenant-token")

    node = client.resolve_wiki_node("wiki-token")

    assert node["obj_type"] == "bitable"
    assert node["obj_token"] == "app_from_wiki"


def test_listen_bitable_record_events_registers_record_and_field_handlers(monkeypatch):
    from types import SimpleNamespace

    from app.clients.feishu import FeishuBitableClient

    registered = []
    started = []

    class FakeBuilder:
        def register_p2_drive_file_bitable_record_changed_v1(self, handler):
            registered.append(("record", handler))
            return self

        def register_p2_drive_file_bitable_field_changed_v1(self, handler):
            registered.append(("field", handler))
            return self

        def build(self):
            return "event-handler"

    class FakeWsClient:
        def __init__(self, app_id, app_secret, event_handler, log_level):
            started.append((app_id, app_secret, event_handler, log_level))

        def start(self):
            started.append("started")

    fake_lark = SimpleNamespace(
        JSON=SimpleNamespace(marshal=lambda data: data),
        LogLevel=SimpleNamespace(INFO="info"),
        EventDispatcherHandler=SimpleNamespace(builder=lambda *_args: FakeBuilder()),
        ws=SimpleNamespace(Client=FakeWsClient),
    )

    client = FeishuBitableClient(app_id="cli_x", app_secret="secret_x")
    monkeypatch.setattr(client, "_load_lark_oapi", lambda: fake_lark)

    client.listen_bitable_record_events(lambda payload: payload)

    assert [name for name, _handler in registered] == ["record", "field"]
    assert started[0] == ("cli_x", "secret_x", "event-handler", "info")
    assert started[1] == "started"


def test_client_without_explicit_credentials_reloads_settings(monkeypatch):
    from app.clients.feishu import FeishuBitableClient

    credentials = [("cli_old", "secret_old"), ("cli_new", "secret_new")]
    monkeypatch.setattr(
        "app.clients.feishu.load_app_credentials",
        lambda: credentials.pop(0),
    )

    client = FeishuBitableClient()

    assert client._ensure_credentials() == ("cli_old", "secret_old")
    assert client._ensure_credentials() == ("cli_new", "secret_new")
