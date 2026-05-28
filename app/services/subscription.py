from __future__ import annotations

from app.models import Monitor


def resubscribe_monitor(session, monitor_id: int, client):
    monitor = session.get(Monitor, monitor_id)
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} does not exist")

    try:
        if hasattr(client, "refresh_bitable_subscription"):
            result = client.refresh_bitable_subscription(monitor.app_token)
        elif hasattr(client, "subscribe_bitable"):
            result = client.subscribe_bitable(monitor.app_token)
        else:
            result = None

        monitor.subscription_status = "success"
        monitor.subscription_error = None
        session.commit()
        return result
    except Exception as error:
        session.rollback()

        monitor = session.get(Monitor, monitor_id)
        if monitor is None:
            raise ValueError(f"Monitor {monitor_id} does not exist")

        monitor.subscription_status = "failed"
        monitor.subscription_error = str(error)
        session.commit()
        raise
