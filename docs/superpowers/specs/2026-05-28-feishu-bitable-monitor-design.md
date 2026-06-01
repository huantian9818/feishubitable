# 飞书多维表格监控器设计文档

## 1. 目标

构建一个全新的、只面向飞书多维表格（Bitable）的监控工具，项目目录为 `/Users/moennan/Documents/feishubitable`。

第一版只解决这一条核心链路：

- 添加多维表格监控源
- 首次全量同步落库
- 低频全量同步兜底
- 飞书事件订阅
- 记录级增量同步
- 通过简单 Web 页面查看状态、当前数据、事件日志和同步记录

本项目不再兼容 `docx`、`sheets`、`wiki` 等其他飞书对象，也不保留旧项目中的通用快照模型。

## 2. 范围

### 2.1 In Scope

- 仅支持飞书多维表格链接
- 支持多个监控源
- 管理页面使用 FastAPI 服务端渲染
- SQLite 作为唯一数据库
- Web 服务与 Worker 服务分离为两个进程
- 首次全量同步建立基线
- 事件订阅采用飞书长连接模式
- `drive.file.bitable_record_changed_v1` 走记录级增量同步
- 低频全量同步作为一致性兜底
- 每个监控源在创建时设置低频兜底间隔，并允许后续修改

### 2.2 Out of Scope

- 支持除多维表格以外的飞书对象
- 多用户系统、权限系统、登录系统
- 分布式部署
- PostgreSQL、MySQL 等其他数据库
- 完整版本快照历史
- 记录级变更审计历史
- 直接消费事件 payload 作为最终展示数据源
- Webhook 回调模式

## 3. 总体架构

采用 `Web 服务 + Worker 服务 + SQLite` 的双进程结构。

### 3.1 Web 服务

Web 服务只负责管理和展示，不直接执行重同步或事件处理。

职责：

- 配置飞书应用凭证
- 创建、删除、查看监控源
- 修改低频全量间隔
- 展示当前数据、最近事件、同步记录
- 接收“立即全量同步”“重新订阅”等用户操作
- 将执行请求写入数据库任务表

Web 服务不负责：

- 飞书长连接
- 首次全量同步
- 事件增量同步
- 大批量写入当前记录数据

### 3.2 Worker 服务

Worker 服务是唯一的主执行者。

职责：

- 启动飞书长连接监听
- 接收并处理飞书事件
- 执行首次全量同步
- 执行手动全量同步
- 执行低频全量同步
- 执行记录级增量同步
- 消费任务队列
- 维护监控状态和同步状态

### 3.3 SQLite

SQLite 同时承担三种角色：

- 业务数据存储
- 执行留痕
- Web 与 Worker 的协调层

Web 与 Worker 不直接互调代码逻辑，统一围绕数据库表进行协作。

## 4. 数据模型

第一版使用以下 7 张主表。

### 4.1 `app_settings`

保存飞书应用配置：

- `app_id`
- `app_secret`
- `tenant_key`
- `timezone`

### 4.2 `monitors`

一条监控源一行。

建议字段：

- `id`
- `name`
- `source_url`
- `app_token`
- `fallback_interval_minutes`
- `next_fallback_sync_at`
- `is_enabled`
- `watch_status`
- `subscription_status`
- `sync_status`
- `last_event_at`
- `last_event_type`
- `last_sync_at`
- `last_full_sync_at`
- `last_sync_error`
- `watch_error`
- `subscription_error`
- `current_record_count`
- `created_at`
- `updated_at`

### 4.3 `bitable_tables`

保存每个监控源下的子表元信息。

建议字段：

- `id`
- `monitor_id`
- `table_id`
- `table_name`
- `field_schema_json`
- `last_seen_revision`
- `updated_at`

约束：

- `UNIQUE(monitor_id, table_id)`

### 4.4 `current_records`

保存监控源的当前记录状态，一条飞书记录一行。

建议字段：

- `id`
- `monitor_id`
- `table_id`
- `record_id`
- `sort_order`
- `fields_json`
- `display_text`
- `source_revision`
- `updated_at`

约束：

- `UNIQUE(monitor_id, table_id, record_id)`

### 4.5 `event_logs`

保存飞书推送事件。

建议字段：

- `id`
- `event_id`
- `monitor_id`
- `event_type`
- `table_id`
- `record_ids_json`
- `event_time`
- `process_status`
- `error_message`
- `raw_json`
- `created_at`

约束：

- `UNIQUE(event_id)`

### 4.6 `sync_runs`

保存每次同步执行记录。

建议字段：

- `id`
- `monitor_id`
- `trigger_type`
- `status`
- `started_at`
- `finished_at`
- `duration_ms`
- `stats_json`
- `error_message`

允许的 `trigger_type`：

- `initial`
- `manual_full`
- `fallback_full`
- `event_incremental`

### 4.7 `worker_jobs`

保存 Web 发给 Worker 的执行任务。

建议字段：

- `id`
- `job_type`
- `monitor_id`
- `payload_json`
- `status`
- `run_after`
- `started_at`
- `finished_at`
- `error_message`
- `created_at`

允许的 `job_type`：

- `initial_full_sync`
- `manual_full_sync`
- `fallback_full_sync`
- `resubscribe`

允许的 `status`：

- `queued`
- `running`
- `success`
- `failed`

## 5. 执行链路

### 5.1 首次全量同步

创建监控源时：

1. Web 校验飞书凭证已配置
2. Web 解析链接并确认是多维表格
3. Web 创建 `monitor`
4. Web 写入一条 `initial_full_sync` 任务
5. Web 立即跳转详情页并提示“首次全量同步正在后台执行”

Worker 执行该任务时：

1. 获取 `tenant_access_token`
2. 拉取多维表格元数据
3. 拉取所有子表
4. 拉取所有子表下全部记录
5. 重建 `bitable_tables`
6. 重建该监控源的 `current_records`
7. 写入 `sync_runs(trigger_type=initial)`
8. 尝试建立飞书事件订阅
9. 更新 `monitors` 的订阅、同步和统计状态

### 5.2 事件驱动记录级增量同步

Worker 长连接收到 `drive.file.bitable_record_changed_v1` 后：

1. 先写 `event_logs`
2. 通过 `event_id` 去重
3. 从事件中解析 `table_id`、`record_id`、动作类型
4. 根据 `app_token` 与 `table_id` 找到对应 `monitor`
5. 对每条变更记录执行：
   - `record_added / record_edited`：
     - 回源获取该记录最新内容
     - 标准化后 `upsert current_records`
   - `record_deleted`：
     - 直接删除对应 `current_records`
6. 更新 `monitors.last_event_at`、`last_sync_at`、`sync_status`
7. 写入 `sync_runs(trigger_type=event_incremental)`

同一事件内如同一 `record_id` 出现多次，按最后一个动作处理。

### 5.3 低频全量同步兜底

Worker 的调度器周期性扫描 `monitors.next_fallback_sync_at`。

到期后：

1. 创建或直接执行一条 `fallback_full_sync` 任务
2. 重新拉取整份多维表格
3. 覆盖 `bitable_tables`
4. 覆盖 `current_records`
5. 写入 `sync_runs(trigger_type=fallback_full)`
6. 更新 `last_full_sync_at`
7. 重新计算 `next_fallback_sync_at`

目标是修复：

- 漏事件
- 事件乱序
- 增量失败
- 字段结构变化

## 6. 低频全量间隔设计

每个监控源都必须配置自己的低频全量兜底间隔。

### 6.1 创建时配置

添加监控源页面提供：

- 预设选项：
  - `6 小时`
  - `12 小时`
  - `24 小时`
  - `72 小时`
- `自定义分钟数`

规则：

- 选择预设时，使用预设值
- 选择自定义时，必须填写合法分钟数

### 6.2 后期修改

监控源详情页允许修改低频全量间隔。

保存后：

- 更新 `fallback_interval_minutes`
- 重新计算 `next_fallback_sync_at`
- 不触发首次同步重跑

### 6.3 调度计算规则

- 全量兜底成功后，下一次时间按“完成时间 + 间隔”计算
- 中途修改间隔后，下一次时间按“保存修改的时间 + 新间隔”重新计算

## 7. Worker 内部模块划分

建议拆分为以下模块：

### 7.1 `worker_main`

负责 Worker 入口、数据库初始化、生命周期管理、优雅退出。

### 7.2 `event_listener`

负责飞书长连接、心跳、重连、在线状态维护。

### 7.3 `event_processor`

负责事件落库、去重、解析和分流。

### 7.4 `sync_executor`

负责全量同步与记录级增量同步的真正执行逻辑。

### 7.5 `job_runner`

负责消费 `worker_jobs`，执行任务并回写状态。

### 7.6 `scheduler`

负责扫描兜底执行时间并创建兜底任务。

## 8. Web 页面设计

第一版只做 4 个页面。

### 8.1 设置页

配置：

- `app_id`
- `app_secret`
- 默认时区

### 8.2 监控源列表页

每个监控源卡片展示：

- 名称
- 原始链接
- 监控状态
- 订阅状态
- 同步状态
- 当前记录数
- 最近事件时间
- 最近同步时间
- 低频全量间隔
- 下一次低频全量时间

支持操作：

- `查看详情`
- `立即全量同步`
- `重新订阅`
- `删除`

### 8.3 添加监控源页

字段：

- 名称
- 多维表格链接
- 低频全量间隔（预设或自定义）

提交后只创建监控源和任务，不等待真正同步完成。

### 8.4 监控源详情页

分为 4 块：

- `监控概览`
- `当前数据`
- `最近事件`
- `同步记录`

当前数据区要求：

- 按子表做顶部标签页
- 每页只显示 `20` 行
- 表格展示
- 支持页码切换

详情页支持操作：

- `立即全量同步`
- `重新订阅`
- `修改低频全量间隔`
- `删除监控源`

## 9. 错误处理与恢复

### 9.1 创建阶段错误

例如：

- 未配置凭证
- 不是多维表格链接
- 监控源重复

处理方式：

- 页面直接报错
- 不创建 monitor
- 不写后台任务

### 9.2 订阅错误

例如：

- 应用权限不足
- 文档未授予应用可管理权限
- 飞书返回 `400 / 403`

处理方式：

- monitor 可以存在
- 首次全量成功后当前数据仍可查看
- `subscription_status` 与 `watch_status` 标失败
- 支持手动 `重新订阅`

### 9.3 事件增量错误

例如：

- payload 解析失败
- 找不到对应 monitor
- 单条记录回源失败
- `upsert` 失败

处理方式：

- 事件先落 `event_logs`
- 失败后保留错误信息
- 不阻断后续事件处理
- 同一批事件中已成功的记录更新不回滚
- 只要本批存在失败，本次 `sync_run` 记 `failed`

### 9.4 全量同步错误

例如：

- 飞书接口失败
- 某张子表拉取失败
- 字段结构变化导致标准化失败

处理方式：

- 记录失败的 `sync_run`
- 保留旧 `current_records`
- 新全量成功前不破坏旧当前状态

### 9.5 恢复手段

- 手动 `重新订阅`
- 手动 `立即全量同步`
- Worker 自动重连长连接
- 低频全量兜底校准

## 10. 测试策略

第一版至少覆盖：

### 10.1 单元测试

- 多维表格链接解析
- 低频间隔解析与下一次执行时间计算
- 事件 payload 解析
- 单条记录标准化
- 记录级 `upsert/delete`

### 10.2 集成测试

- 首次全量同步全链路
- 事件增量同步全链路
- 低频兜底全量同步
- 任务表消费链路
- Web 页面主要路由

### 10.3 模拟飞书接口测试

- 元数据获取
- 子表列表获取
- 全量记录分页
- 单条记录回源获取
- 订阅与查询订阅状态
- 长连接事件处理

## 11. 成功标准

当以下结果成立时，第一版视为完成：

- 能创建多个多维表格监控源
- 每个监控源都能在创建时配置低频全量间隔
- 首次全量同步能正确落库
- 长连接能收到多维表格记录变更事件
- 事件能驱动记录级增量同步
- 低频全量能按配置自动兜底执行
- Web 页面能清楚展示状态、当前数据、事件日志和同步记录
- Web 页面上的操作不阻塞浏览器请求
- 即使订阅失败，已有当前数据仍可查看

