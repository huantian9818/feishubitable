from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import json

from app.clients.feishu import FeishuApiError, FeishuBitableClient
from app.clock import system_now
from app.models import BitableTable, CurrentRecord, EventLog, Monitor, SyncRun, WorkerJob
from app.services.fallback_schedule import PRESET_INTERVALS, compute_next_fallback_at
from app.services.link_parser import resolve_bitable_app_token
from app.services.view_models import build_current_record_view
from app.web.dependencies import get_session
from app.web.templating import templates

router = APIRouter()
PAGE_SIZE = 20
RUN_HISTORY_LIMIT = 50


def _field_names_from_schema(field_schema_json: str | None) -> list[str]:
    if not field_schema_json:
        return []

    try:
        schema = json.loads(field_schema_json)
    except json.JSONDecodeError:
        return []

    field_names = []
    for field in schema:
        field_name = field.get("field_name") if isinstance(field, dict) else None
        if field_name:
            field_names.append(str(field_name))
    return field_names


def _job_source_event_id(job: WorkerJob) -> str | None:
    if not job.payload_json:
        return None

    try:
        payload = json.loads(job.payload_json)
    except json.JSONDecodeError:
        return None

    source_event_id = payload.get("source_event_id") if isinstance(payload, dict) else None
    return str(source_event_id) if source_event_id else None


def _format_delay_seconds(total_seconds: float | None) -> str:
    if total_seconds is None:
        return "-"

    seconds = max(0, int(total_seconds))
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}小时{minutes}分{remainder}秒"
    if minutes:
        return f"{minutes}分{remainder}秒"
    return f"{remainder}秒"


def _build_worker_job_rows(worker_jobs: list[WorkerJob], event_logs: list[EventLog]) -> list[dict]:
    event_logs_by_event_id = {event_log.event_id: event_log for event_log in event_logs}
    job_index_by_id = {job.id: index for index, job in enumerate(reversed(worker_jobs), start=1)}
    rows = []
    for job in worker_jobs:
        event_log = event_logs_by_event_id.get(_job_source_event_id(job) or "")
        delivery_delay = None
        if event_log is not None and event_log.event_time and event_log.created_at:
            delivery_delay = (event_log.created_at - event_log.event_time).total_seconds()

        rows.append(
            {
                "job": job,
                "event_log": event_log,
                "delivery_delay_text": _format_delay_seconds(delivery_delay),
                "monitor_job_index": job_index_by_id[job.id],
            }
        )
    return rows


def _build_sync_run_rows(sync_runs: list[SyncRun]) -> list[dict]:
    run_index_by_id = {run.id: index for index, run in enumerate(reversed(sync_runs), start=1)}
    return [
        {
            "run": run,
            "monitor_run_index": run_index_by_id[run.id],
        }
        for run in sync_runs
    ]


def _render_monitor_form(
    request: Request,
    *,
    errors: list[str] | None = None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "monitor_form.html",
        {
            "preset_intervals": PRESET_INTERVALS,
            "errors": errors or [],
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


def _delete_monitor_graph(session: Session, monitor_id: int) -> None:
    from app.models import TableJobLease

    session.query(CurrentRecord).filter(CurrentRecord.monitor_id == monitor_id).delete()
    session.query(BitableTable).filter(BitableTable.monitor_id == monitor_id).delete()
    session.query(EventLog).filter(EventLog.monitor_id == monitor_id).delete()
    session.query(SyncRun).filter(SyncRun.monitor_id == monitor_id).delete()
    session.query(WorkerJob).filter(WorkerJob.monitor_id == monitor_id).delete()
    session.query(TableJobLease).filter(TableJobLease.monitor_id == monitor_id).delete()
    session.query(Monitor).filter(Monitor.id == monitor_id).delete()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    monitors = session.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "monitors.html",
        {"monitors": monitors, "preset_intervals": PRESET_INTERVALS},
    )


@router.get("/monitors", response_class=HTMLResponse)
def list_monitors(request: Request, session: Session = Depends(get_session)):
    monitors = session.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "monitors.html",
        {"monitors": monitors, "preset_intervals": PRESET_INTERVALS},
    )


@router.get("/monitors/new", response_class=HTMLResponse)
def new_monitor_form(request: Request):
    return _render_monitor_form(request)


@router.post("/monitors")
def create_monitor(
    request: Request,
    name: str = Form(...),
    source_url: str = Form(...),
    fallback_choice: str = Form("preset"),
    fallback_interval_minutes: int = Form(...),
    session: Session = Depends(get_session),
):
    del fallback_choice

    cleaned_name = name.strip()
    cleaned_source_url = source_url.strip()
    form_data = {
        "name": cleaned_name,
        "source_url": cleaned_source_url,
        "fallback_interval_minutes": str(fallback_interval_minutes),
    }

    try:
        app_token = resolve_bitable_app_token(cleaned_source_url, FeishuBitableClient())
    except (ValueError, FeishuApiError) as error:
        return _render_monitor_form(request, errors=[str(error)], form_data=form_data)

    if fallback_interval_minutes not in PRESET_INTERVALS:
        return _render_monitor_form(
            request,
            errors=["请选择允许的低频全量间隔"],
            form_data=form_data,
        )

    monitor = Monitor(
        name=cleaned_name,
        source_url=cleaned_source_url,
        app_token=app_token,
        fallback_interval_minutes=fallback_interval_minutes,
        next_fallback_sync_at=compute_next_fallback_at(system_now(), fallback_interval_minutes),
    )

    try:
        session.add(monitor)
        session.flush()
        session.add(
            WorkerJob(
                job_type="initial_full_sync",
                monitor_id=monitor.id,
                status="queued",
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return RedirectResponse(url=f"/monitors/{monitor.id}", status_code=303)


@router.post("/monitors/{monitor_id}/delete")
def delete_monitor(
    monitor_id: int,
    session: Session = Depends(get_session),
):
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    try:
        _delete_monitor_graph(session, monitor_id)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return RedirectResponse(url="/monitors", status_code=303)


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
def monitor_detail(
    monitor_id: int,
    request: Request,
    tab: str | None = None,
    page: int = 1,
    session: Session = Depends(get_session),
):
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    latest_job = (
        session.query(WorkerJob)
        .filter(WorkerJob.monitor_id == monitor_id)
        .order_by(WorkerJob.created_at.desc(), WorkerJob.id.desc())
        .first()
    )
    tables = (
        session.query(BitableTable)
        .filter(BitableTable.monitor_id == monitor_id)
        .order_by(BitableTable.id.asc())
        .all()
    )
    table_counts = dict(
        session.query(CurrentRecord.table_id, func.count(CurrentRecord.id))
        .filter(CurrentRecord.monitor_id == monitor_id)
        .group_by(CurrentRecord.table_id)
        .all()
    )
    table_views = [
        {
            "id": table.table_id,
            "label": table.table_name,
            "count": table_counts.get(table.table_id, 0),
            "field_names": _field_names_from_schema(table.field_schema_json),
        }
        for table in tables
    ]
    available_table_ids = {table["id"] for table in table_views}
    selected_table_id = tab if tab in available_table_ids else (table_views[0]["id"] if table_views else None)
    selected_table = next((table for table in table_views if table["id"] == selected_table_id), None)
    total_count = selected_table["count"] if selected_table else 0
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE) if total_count else 1
    current_page = min(max(page, 1), total_pages)
    offset = (current_page - 1) * PAGE_SIZE
    records = []
    if selected_table_id is not None:
        records = (
            session.query(CurrentRecord)
            .filter(
                CurrentRecord.monitor_id == monitor_id,
                CurrentRecord.table_id == selected_table_id,
            )
            .order_by(
                CurrentRecord.sort_order.is_(None),
                CurrentRecord.sort_order.asc(),
                CurrentRecord.id.asc(),
            )
            .offset(offset)
            .limit(PAGE_SIZE)
            .all()
        )
    current_record_view = build_current_record_view(
        records=records,
        tables=table_views,
        active_table_id=selected_table_id,
        page=current_page,
        page_size=PAGE_SIZE,
    )
    return templates.TemplateResponse(
        request,
        "monitor_detail.html",
        {
            "monitor": monitor,
            "latest_job": latest_job,
            "current_record_view": current_record_view,
        },
    )


@router.get("/monitors/{monitor_id}/runs", response_class=HTMLResponse)
def monitor_runs(
    monitor_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    sync_runs = (
        session.query(SyncRun)
        .filter(SyncRun.monitor_id == monitor_id)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
        .limit(RUN_HISTORY_LIMIT)
        .all()
    )
    worker_jobs = (
        session.query(WorkerJob)
        .filter(WorkerJob.monitor_id == monitor_id)
        .order_by(WorkerJob.created_at.desc(), WorkerJob.id.desc())
        .limit(RUN_HISTORY_LIMIT)
        .all()
    )
    source_event_ids = [event_id for event_id in (_job_source_event_id(job) for job in worker_jobs) if event_id]
    related_event_logs = []
    if source_event_ids:
        related_event_logs = (
            session.query(EventLog)
            .filter(
                EventLog.monitor_id == monitor_id,
                EventLog.event_id.in_(source_event_ids),
            )
            .all()
        )
    return templates.TemplateResponse(
        request,
        "monitor_runs.html",
        {
            "monitor": monitor,
            "sync_run_rows": _build_sync_run_rows(sync_runs),
            "worker_job_rows": _build_worker_job_rows(worker_jobs, related_event_logs),
            "run_history_limit": RUN_HISTORY_LIMIT,
        },
    )
