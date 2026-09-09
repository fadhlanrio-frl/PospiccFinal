"""scheduler.py - background 10-min Plugo sync, only used when DATA_SOURCE_MODE=plugo/both."""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

import alerts
import database as db
import plugo_client

_scheduler = None
_last_synced_at = None


def sync_once():
    global _last_synced_at
    now = datetime.utcnow()
    # First sync (or after a restart) has no prior timestamp to compare against,
    # so fall back to a fixed 15-minute lookback rather than a real elapsed time.
    since_minutes = 15 if _last_synced_at is None else (now - _last_synced_at).total_seconds() / 60
    since_minutes = max(0.0, min(since_minutes, 60.0))

    products = plugo_client.fetch_products()
    if products:
        db.upsert_products(products)
        db.mark_data_source("Sales", "system", "Plugo API", "current")
        db.mark_data_source("Profitability", "system", "Plugo API", "current")

    orders = plugo_client.fetch_recent_orders(since_minutes=since_minutes)
    _last_synced_at = now
    if orders:
        db.insert_sales_orders(orders)
        db.mark_data_source("Sales", "system", "Plugo API", "current")

    try:
        inventory = plugo_client.fetch_inventory()
    except plugo_client.PlugoAPIError as e:
        # Products/orders above may have synced fine even if inventory hasn't
        # been wired up yet - don't let that block the rest of the sync.
        db.mark_data_source("Inventory", "system", "Plugo API", "error: " + str(e))
        inventory = []
    if inventory:
        db.insert_inventory_snapshots(inventory)
        db.mark_data_source("Inventory", "system", "Plugo API", "current")

    alerts.run_all_checks()


def start_scheduler(interval_minutes: int):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_once, "interval", minutes=interval_minutes, id="plugo_sync", next_run_time=None,
    )
    _scheduler.start()
    return _scheduler
