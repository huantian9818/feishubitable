from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.clock import utc_now
from app.main import get_session, templates
from app.models import Monitor, SyncRun, WorkerJob
from app.services.fallback_schedule import PRESET_INTERVALS, compute_next_fallback_at
from app.services.link_parser import parse_bitable_link

router = APIRouter()


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
    return templates.TemplateResponse(
        request,
        "monitor_form.html",
        {"preset_intervals": PRESET_INTERVALS},
    )


@router.post("/monitors")
def create_monitor(
    name: str = Form(...),
    source_url: str = Form(...),
    fallback_choice: str = Form("preset"),
    fallback_interval_minutes: int = Form(...),
    session: Session = Depends(get_session),
):
    del fallback_choice

    app_token = parse_bitable_link(source_url.strip())
    monitor = Monitor(
        name=name.strip(),
        source_url=source_url.strip(),
        app_token=app_token,
        fallback_interval_minutes=fallback_interval_minutes,
        next_fallback_sync_at=compute_next_fallback_at(utc_now(), fallback_interval_minutes),
    )
    session.add(monitor)
    session.commit()

    session.add(
        WorkerJob(
            job_type="initial_full_sync",
            monitor_id=monitor.id,
            status="queued",
        )
    )
    session.commit()
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
