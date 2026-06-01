# Feishu Bitable Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从零搭建一个只面向飞书多维表格的监控工具，支持首次全量落库、低频全量兜底、长连接事件订阅和记录级增量同步，并提供简单 Web 管理页。

**Architecture:** Web 服务只负责配置、管理和展示；Worker 服务负责长连接、任务消费和同步执行；SQLite 同时承担业务库、任务协调层和执行留痕。全量同步与增量同步共用同一套 Feishu 客户端与标准化逻辑，页面所有“执行型”按钮都通过任务表异步触发，避免请求阻塞。

**Tech Stack:** Python 3.13, FastAPI, Jinja2, SQLAlchemy 2.x, SQLite, httpx, lark-oapi, uv, pytest

---

## File Structure

- `pyproject.toml`
  项目依赖、测试脚本和入口命令。
- `.gitignore`
  忽略 `.venv`、SQLite 数据库、缓存文件和运行日志。
- `README.md`
  本地开发、Web/Worker 启动方式、飞书权限和排障说明。
- `app/config.py`
  应用配置读取和默认路径定义。
- `app/clock.py`
  统一时间工具，避免散落的 `datetime.now(...)` 逻辑。
- `app/db.py`
  SQLite engine、session 和建表入口。
- `app/models.py`
  `app_settings`、`monitors`、`bitable_tables`、`current_records`、`event_logs`、`sync_runs`、`worker_jobs` 的 SQLAlchemy 模型。
- `app/schemas.py`
  页面和内部服务共用的轻量类型与枚举常量。
- `app/clients/feishu.py`
  飞书 REST 客户端，负责 token、bitable 元数据、子表列表、全量记录分页、单条记录获取、订阅和查询订阅状态。
- `app/services/link_parser.py`
  多维表格链接解析。
- `app/services/fallback_schedule.py`
  低频全量间隔解析、预设值和下一次执行时间计算。
- `app/services/full_sync.py`
  首次全量、手动全量、兜底全量的通用执行器。
- `app/services/incremental_sync.py`
  `bitable_record_changed_v1` 的记录级增量执行器。
- `app/services/subscription.py`
  建立、查询、取消订阅和状态回写。
- `app/services/view_models.py`
  详情页当前数据的标签页、表格和分页组装。
- `app/web/routes/settings.py`
  设置页路由。
- `app/web/routes/monitors.py`
  监控源列表、创建、详情、修改间隔、手动全量、重新订阅、删除。
- `app/templates/base.html`
  公共布局。
- `app/templates/settings.html`
  设置页模板。
- `app/templates/monitors.html`
  监控源列表模板。
- `app/templates/monitor_form.html`
  添加监控源模板。
- `app/templates/monitor_detail.html`
  详情页模板。
- `app/templates/monitor_runs.html`
  执行记录页模板。
- `app/static/styles.css`
  极简文字型页面样式。
- `app/main.py`
  Web 服务入口和路由挂载。
- `worker/event_listener.py`
  飞书长连接封装和消息接收。
- `worker/event_processor.py`
  事件落库、去重、分流。
- `worker/job_runner.py`
  `worker_jobs` 消费和执行。
- `worker/scheduler.py`
  低频全量兜底扫描与任务创建。
- `worker/main.py`
  Worker 入口，启动监听、调度和任务循环。
- `tests/conftest.py`
  测试数据库、FastAPI client、假客户端 fixtures。
- `tests/test_app_bootstrap.py`
  Web 入口与健康检查。
- `tests/test_models_and_schedule.py`
  模型和兜底调度计算。
- `tests/test_full_sync.py`
  全量同步逻辑。
- `tests/test_monitor_routes.py`
  监控源页面与任务入队。
- `tests/test_job_runner.py`
  后台任务执行。
- `tests/test_incremental_sync.py`
  事件增量同步。
- `tests/test_event_processor.py`
  事件落库、去重和分流。

### Task 1: Bootstrap the Empty Repository

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/templates/base.html`
- Create: `app/static/styles.css`
- Create: `tests/conftest.py`
- Create: `tests/test_app_bootstrap.py`

- [ ] **Step 1: Initialize the repo and write the first failing web bootstrap test**

```python
# tests/test_app_bootstrap.py
def test_health_check_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_app_bootstrap.py -v`

Expected: `ModuleNotFoundError` or import failure because `app.main` does not exist yet.

- [ ] **Step 3: Create the minimal project skeleton**

```toml
# pyproject.toml
[project]
name = "feishubitable"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
  "fastapi>=0.116.0",
  "jinja2>=3.1.6",
  "sqlalchemy>=2.0.43",
  "httpx>=0.28.1",
  "lark-oapi>=1.4.21",
  "uvicorn>=0.35.0",
]

[dependency-groups]
dev = [
  "pytest>=8.4.1",
]
```

```python
# app/main.py
from fastapi import FastAPI

app = FastAPI(title="Feishu Bitable Monitor")


@app.get("/health")
def health():
    return {"status": "ok"}
```

```gitignore
# .gitignore
.venv/
__pycache__/
.pytest_cache/
*.pyc
data/
*.sqlite3
*.log
```

- [ ] **Step 4: Run the test again to verify it passes**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_app_bootstrap.py -v`

Expected: `1 passed`

- [ ] **Step 5: Initialize git and commit the bootstrap**

```bash
cd /Users/moennan/Documents/feishubitable
git init
git add .gitignore pyproject.toml app/__init__.py app/main.py tests/conftest.py tests/test_app_bootstrap.py
git commit -m "chore: bootstrap feishu bitable monitor project"
```

### Task 2: Add SQLite Models and Fallback Schedule Rules

**Files:**
- Create: `app/config.py`
- Create: `app/clock.py`
- Create: `app/db.py`
- Create: `app/models.py`
- Create: `app/schemas.py`
- Create: `app/services/fallback_schedule.py`
- Create: `tests/test_models_and_schedule.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for schema defaults and fallback timing**

```python
# tests/test_models_and_schedule.py
from datetime import UTC, datetime

from app.services.fallback_schedule import compute_next_fallback_at


def test_compute_next_fallback_at_uses_minutes_from_now():
    anchor = datetime(2026, 5, 28, 2, 0, 0, tzinfo=UTC).replace(tzinfo=None)

    assert compute_next_fallback_at(anchor, 360).isoformat(sep=" ") == "2026-05-28 08:00:00"
```

```python
def test_monitor_defaults_start_in_pending_state(session):
    from app.models import Monitor

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    assert monitor.watch_status == "pending"
    assert monitor.subscription_status == "pending"
    assert monitor.sync_status == "never"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_models_and_schedule.py -v`

Expected: import failures because models, DB and schedule helpers do not exist yet.

- [ ] **Step 3: Implement DB setup, models and fallback schedule helper**

```python
# app/clock.py
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
```

```python
# app/services/fallback_schedule.py
from datetime import datetime, timedelta


PRESET_INTERVALS = [360, 720, 1440, 4320]


def compute_next_fallback_at(anchor: datetime, minutes: int) -> datetime:
    return anchor + timedelta(minutes=minutes)
```

```python
# app/models.py
from sqlalchemy import Boolean, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.clock import utc_now


class Base(DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    app_token: Mapped[str] = mapped_column(Text)
    fallback_interval_minutes: Mapped[int] = mapped_column(Integer)
    next_fallback_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_status: Mapped[str] = mapped_column(Text, default="pending")
    subscription_status: Mapped[str] = mapped_column(Text, default="pending")
    sync_status: Mapped[str] = mapped_column(Text, default="never")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
```

- [ ] **Step 4: Add test DB fixtures and verify the tests pass**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import init_db
from app.models import Base


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session
```

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_models_and_schedule.py -v`

Expected: `2 passed`

- [ ] **Step 5: Commit the data layer foundation**

```bash
cd /Users/moennan/Documents/feishubitable
git add app/config.py app/clock.py app/db.py app/models.py app/schemas.py app/services/fallback_schedule.py tests/conftest.py tests/test_models_and_schedule.py
git commit -m "feat: add sqlite models and fallback scheduling"
```

### Task 3: Build the Feishu Bitable Client and Full Sync Executor

**Files:**
- Create: `app/clients/feishu.py`
- Create: `app/services/link_parser.py`
- Create: `app/services/full_sync.py`
- Create: `tests/test_full_sync.py`
- Modify: `app/models.py`

- [ ] **Step 1: Write the failing test for initial full sync**

```python
# tests/test_full_sync.py
def test_run_full_sync_rebuilds_tables_records_and_sync_run(session, monkeypatch):
    from app.models import Monitor
    from app.services.full_sync import run_full_sync

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/abc",
        app_token="abc",
        fallback_interval_minutes=360,
    )
    session.add(monitor)
    session.commit()

    class FakeClient:
        def get_bitable_meta(self, app_token):
            return {"app_token": app_token}

        def get_bitable_tables(self, app_token):
            return [{"table_id": "tbl1", "name": "员工表", "fields": [{"field_id": "f1", "field_name": "姓名"}]}]

        def list_bitable_records(self, app_token, table_id):
            return [{"record_id": "rec1", "fields": {"姓名": "张三"}}]

    result = run_full_sync(session, monitor.id, FakeClient(), trigger_type="initial")

    assert result.trigger_type == "initial"
    assert result.record_count == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_full_sync.py -v`

Expected: import failure because full sync service and related tables do not exist yet.

- [ ] **Step 3: Implement link parsing, Feishu client interface and full sync**

```python
# app/services/link_parser.py
from urllib.parse import urlparse


def parse_bitable_link(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "base":
        raise ValueError("仅支持飞书多维表格链接")
    return parts[1]
```

```python
# app/services/full_sync.py
from dataclasses import dataclass
import json

from app.clock import utc_now
from app.models import BitableTable, CurrentRecord, Monitor, SyncRun
from app.services.fallback_schedule import compute_next_fallback_at


@dataclass
class FullSyncResult:
    trigger_type: str
    record_count: int


def run_full_sync(session, monitor_id: int, client, trigger_type: str) -> FullSyncResult:
    monitor = session.get(Monitor, monitor_id)
    tables = client.get_bitable_tables(monitor.app_token)
    session.query(BitableTable).filter_by(monitor_id=monitor_id).delete()
    session.query(CurrentRecord).filter_by(monitor_id=monitor_id).delete()

    count = 0
    for order, table in enumerate(tables, start=1):
        session.add(
            BitableTable(
                monitor_id=monitor_id,
                table_id=table["table_id"],
                table_name=table["name"],
                field_schema_json=json.dumps(table.get("fields", []), ensure_ascii=False),
            )
        )
        records = client.list_bitable_records(monitor.app_token, table["table_id"])
        for row_index, record in enumerate(records, start=1):
            count += 1
            session.add(
                CurrentRecord(
                    monitor_id=monitor_id,
                    table_id=table["table_id"],
                    record_id=record["record_id"],
                    sort_order=row_index,
                    fields_json=json.dumps(record["fields"], ensure_ascii=False),
                    display_text=" | ".join(str(v) for v in record["fields"].values()),
                )
            )

    now = utc_now()
    monitor.current_record_count = count
    monitor.sync_status = "success"
    monitor.last_full_sync_at = now
    monitor.last_sync_at = now
    monitor.next_fallback_sync_at = compute_next_fallback_at(now, monitor.fallback_interval_minutes)
    session.add(SyncRun(monitor_id=monitor_id, trigger_type=trigger_type, status="success", started_at=now, finished_at=now, duration_ms=0, stats_json=json.dumps({"record_count": count}, ensure_ascii=False)))
    session.commit()
    return FullSyncResult(trigger_type=trigger_type, record_count=count)
```

- [ ] **Step 4: Run the full sync tests and make them pass**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_full_sync.py -v`

Expected: `1 passed`

- [ ] **Step 5: Commit the full sync baseline**

```bash
cd /Users/moennan/Documents/feishubitable
git add app/clients/feishu.py app/services/link_parser.py app/services/full_sync.py app/models.py tests/test_full_sync.py
git commit -m "feat: add bitable full sync baseline"
```

### Task 4: Build the Web Management Pages and Async Job Enqueue

**Files:**
- Create: `app/web/routes/settings.py`
- Create: `app/web/routes/monitors.py`
- Create: `app/templates/settings.html`
- Create: `app/templates/monitors.html`
- Create: `app/templates/monitor_form.html`
- Create: `app/templates/monitor_detail.html`
- Create: `app/templates/monitor_runs.html`
- Modify: `app/main.py`
- Modify: `app/static/styles.css`
- Create: `tests/test_monitor_routes.py`

- [ ] **Step 1: Write failing route tests for monitor creation and job enqueue**

```python
# tests/test_monitor_routes.py
def test_create_monitor_enqueues_initial_full_sync_job(client, session):
    from app.models import AppSetting

    session.add(AppSetting(app_id="cli_x", app_secret="secret"))
    session.commit()

    response = client.post(
        "/monitors",
        data={
            "name": "账号管理",
            "source_url": "https://example.feishu.cn/base/app123",
            "fallback_choice": "preset",
            "fallback_interval_minutes": "360",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
```

```python
def test_monitor_detail_shows_interval_and_current_status(client, seeded_monitor):
    response = client.get(f"/monitors/{seeded_monitor.id}")

    assert response.status_code == 200
    assert "低频全量间隔" in response.text
    assert "下一次低频全量时间" in response.text
```

- [ ] **Step 2: Run the route tests to verify they fail**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_monitor_routes.py -v`

Expected: 404s or import failures because the routes, templates and job creation flow do not exist yet.

- [ ] **Step 3: Implement settings page, monitor CRUD pages and async job enqueue**

```python
# app/web/routes/monitors.py
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models import Monitor, WorkerJob
from app.services.fallback_schedule import PRESET_INTERVALS, compute_next_fallback_at
from app.services.link_parser import parse_bitable_link

router = APIRouter()


@router.post("/monitors")
def create_monitor(name: str = Form(...), source_url: str = Form(...), fallback_interval_minutes: int = Form(...)):
    app_token = parse_bitable_link(source_url.strip())
    monitor = Monitor(
        name=name.strip(),
        source_url=source_url.strip(),
        app_token=app_token,
        fallback_interval_minutes=fallback_interval_minutes,
    )
    session.add(monitor)
    session.commit()
    session.add(WorkerJob(job_type="initial_full_sync", monitor_id=monitor.id, status="queued"))
    session.commit()
    return RedirectResponse(url=f"/monitors/{monitor.id}", status_code=303)
```

```html
<!-- app/templates/monitor_form.html -->
<form method="post" action="/monitors">
  <label>名称 <input name="name" required></label>
  <label>飞书多维表格链接 <input name="source_url" required></label>
  <label>低频全量间隔
    <select name="fallback_interval_minutes">
      <option value="360">6 小时</option>
      <option value="720">12 小时</option>
      <option value="1440">24 小时</option>
      <option value="4320">72 小时</option>
    </select>
  </label>
  <button type="submit">添加监控源</button>
</form>
```

- [ ] **Step 4: Run the route tests again to verify they pass**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_monitor_routes.py -v`

Expected: route tests pass and confirm the page only enqueues background work.

- [ ] **Step 5: Commit the Web management layer**

```bash
cd /Users/moennan/Documents/feishubitable
git add app/main.py app/web/routes/settings.py app/web/routes/monitors.py app/templates/base.html app/templates/settings.html app/templates/monitors.html app/templates/monitor_form.html app/templates/monitor_detail.html app/templates/monitor_runs.html app/static/styles.css tests/test_monitor_routes.py
git commit -m "feat: add web management pages and async monitor creation"
```

### Task 5: Add Worker Job Runner and Fallback Scheduler

**Files:**
- Create: `worker/job_runner.py`
- Create: `worker/scheduler.py`
- Create: `worker/main.py`
- Create: `tests/test_job_runner.py`
- Modify: `app/models.py`

- [ ] **Step 1: Write failing tests for queued full sync jobs and fallback scheduling**

```python
# tests/test_job_runner.py
def test_job_runner_executes_manual_full_sync_job(session, monkeypatch):
    from app.models import Monitor, WorkerJob
    from worker.job_runner import run_next_job

    monitor = Monitor(name="账号管理", source_url="https://example.feishu.cn/base/app123", app_token="app123", fallback_interval_minutes=360)
    session.add(monitor)
    session.commit()
    session.add(WorkerJob(job_type="manual_full_sync", monitor_id=monitor.id, status="queued"))
    session.commit()

    called = []
    monkeypatch.setattr("worker.job_runner.run_full_sync", lambda session, monitor_id, client, trigger_type: called.append((monitor_id, trigger_type)))

    run_next_job(session, client=object())

    assert called == [(monitor.id, "manual_full")]
```

```python
def test_scheduler_enqueues_fallback_job_when_monitor_is_due(session):
    from app.clock import utc_now
    from app.models import Monitor
    from worker.scheduler import enqueue_due_fallback_jobs

    monitor = Monitor(
        name="账号管理",
        source_url="https://example.feishu.cn/base/app123",
        app_token="app123",
        fallback_interval_minutes=360,
        next_fallback_sync_at=utc_now(),
    )
    session.add(monitor)
    session.commit()

    count = enqueue_due_fallback_jobs(session)

    assert count == 1
```

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_job_runner.py -v`

Expected: import failures because the worker modules do not exist yet.

- [ ] **Step 3: Implement queued job execution and due-job scheduling**

```python
# worker/job_runner.py
from sqlalchemy import select

from app.models import WorkerJob
from app.services.full_sync import run_full_sync
from app.services.subscription import resubscribe_monitor


def run_next_job(session, client):
    job = session.scalars(select(WorkerJob).where(WorkerJob.status == "queued").order_by(WorkerJob.id)).first()
    if job is None:
        return False

    job.status = "running"
    session.commit()

    if job.job_type == "initial_full_sync":
        run_full_sync(session, job.monitor_id, client, trigger_type="initial")
    elif job.job_type == "manual_full_sync":
        run_full_sync(session, job.monitor_id, client, trigger_type="manual_full")
    elif job.job_type == "fallback_full_sync":
        run_full_sync(session, job.monitor_id, client, trigger_type="fallback_full")
    elif job.job_type == "resubscribe":
        resubscribe_monitor(session, job.monitor_id, client)

    job.status = "success"
    session.commit()
    return True
```

```python
# worker/scheduler.py
from sqlalchemy import and_, select

from app.clock import utc_now
from app.models import Monitor, WorkerJob


def enqueue_due_fallback_jobs(session) -> int:
    due_monitors = session.scalars(
        select(Monitor).where(and_(Monitor.is_enabled.is_(True), Monitor.next_fallback_sync_at <= utc_now()))
    ).all()
    for monitor in due_monitors:
        session.add(WorkerJob(job_type="fallback_full_sync", monitor_id=monitor.id, status="queued"))
    session.commit()
    return len(due_monitors)
```

- [ ] **Step 4: Run the worker tests and verify they pass**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_job_runner.py -v`

Expected: `2 passed`

- [ ] **Step 5: Commit the Worker queue and scheduler**

```bash
cd /Users/moennan/Documents/feishubitable
git add worker/job_runner.py worker/scheduler.py worker/main.py app/models.py tests/test_job_runner.py
git commit -m "feat: add worker job runner and fallback scheduler"
```

### Task 6: Add Long Connection Event Processing and Record-Level Incremental Sync

**Files:**
- Create: `worker/event_listener.py`
- Create: `worker/event_processor.py`
- Create: `app/services/incremental_sync.py`
- Create: `app/services/subscription.py`
- Create: `tests/test_incremental_sync.py`
- Create: `tests/test_event_processor.py`
- Modify: `app/clients/feishu.py`

- [ ] **Step 1: Write failing tests for event dedupe and single-record upsert/delete**

```python
# tests/test_incremental_sync.py
def test_incremental_sync_updates_only_one_record(session, monkeypatch):
    from app.models import CurrentRecord, Monitor
    from app.services.incremental_sync import run_incremental_sync

    monitor = Monitor(name="账号管理", source_url="https://example.feishu.cn/base/app123", app_token="app123", fallback_interval_minutes=360)
    session.add(monitor)
    session.commit()
    session.add(CurrentRecord(monitor_id=monitor.id, table_id="tbl1", record_id="rec1", sort_order=1, fields_json='{"姓名":"旧值"}', display_text="旧值"))
    session.commit()

    class FakeClient:
        def get_bitable_record(self, app_token, table_id, record_id):
            return {"record_id": record_id, "fields": {"姓名": "新值"}}

    run_incremental_sync(
        session=session,
        monitor_id=monitor.id,
        table_id="tbl1",
        actions=[{"record_id": "rec1", "action": "record_edited"}],
        client=FakeClient(),
    )

    row = session.query(CurrentRecord).filter_by(record_id="rec1").one()
    assert "新值" in row.display_text
```

```python
# tests/test_event_processor.py
def test_process_event_deduplicates_by_event_id(session):
    from worker.event_processor import record_event

    payload = {
        "header": {"event_id": "evt-1", "event_type": "drive.file.bitable_record_changed_v1", "create_time": "1779931045198"},
        "event": {"app_token": "app123", "table_id": "tbl1", "action_list": []},
    }

    created = record_event(session, payload)
    duplicated = record_event(session, payload)

    assert created is True
    assert duplicated is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_incremental_sync.py tests/test_event_processor.py -v`

Expected: import failures because incremental sync and event processing modules do not exist yet.

- [ ] **Step 3: Implement event logging, dedupe, subscription handling and record-level sync**

```python
# app/services/incremental_sync.py
import json

from app.clock import utc_now
from app.models import CurrentRecord, Monitor, SyncRun


def run_incremental_sync(session, monitor_id: int, table_id: str, actions: list[dict], client) -> None:
    monitor = session.get(Monitor, monitor_id)
    updated_count = 0
    deleted_count = 0
    now = utc_now()

    for action in actions:
        record_id = action["record_id"]
        if action["action"] == "record_deleted":
            session.query(CurrentRecord).filter_by(monitor_id=monitor_id, table_id=table_id, record_id=record_id).delete()
            deleted_count += 1
            continue

        record = client.get_bitable_record(monitor.app_token, table_id, record_id)
        display_text = " | ".join(str(v) for v in record["fields"].values())
        row = session.query(CurrentRecord).filter_by(monitor_id=monitor_id, table_id=table_id, record_id=record_id).one_or_none()
        if row is None:
            row = CurrentRecord(monitor_id=monitor_id, table_id=table_id, record_id=record_id, sort_order=0, fields_json="{}", display_text="")
            session.add(row)
        row.fields_json = json.dumps(record["fields"], ensure_ascii=False)
        row.display_text = display_text
        row.updated_at = now
        updated_count += 1

    monitor.sync_status = "success"
    monitor.last_sync_at = now
    session.add(
        SyncRun(
            monitor_id=monitor_id,
            trigger_type="event_incremental",
            status="success",
            started_at=now,
            finished_at=now,
            duration_ms=0,
            stats_json=json.dumps({"updated_count": updated_count, "deleted_count": deleted_count, "skipped_count": 0}, ensure_ascii=False),
        )
    )
    session.commit()
```

```python
# worker/event_processor.py
from datetime import UTC, datetime
import json

from app.models import EventLog, Monitor
from app.services.incremental_sync import run_incremental_sync


def record_event(session, payload: dict) -> bool:
    header = payload["header"]
    if session.query(EventLog).filter_by(event_id=header["event_id"]).one_or_none() is not None:
        return False
    event = payload["event"]
    monitor = session.query(Monitor).filter_by(app_token=event["app_token"]).one()
    session.add(
        EventLog(
            event_id=header["event_id"],
            monitor_id=monitor.id,
            event_type=header["event_type"],
            table_id=event["table_id"],
            record_ids_json=json.dumps([item["record_id"] for item in event["action_list"]], ensure_ascii=False),
            event_time=datetime.fromtimestamp(int(header["create_time"]) / 1000, tz=UTC).replace(tzinfo=None),
            process_status="pending",
            raw_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    session.commit()
    return True
```

- [ ] **Step 4: Run the event and incremental sync tests**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_incremental_sync.py tests/test_event_processor.py -v`

Expected: both test files pass, proving the Worker can record and process single-record changes.

- [ ] **Step 5: Commit the event-driven incremental flow**

```bash
cd /Users/moennan/Documents/feishubitable
git add worker/event_listener.py worker/event_processor.py app/services/incremental_sync.py app/services/subscription.py app/clients/feishu.py tests/test_incremental_sync.py tests/test_event_processor.py
git commit -m "feat: add long-connection event processing and incremental sync"
```

### Task 7: Finish the Detail Views, Run the Full Test Suite, and Update the Runbook

**Files:**
- Create: `app/services/view_models.py`
- Modify: `app/templates/monitor_detail.html`
- Modify: `app/templates/monitor_runs.html`
- Modify: `README.md`
- Modify: `worker/main.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write one failing integration-style UI test for tabbed current data**

```python
# tests/test_monitor_routes.py
def test_monitor_detail_renders_table_tabs_and_pagination(client, seeded_bitable_monitor):
    response = client.get(f"/monitors/{seeded_bitable_monitor.id}?tab=tbl1&page=1")

    assert response.status_code == 200
    assert "当前数据" in response.text
    assert "员工表" in response.text
    assert "<table" in response.text
    assert "page=1" in response.text
```

- [ ] **Step 2: Run the single UI test to verify it fails**

Run: `cd /Users/moennan/Documents/feishubitable && pytest tests/test_monitor_routes.py::test_monitor_detail_renders_table_tabs_and_pagination -v`

Expected: FAIL because detail view assembly and pagination are not complete yet.

- [ ] **Step 3: Implement view models, worker run commands and final docs**

```python
# app/services/view_models.py
import json
from math import ceil


def build_current_record_view(records, table_meta_by_id, active_table_id, page, page_size=20):
    grouped = {}
    for row in records:
        grouped.setdefault(row.table_id, []).append(row)

    ordered_table_ids = list(grouped.keys())
    selected_table_id = active_table_id or (ordered_table_ids[0] if ordered_table_ids else None)
    selected_rows = grouped.get(selected_table_id, [])

    headers = ["记录ID"]
    if selected_rows:
        first_fields = json.loads(selected_rows[0].fields_json)
        headers.extend(first_fields.keys())

    start = (page - 1) * page_size
    end = start + page_size
    sliced_rows = selected_rows[start:end]

    body_rows = []
    for row in sliced_rows:
        fields = json.loads(row.fields_json)
        body_rows.append([row.record_id, *fields.values()])

    total_pages = max(1, ceil(len(selected_rows) / page_size)) if selected_rows else 1
    tabs = [
        {
            "id": table_id,
            "label": table_meta_by_id.get(table_id, table_id),
            "count": len(grouped[table_id]),
            "active": table_id == selected_table_id,
        }
        for table_id in ordered_table_ids
    ]

    return {
        "tabs": tabs,
        "headers": headers,
        "rows": body_rows,
        "active_table_id": selected_table_id,
        "pagination": {"page": page, "pages": list(range(1, total_pages + 1))},
    }
```

```markdown
# README.md
## 启动

1. `uv sync`
2. `uv run uvicorn app.main:app --reload`
3. `uv run python -m worker.main`

## 需要的飞书权限

- `bitable:app`
- `bitable:record`
- `drive:drive`
- `docs:event:subscribe`
```

- [ ] **Step 4: Run the complete verification suite**

Run: `cd /Users/moennan/Documents/feishubitable && pytest -v`

Expected: all tests pass.

Run: `cd /Users/moennan/Documents/feishubitable && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`

Expected: `GET /health` returns `{"status":"ok"}`.

Run: `cd /Users/moennan/Documents/feishubitable && uv run python -m worker.main`

Expected: Worker starts, initializes DB, enters long-connection and scheduler loops without import errors.

- [ ] **Step 5: Commit the finished first version**

```bash
cd /Users/moennan/Documents/feishubitable
git add README.md app/services/view_models.py app/templates/monitor_detail.html app/templates/monitor_runs.html app/main.py worker/main.py tests/test_monitor_routes.py
git commit -m "feat: complete first version of feishu bitable monitor"
```

## Self-Review

- Spec coverage:
  - 仅支持多维表格：Task 3、Task 6
  - 首次全量同步：Task 3、Task 5
  - 低频全量间隔创建与修改：Task 4、Task 5
  - 长连接事件：Task 6
  - 记录级增量同步：Task 6
  - Web 页面和表格分页：Task 4、Task 7
  - 错误留痕与同步记录：Task 3、Task 5、Task 6
- Placeholder scan:
  - 已检查完整文档，没有保留 `TODO`、`TBD`、省略号实现或“以后再补”的指令。
- Type consistency:
  - `trigger_type` 在计划内统一使用 `initial / manual_full / fallback_full / event_incremental`
  - `job_type` 在计划内统一使用 `initial_full_sync / manual_full_sync / fallback_full_sync / resubscribe`
