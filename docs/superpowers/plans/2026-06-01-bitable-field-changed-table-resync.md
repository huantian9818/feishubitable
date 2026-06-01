# Bitable Field Changed Table Resync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `drive.file.bitable_field_changed_v1` handling that enqueues per-table resync jobs, coalesces queued jobs by `monitor_id + table_id`, and refreshes the changed table's schema plus all records.

**Architecture:** Extend the websocket event registration and event processor so field-change events are recorded but dispatched to a new queued worker job instead of inline execution. Reuse the existing database tables and `WorkerJob` queue by adding a table-resync job type plus a table-focused sync service that rewrites one table's schema and current records.

**Tech Stack:** FastAPI, SQLAlchemy ORM, SQLite, pytest

---

### Task 1: Cover event dispatch and queue coalescing

**Files:**
- Modify: `tests/test_event_processor.py`
- Modify: `tests/test_job_runner.py`

- [ ] Add failing tests for `drive.file.bitable_field_changed_v1` that prove:
  - a new field-change event records an `EventLog`
  - the event enqueues one `WorkerJob` carrying `table_id`
  - a second field-change event for the same table replaces a queued job instead of adding another
  - a second field-change event for a different table creates an additional queued job
- [ ] Run the focused test selection and confirm it fails because field-change events are not yet recognized

### Task 2: Implement field-change event recording and job scheduling

**Files:**
- Modify: `worker/event_processor.py`
- Modify: `app/models.py` only if existing columns cannot carry the needed payload

- [ ] Add event-type-aware handling so `record_event()` still persists the event log but routes `drive.file.bitable_field_changed_v1` into a queued table-resync job
- [ ] Implement queue coalescing keyed by `monitor_id + table_id` for queued jobs, while allowing a follow-up queued job when one for the same table is already running
- [ ] Keep record-changed behavior unchanged
- [ ] Re-run the focused tests and confirm they pass

### Task 3: Cover and implement table-resync execution

**Files:**
- Modify: `tests/test_job_runner.py`
- Modify: `tests/test_full_sync.py` or add a dedicated focused sync test file if clearer
- Modify: `worker/job_runner.py`
- Modify: `app/services/full_sync.py` or add a focused helper there if it keeps boundaries cleaner

- [ ] Add failing tests for a new worker job type that refreshes exactly one table's `field_schema_json` and all rows for that `table_id`
- [ ] Make the tests assert that:
  - rows from other tables are untouched
  - monitor counts/status update correctly
  - the sync run is distinguishable from record-level incremental sync
- [ ] Implement the minimal table-resync path and hook it into `run_next_job()`
- [ ] Re-run the focused tests and confirm they pass

### Task 4: Register the new Feishu event type

**Files:**
- Modify: `app/clients/feishu.py`
- Modify: `tests/test_feishu_client.py` if event registration coverage exists or needs extension

- [ ] Add a failing test that proves the websocket event dispatcher registers `drive.file.bitable_field_changed_v1`
- [ ] Implement the minimal additional registration without disturbing `drive.file.bitable_record_changed_v1`
- [ ] Re-run the focused tests and confirm they pass

### Task 5: Regression verification

**Files:**
- Modify: none unless regressions force targeted fixes
- Test: `tests/test_event_processor.py`
- Test: `tests/test_job_runner.py`
- Test: `tests/test_full_sync.py`
- Test: `tests/test_feishu_client.py`
- Test: `tests/test_worker_main.py`
- Test: full `pytest` suite

- [ ] Run the focused regression set for the touched areas
- [ ] Run the full test suite and confirm all tests pass
- [ ] Review git diff to ensure no unrelated user changes were overwritten
