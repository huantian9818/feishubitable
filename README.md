# Feishu Bitable Monitor

面向飞书多维表格的本地监控工具。项目采用 `FastAPI Web + Worker + SQLite` 结构，负责：

- 配置飞书应用凭证
- 添加和删除监控源
- 首轮全量同步多维表格数据
- 持续接收飞书事件并做增量更新
- 在页面里查看当前数据、任务记录、同步结果和事件推送延迟

当前系统时间统一使用 `Asia/Shanghai`，数据库、页面展示和 Worker 日志都是北京时间。

## 功能概览

### 1. 监控源管理

- 支持添加监控源
- 支持删除监控源，并同时清理本地关联数据
- 监控列表提供明确的 `查看详情` 和 `删除监控源` 入口

### 2. 链接支持

- 支持飞书多维表格直链：`/base/<app_token>`
- 支持飞书知识库 `wiki` 链接

对于 `wiki` 链接，系统会先解析知识库节点，再拿到真实的 bitable `app_token` 进行后续同步和事件订阅。

### 3. 数据同步

- 新建监控源后会自动创建 `initial_full_sync` 任务
- 首轮全量同步会拉取：
  - 所有子表
  - 每张子表的字段列表
  - 每张子表的全部记录
- 本地详情页“当前数据”展示的列顺序，按飞书字段顺序渲染，而不是按记录 JSON 的 key 顺序猜测

### 4. 事件驱动更新

当前已经接入两类多维表格事件：

- `drive.file.bitable_record_changed_v1`
- `drive.file.bitable_field_changed_v1`

处理规则：

- `record_changed`
  - 为每条事件创建一个 `record_changed_incremental` 队列任务
  - 同一子表内严格保序
  - 不同子表可并行

- `field_changed`
  - 触发 `field_changed_table_resync`
  - 只刷新事件所属 `table_id`
  - 刷新该表字段 schema
  - 重拉该表全部记录

### 5. 低频兜底同步

每个监控源都配置一个低频全量间隔。到期后 Worker 会自动补入 `fallback_full_sync` 任务，用于：

- 长连接断线期间的兜底修正
- 事件漏收后的最终一致性恢复

### 6. 运行记录页

运行记录页分为两块：

- `待处理/已处理任务`
  - 看队列层发生了什么
  - 例如 `initial_full_sync`、`record_changed_incremental`

- `实际同步结果`
  - 看真正的数据同步结果
  - 例如 `initial`、`event_incremental`、`event_field_table_resync`

对于事件触发的任务，页面还会显示：

- `事件发生`
- `本地接收`
- `推送延迟`

这能直接判断延迟是发生在“飞书推送到本地”这一段，还是发生在“本地收到后处理”这一段。

## 执行逻辑

### 新建监控源

1. 在 `/monitors/new` 提交链接和低频间隔
2. Web 解析链接，保存 `Monitor`
3. Web 写入 `initial_full_sync` 到 `worker_jobs`
4. Worker 消费任务，执行首轮全量同步
5. 全量同步完成后，刷新飞书文件订阅

### 收到记录变更事件

1. 飞书通过长连接把事件推给 Worker
2. Worker 将原始事件写入 `event_logs`
3. Worker 创建 `record_changed_incremental`
4. Worker 消费任务，按事件中的 `record_id` 拉最新记录
5. 写回 `current_records`
6. 落一条 `sync_runs` 结果记录

### 收到字段变更事件

1. 飞书通过长连接把事件推给 Worker
2. Worker 将事件写入 `event_logs`
3. Worker 创建 `field_changed_table_resync`
4. Worker 拉该子表字段列表
5. Worker 拉该子表全部记录
6. 更新该子表本地 schema 和记录
7. 落一条 `sync_runs` 结果记录

### 同表串行 / 多表并行

系统使用 `table_job_leases` 做子表级租约控制：

- 同一 `monitor_id + table_id` 共享一条串行通道
- 不同 `table_id` 的任务允许并行
- `record_changed` 和 `field_changed` 对同一子表不会并发打架

## 页面说明

### `/settings`

- 配置 `App ID`
- 配置 `App Secret`
- 配置 `Tenant Key`

系统时区固定为北京时间，不再支持切换。

### `/monitors`

- 查看所有监控源
- 添加监控源
- 查看详情
- 删除监控源

### `/monitors/<id>`

- 查看监控基本信息
- 查看子表分页数据
- 查看当前同步状态
- 查看当前任务状态

### `/monitors/<id>/runs`

- 查看队列任务历史
- 查看同步结果历史
- 查看事件推送延迟

## 本地运行

### 环境要求

- Python 3.13+
- `uv`

安装依赖：

```bash
uv sync
```

### 启动 Web

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问入口：

- [http://127.0.0.1:8000/monitors](http://127.0.0.1:8000/monitors)
- [http://127.0.0.1:8000/settings](http://127.0.0.1:8000/settings)
- [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 启动 Worker

常驻运行：

```bash
uv run python -m worker.main --interval 10
```

只跑一轮：

```bash
uv run python -m worker.main --once
```

只消费任务，不启动长连接监听：

```bash
uv run python -m worker.main --no-listener --interval 10
```

## 飞书侧要求

### 应用凭证

至少需要：

- `App ID`
- `App Secret`

`Tenant Key` 当前主要用于保留租户信息，不是当前同步链路的核心鉴权参数。

### 事件与订阅

除了在飞书开放平台里开启事件外，bitable 事件还依赖文件级订阅。当前项目会在首轮全量同步成功后自动调用订阅接口。

如果长连接不在线：

- 飞书侧事件仍然会产生
- 但当前进程收不到实时事件
- 项目没有“断线后补领历史事件”的机制
- 只能依赖后续新事件或低频全量同步兜底

### 权限建议

至少要保证应用对目标多维表格具备：

- 可读取表结构
- 可读取记录
- 可订阅多维表格相关事件

如果权限不足，常见现象包括：

- 初始全量同步失败
- 订阅刷新失败
- 长连接在线但一直收不到目标表事件

## 数据文件与表

SQLite 默认保存在：

- `data/app.sqlite3`

核心表：

- `app_settings`
- `monitors`
- `bitable_tables`
- `current_records`
- `event_logs`
- `worker_jobs`
- `sync_runs`
- `table_job_leases`

## 常用命令

安装依赖：

```bash
uv sync
```

运行所有测试：

```bash
uv run python -m pytest
```

只跑监控路由测试：

```bash
uv run python -m pytest tests/test_monitor_routes.py -q
```

## 排障建议

### 1. 页面正常，但没有同步

优先确认 Worker 是否还在运行。如果只有 Web，没有 Worker，任务会一直停留在队列中。

### 2. 改了知识库文档正文，但没有事件

这是正常现象。当前项目监听的是 bitable 事件，不是 wiki 文档正文编辑事件。

### 3. 改了多维表格记录，但事件到得很晚

看运行记录页里的：

- `事件发生`
- `本地接收`
- `推送延迟`

如果这三项已经显示出明显延迟，说明慢的是飞书推送到本地这一段，不是本地 Worker 处理慢。

### 4. 字段顺序和源表不一致

当前版本已经按飞书字段接口落库。如果还不一致，先手动触发一次全量同步，确认本地 `field_schema_json` 已刷新。

### 5. 页面数据更新了，但浏览器没变

当前页面是服务端渲染，没有 WebSocket 自动刷新。需要刷新页面后才能看到最新值。
