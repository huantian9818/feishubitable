# record_changed 多表并行设计文档

## 1. 目标

在现有飞书多维表格监控器基础上，重构 `drive.file.bitable_record_changed_v1` 的执行模型，使其从“事件回调内同步执行”升级为“入 `WorkerJob` 队列后由多个 Worker 并行消费”。

这次改造的核心目标只有一条：

- 不同子表可以并行执行
- 同一子表必须严格串行执行
- 同一子表内的 `record_changed` 与 `field_changed` 必须共用一条顺序执行通道
- `record_changed` 事件绝不合并，每个事件都单独执行

这里的“表”指的是一个飞书多维表格应用中的子表，即 `table_id`，不是整个监控源。

## 2. 背景

当前实现中：

- `drive.file.bitable_record_changed_v1` 在事件回调线程里直接执行记录级增量同步
- `drive.file.bitable_field_changed_v1` 已经改为写入 `worker_jobs`，再由 Worker 执行表级重拉

这带来两个问题：

- `record_changed` 与 `field_changed` 的执行模型不一致
- `record_changed` 不能利用多 Worker 并行能力，也不能和同子表的 `field_changed` 共享串行保护

因此需要把 `record_changed` 也迁移到队列模型，同时补上“按子表串行”的约束。

## 3. 范围

### 3.1 In Scope

- `drive.file.bitable_record_changed_v1` 改为入 `worker_jobs`
- 支持启动多个 Worker 进程并行消费
- 以 `monitor_id + table_id` 作为串行粒度
- 同一子表内的 `record_changed` 绝不合并
- 同一子表内的 `record_changed` 与 `field_changed` 共享执行租约
- 任务顺序以进入系统顺序为准，即 `worker_jobs.id` 顺序
- 增加租约超时机制，避免 Worker 崩溃后永久锁死子表

### 3.2 Out of Scope

- `field_changed` 任务合并策略调整
- 全量同步任务并行化
- 多数据库支持
- 自动重试、死信队列、复杂补偿机制
- 按 `record_id` 更细粒度的并行
- 更改 Web 页面交互

## 4. 总体架构

改造后，事件处理链路分为两层：

1. **事件接收层**
   - 飞书长连接收到事件
   - 事件先写入 `event_logs`
   - 再写入 `worker_jobs`
   - 不在回调线程中直接执行 `record_changed`

2. **任务执行层**
   - 多个 Worker 进程并行运行
   - 每个 Worker 都从 `worker_jobs` 中挑选可执行任务
   - 真正能否执行，不仅取决于任务是否 `queued`，还取决于这张子表当前是否空闲

并行与有序的平衡点是：

- **不同 `monitor_id + table_id`**：允许被不同 Worker 同时执行
- **相同 `monitor_id + table_id`**：必须共享同一把执行租约，只能有一个 Worker 进入执行态

## 5. 数据模型

### 5.1 复用现有 `worker_jobs`

`worker_jobs` 继续作为统一任务事实表。

新增或明确使用的 `job_type`：

- `record_changed_incremental`
- `field_changed_table_resync`
- 现有 `initial_full_sync`
- 现有 `manual_full_sync`
- 现有 `fallback_full_sync`
- 现有 `resubscribe`

`record_changed_incremental` 的 `payload_json` 至少包含：

- `table_id`
- `event_id`

`field_changed_table_resync` 的 `payload_json` 至少包含：

- `table_id`
- `source_event_id`

### 5.2 新增 `table_job_leases`

新增一张表，负责“这张子表当前能不能跑”。

建议字段：

- `id`
- `monitor_id`
- `table_id`
- `worker_id`
- `lease_expires_at`
- `created_at`
- `updated_at`

约束：

- `UNIQUE(monitor_id, table_id)`

语义：

- 存在且未过期：说明这张子表正在被某个 Worker 执行
- 不存在或已过期：说明这张子表可被新的 Worker 接管

### 5.3 现有表保持不变

以下表结构不需要因为本次改造而扩字段：

- `event_logs`
- `sync_runs`
- `monitors`
- `bitable_tables`
- `current_records`

## 6. 任务流转

### 6.1 事件入队

`drive.file.bitable_record_changed_v1` 到来后：

1. 写入 `event_logs`
2. 生成一条 `record_changed_incremental` 任务
3. 不做任务合并
4. 不在事件回调线程内执行增量同步

`drive.file.bitable_field_changed_v1` 保持当前行为：

1. 写入 `event_logs`
2. 生成 `field_changed_table_resync` 任务
3. 同子表的 `queued` 任务允许按现有规则合并为最后一个

### 6.2 Worker 抢任务

每个 Worker 都按 `worker_jobs.id` 从小到大扫描 `queued` 任务。

拿到候选任务后：

1. 解析出 `monitor_id + table_id`
2. 尝试获取这张子表的租约
3. 获取成功：把任务标记为 `running` 并执行
4. 获取失败：跳过这条任务，继续查找下一条可执行任务

这意味着：

- 队列顺序仍然保留
- 但不会因为一张忙碌子表挡住其他子表任务

### 6.3 任务执行

`record_changed_incremental`：

- 只执行该事件对应的记录级增量同步
- 每个事件单独执行
- 不允许任务合并

`field_changed_table_resync`：

- 刷新该子表的字段结构缓存
- 重拉该子表全部记录

无论是哪一种任务，只要落在同一个 `monitor_id + table_id` 上，就必须共用同一把租约锁。

## 7. 顺序语义

顺序只按一个规则定义：

- **同一子表内，按任务进入系统顺序执行**

这里的“进入系统顺序”就是 `worker_jobs.id` 顺序，不按飞书事件头里的 `create_time` 重排。

这样可以避免：

- 依赖事件时间戳排序带来的复杂比较
- 多 Worker 下按业务时间重排的歧义

这也符合用户要求：

- 同一子表绝不合并 `record_changed`
- 每个事件都单独执行
- 严格按进入系统顺序逐条处理

## 8. 失败与恢复

### 8.1 正常完成

任务成功后：

- 更新 `worker_jobs.status = success`
- 写入对应 `sync_runs`
- 释放子表租约

### 8.2 任务失败

任务失败后：

- 更新 `worker_jobs.status = failed`
- 写入失败 `sync_runs`
- 释放子表租约

失败不会阻塞后续同子表任务继续执行。

### 8.3 Worker 崩溃

如果 Worker 在执行中崩溃：

- 它来不及主动释放租约
- 依赖 `lease_expires_at` 超时恢复
- 其他 Worker 看到租约过期后，可以重新接管后续任务

第一版不处理“执行中一半的任务自动补跑”，只保证：

- 子表不会永久锁死
- 后续任务仍能继续推进

## 9. 一致性要求

这次改造后，同一子表的两类任务必须共享一致性边界：

- `record_changed_incremental`
- `field_changed_table_resync`

这样可以避免以下冲突：

- 一边做整表重拉，一边做记录级局部更新
- 两种写路径同时覆盖同一子表数据

一致性边界统一为：

- `monitor_id + table_id`

## 10. 测试策略

需要新增或调整四类测试。

### 10.1 事件入队测试

- `record_changed` 不再在回调线程里直接执行
- `record_changed` 会生成 `record_changed_incremental` 任务
- 相同 `event_id` 仍然去重
- `field_changed` 现有行为不被破坏

### 10.2 租约测试

- 两条不同子表任务可被两个 Worker 分别获取
- 两条相同子表任务不能同时获取
- 租约过期后可被重新接管

### 10.3 顺序测试

- 同一子表的多个 `record_changed` 按 `worker_jobs.id` 顺序执行
- 同一子表的 `record_changed` 和 `field_changed` 也按该顺序串行执行

### 10.4 失败恢复测试

- 执行失败后租约会释放
- 后续同子表任务仍能执行
- Worker 崩溃后的过期租约可以被新 Worker 接管

## 11. 方案取舍

本次选择的是：

- `SQLite + 多 Worker + 子表租约表`

不选择以下方案的原因：

- **单 Worker + 线程池**：状态主要留在进程内，崩溃恢复和扩展性差
- **外部队列系统**：对当前项目过重
- **仅按监控源串行**：并行粒度太粗，无法实现“多表并行”

## 12. 结论

本次设计把 `record_changed` 纳入统一任务队列，并新增 `monitor_id + table_id` 粒度的租约控制。

最终实现的系统语义是：

- 不同子表可以并行
- 同一子表严格串行
- 同一子表的 `record_changed` 绝不合并
- 同一子表的 `record_changed` 与 `field_changed` 共用同一条执行通道
- Worker 崩溃不会把某张子表永久锁死

这为后续真正启动多个 Worker 并行消费打下执行模型基础，同时保持当前 SQLite 架构不变。
