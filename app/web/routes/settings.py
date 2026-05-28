from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.main import get_session, templates
from app.models import AppSetting

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    setting = session.query(AppSetting).order_by(AppSetting.id).first()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"setting": setting},
    )


@router.post("/settings")
def save_settings(
    app_id: str = Form(""),
    app_secret: str = Form(""),
    tenant_key: str = Form(""),
    timezone: str = Form("Asia/Shanghai"),
    session: Session = Depends(get_session),
):
    setting = session.query(AppSetting).order_by(AppSetting.id).first()
    if setting is None:
        setting = AppSetting()

    setting.app_id = app_id.strip() or None
    setting.app_secret = app_secret.strip() or None
    setting.tenant_key = tenant_key.strip() or None
    setting.timezone = timezone.strip() or "Asia/Shanghai"

    session.add(setting)
    session.commit()
    return RedirectResponse(url="/settings", status_code=303)
