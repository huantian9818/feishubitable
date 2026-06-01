# Feishu Bitable Monitor

面向飞书多维表格的轻量监控工具。当前仓库采用 `Web 服务 + Worker 服务 + SQLite` 的双进程结构：

- Web 负责配置、管理和查看状态
- Worker 负责调度、消费异步任务和执行同步

## 本地启动

### 1. 准备环境

要求：

- Python 3.13+
- `uv` 可执行命令

如果当前终端里没有 `uv`，可以先安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装依赖：

```bash
cd /Users/moennan/Documents/feishubitable
uv sync
```

### 2. 启动 Web

```bash
cd /Users/moennan/Documents/feishubitable
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

启动后访问：

- 管理页：[http://127.0.0.1:8000/monitors](http://127.0.0.1:8000/monitors)
- 设置页：[http://127.0.0.1:8000/settings](http://127.0.0.1:8000/settings)
- 健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 3. 启动 Worker

持续轮询模式（推荐本地开发时使用）：

```bash
cd /Users/moennan/Documents/feishubitable
uv run python -m worker.main
```

单次循环模式（只扫一次兜底任务并尝试消费一个任务）：

```bash
cd /Users/moennan/Documents/feishubitable
uv run python -m worker.main --once
```

调整轮询间隔：

```bash
cd /Users/moennan/Documents/feishubitable
uv run python -m worker.main --interval 10
```

### 4. 基本使用顺序

1. 打开 `/settings`，填写飞书应用配置：`App ID`、`App Secret`、`Tenant Key`
2. 打开 `/monitors`，添加一个飞书多维表格链接
3. 保持 Worker 进程在运行，等待初始全量任务被消费
4. 打开监控详情页和运行记录页，观察同步状态、错误和统计

## 需要的飞书权限

至少准备这些能力：

- `bitable:app`
- `bitable:record`
- `drive:drive`
- `docs:event:subscribe`

除此之外，还要确认两件事：

- 飞书应用本身已经开通多维表格相关能力
- 被监控的多维表格已经对这个应用授予可访问/可管理权限，否则会出现订阅失败或读取失败

如果你要验证事件驱动链路，还需要确保应用拿到了多维表格记录变更事件的订阅能力，并且对应事件已在飞书开放平台侧启用。

## 常用命令

安装依赖：

```bash
uv sync
```

运行测试：

```bash
uv run python -m pytest
```

只跑基础启动测试：

```bash
uv run python -m pytest tests/test_app_bootstrap.py
```

检查 Worker 入口语法：

```bash
uv run python -m py_compile worker/main.py
```

## 基础排障

`uv: command not found`

- 说明 `uv` 不在当前 shell 的 `PATH` 里
- 重新打开终端，或先执行安装脚本，再运行 `uv sync`

`/health` 正常但页面打不开

- 先确认 Web 是否用 `uvicorn app.main:app` 启动
- 再确认访问的是 `127.0.0.1:8000` 而不是别的端口

创建监控后一直没有同步

- 确认 Worker 进程是否仍在运行
- 打开运行记录页，查看是否有 `queued` 任务长期不动
- 如果只有 Web，没有 Worker，异步任务会一直留在队列里

运行记录出现 `failed`

- 优先看运行记录页里的错误信息
- 再检查飞书应用权限、表格授权和填写的 `App ID / App Secret / Tenant Key`
- 如果是首次全量失败，通常和表格访问权限或客户端实现未接通有关

SQLite 数据看起来不一致

- Web 和 Worker 必须指向同一个仓库目录下的 `data/app.sqlite3`
- 不要一边在 A 目录启动 Web，一边在 B 目录启动 Worker

本地观察建议：

- 一个终端跑 Web
- 一个终端跑 Worker
- Worker 默认常驻轮询，适合直接观察任务从 `queued -> running -> success/failed` 的变化
