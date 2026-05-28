from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.clock import utc_now
from app.models import Monitor, SyncRun, WorkerJob
from app.services.fallback_schedule import PRESET_INTERVALS, compute_next_fallback_at
from app.services.link_parser import parse_bitable_link
from app.web.dependencies import get_session
from app.web.templating import templates

router = APIRouter()


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
        app_token = parse_bitable_link(cleaned_source_url)
    except ValueError as error:
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
        next_fallback_sync_at=compute_next_fallback_at(utc_now(), fallback_interval_minutes),
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


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
def monitor_detail(
    monitor_id: int,
    request: Request,
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
    return templates.TemplateResponse(
        request,
        "monitor_detail.html",
        {"monitor": monitor, "latest_job": latest_job},
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
        .all()
    )
    worker_jobs = (
        session.query(WorkerJob)
        .filter(WorkerJob.monitor_id == monitor_id)
        .order_by(WorkerJob.created_at.desc(), WorkerJob.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "monitor_runs.html",
        {"monitor": monitor, "sync_runs": sync_runs, "worker_jobs": worker_jobs},
    )
