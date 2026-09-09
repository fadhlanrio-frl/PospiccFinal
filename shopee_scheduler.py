"""shopee_scheduler.py - hourly Shopee Open API sync (products, stock, orders).
Only starts once a shop has completed the one-time OAuth connect (see the
Shopee API tab on the Import Data page)."""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import alerts
import database as db
import shopee_api_client

_scheduler = None
_last_synced_at = None


def sync_once():
    global _last_synced_at
    now = datetime.utcnow()
    # First sync (or after a restart) has no prior timestamp - backfill a full
    # day rather than just the last hour, capped by Shopee's 15-day API limit.
    since_minutes = 24 * 60 if _last_synced_at is None else (now - _last_synced_at).total_seconds() / 60

    products, inventory = shopee_api_client.fetch_products_and_inventory()
    known_skus = {p["sku"] for p in products}
    if products:
        db.upsert_products(products)
        db.mark_data_source("Sales", "system", "Shopee API", "current")
        db.mark_data_source("Profitability", "system", "Shopee API", "current")
    if inventory:
        db.insert_inventory_snapshots(inventory)
        db.mark_data_source("Inventory", "system", "Shopee API", "current")

    headers, line_items = shopee_api_client.fetch_recent_orders(since_minutes=since_minutes)
    _last_synced_at = now

    if line_items:
        # Auto-register any SKU seen in an order that get_item_list didn't
        # return (e.g. delisted product) - mirrors the old Excel importer's
        # fallback so Sales never silently drops a line item for a missing FK.
        new_products = []
        for item in line_items:
            sku = item["sku"]
            if sku not in known_skus:
                new_products.append({
                    "sku": sku, "product_name": item.pop("_product_name", sku) or sku,
                    "category": "Uncategorized", "hpp": 0,
                    "selling_price": item.pop("_selling_price", 0) or 0, "vendor": "Shopee",
                })
                known_skus.add(sku)
            else:
                item.pop("_product_name", None)
                item.pop("_selling_price", None)
        if new_products:
            db.upsert_products(new_products)

        db.upsert_order_headers(headers)
        db.insert_sales_orders(line_items)
        db.mark_data_source("Sales", "system", "Shopee API", "current")
        db.mark_data_source("Profitability", "system", "Shopee API", "current")
        _capture_buyer_notes(headers, line_items)

    alerts.run_all_checks()


def _capture_buyer_notes(headers: list[dict], line_items: list[dict]):
    """Mirrors what the old Shopee Excel importer did: surface buyer notes as
    Product Intelligence entries. An order's update_time can fall inside more
    than one hourly sync window as its status changes (unpaid -> shipped ->
    completed), so skip orders already captured to avoid re-adding the same
    note every hour - the marker this writes ("order {no_pesanan}") is parsed
    back out to check that."""
    first_sku_by_order = {}
    for item in line_items:
        first_sku_by_order.setdefault(item["no_pesanan"], item["sku"])

    existing = db.fetch_df(
        "SELECT customer_likes FROM product_intelligence WHERE entered_by = 'Shopee API (auto)'"
    )
    already_captured = set()
    for val in existing["customer_likes"].dropna():
        if val.startswith("[Catatan pembeli, order "):
            already_captured.add(val.split("order ", 1)[1].split("]", 1)[0])

    for h in headers:
        note = h.get("buyer_note")
        no_pesanan = h["no_pesanan"]
        if not note or no_pesanan in already_captured:
            continue
        sku = first_sku_by_order.get(no_pesanan)
        if not sku:
            continue
        db.add_product_intelligence({
            "sku": sku, "market_sentiment": None, "internal_observation": None,
            "customer_likes": f"[Catatan pembeli, order {no_pesanan}]: {note}",
            "customer_dislikes": None, "vendor_concerns": None,
            "entered_by": "Shopee API (auto)",
        })


def start_scheduler(interval_minutes: int):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        sync_once, "interval", minutes=interval_minutes, id="shopee_sync", next_run_time=None,
    )
    _scheduler.start()
    return _scheduler
