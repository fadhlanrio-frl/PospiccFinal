"""
database.py
SQLite layer for the whole dashboard.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT,
    hpp REAL DEFAULT 0,
    selling_price REAL DEFAULT 0,
    product_thesis TEXT,
    vendor TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- One row per order (header-level fields: buyer, shipping, payment, location,
-- discounts). Populated by the Shopee API hourly sync (shopee_scheduler.py).
CREATE TABLE IF NOT EXISTS order_headers (
    no_pesanan TEXT PRIMARY KEY,
    status_pesanan TEXT,
    cancellation_status TEXT,
    order_date TEXT,
    payment_time TEXT,
    ship_by_date TEXT,
    arranged_shipping_time TEXT,
    completed_time TEXT,
    payment_method TEXT,
    shipping_option TEXT,
    courier TEXT,
    tracking_number TEXT,
    total_weight_gr REAL,
    total_payment REAL,
    shipping_fee_paid_by_buyer REAL,
    total_discount REAL,
    voucher_seller REAL,
    voucher_shopee REAL,
    cashback_koin REAL,
    creditcard_discount REAL,
    buyer_username TEXT,
    buyer_note TEXT,
    city TEXT,
    province TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);

-- One row per order LINE ITEM (one product within an order). no_pesanan links
-- back to order_headers for shipping/buyer/location context.
CREATE TABLE IF NOT EXISTS sales_orders (
    order_id TEXT PRIMARY KEY,
    no_pesanan TEXT,
    sku TEXT NOT NULL,
    variant_name TEXT,
    order_date TEXT NOT NULL,
    units_sold INTEGER NOT NULL,
    returned_quantity INTEGER DEFAULT 0,
    revenue REAL NOT NULL,
    channel TEXT,
    synced_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sku) REFERENCES products (sku)
);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    stock_on_hand INTEGER NOT NULL,
    reserved_stock INTEGER DEFAULT 0,
    snapshot_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sku) REFERENCES products (sku)
);

CREATE TABLE IF NOT EXISTS marketing_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    ads_spend REAL DEFAULT 0,
    attributed_revenue REAL DEFAULT 0,
    is_paid INTEGER DEFAULT 1,
    synced_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sku) REFERENCES products (sku)
);

CREATE TABLE IF NOT EXISTS product_intelligence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    entry_date TEXT DEFAULT (datetime('now')),
    market_sentiment TEXT,
    internal_observation TEXT,
    customer_likes TEXT,
    customer_dislikes TEXT,
    vendor_concerns TEXT,
    entered_by TEXT,
    FOREIGN KEY (sku) REFERENCES products (sku)
);

CREATE TABLE IF NOT EXISTS data_sources (
    module TEXT PRIMARY KEY,
    last_updated TEXT,
    updated_by TEXT,
    source TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS alerts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at TEXT DEFAULT (datetime('now')),
    alert_type TEXT,
    sku TEXT,
    message TEXT,
    severity TEXT
);

CREATE TABLE IF NOT EXISTS marketplace_income_summary (
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    marketplace TEXT NOT NULL DEFAULT 'Shopee',
    username TEXT,
    total_pendapatan REAL,
    total_pengeluaran REAL,
    total_dilepas REAL,
    imported_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (period_start, period_end, marketplace)
);

-- One row per order, from the Income Report's per-order fee breakdown -
-- gives ACTUAL Shopee fees (not estimates) for true net-profit calculations.
CREATE TABLE IF NOT EXISTS order_settlements (
    no_pesanan TEXT PRIMARY KEY,
    order_date TEXT,
    release_date TEXT,
    total_income REAL,
    biaya_administrasi REAL DEFAULT 0,
    biaya_proses_pesanan REAL DEFAULT 0,
    biaya_transaksi REAL DEFAULT 0,
    biaya_komisi_ams REAL DEFAULT 0,
    biaya_kampanye REAL DEFAULT 0,
    pph22 REAL DEFAULT 0,
    other_fees REAL DEFAULT 0,
    source TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);

-- Shopee Open Platform OAuth tokens (access_token expires every 4h, refreshed
-- automatically using refresh_token which expires every 30d - these rotate
-- constantly so they live here, never as static values in .env). Single-shop
-- dashboard, so shop_id is the natural key - one row per authorized shop.
CREATE TABLE IF NOT EXISTS shopee_oauth_tokens (
    shop_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    access_token_expires_at TEXT NOT NULL,
    refresh_token_expires_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def save_shopee_tokens(shop_id: str, access_token: str, refresh_token: str,
                        access_token_expires_at: str, refresh_token_expires_at: str | None = None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO shopee_oauth_tokens
                (shop_id, access_token, refresh_token, access_token_expires_at, refresh_token_expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(shop_id) DO UPDATE SET
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                access_token_expires_at=excluded.access_token_expires_at,
                refresh_token_expires_at=excluded.refresh_token_expires_at,
                updated_at=datetime('now')
            """,
            (shop_id, access_token, refresh_token, access_token_expires_at, refresh_token_expires_at),
        )


def get_shopee_tokens() -> dict | None:
    """Returns the most recently connected Shopee shop's tokens, or None if
    no shop has ever been authorized yet."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM shopee_oauth_tokens ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_sales_reference_datetime() -> str:
    """Anchor for every 'last N days' sales/inventory window in the dashboard.
    Data arrives in historical batches (Excel/Shopee export), not live, so
    windows are anchored to the most recent order_date instead of wall-clock
    time - otherwise every module goes blank as soon as 'now' drifts past
    whatever period the last import covered."""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(order_date) AS latest FROM sales_orders").fetchone()
    return row["latest"] if row and row["latest"] else datetime.utcnow().isoformat()


def get_marketing_reference_date() -> str:
    """Same idea as get_sales_reference_datetime(), anchored to marketing_metrics
    (metric_date is date-only, no time component)."""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(metric_date) AS latest FROM marketing_metrics").fetchone()
    return row["latest"] if row and row["latest"] else datetime.utcnow().strftime("%Y-%m-%d")


def mark_data_source(module: str, updated_by: str, source: str, status: str = "current"):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO data_sources (module, last_updated, updated_by, source, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(module) DO UPDATE SET
                last_updated=excluded.last_updated,
                updated_by=excluded.updated_by,
                source=excluded.source,
                status=excluded.status
            """,
            (module, datetime.utcnow().isoformat(), updated_by, source, status),
        )


def upsert_products(products: list[dict]):
    with get_conn() as conn:
        for p in products:
            conn.execute(
                """
                INSERT INTO products (sku, product_name, category, hpp, selling_price, vendor)
                VALUES (:sku, :product_name, :category, :hpp, :selling_price, :vendor)
                ON CONFLICT(sku) DO UPDATE SET
                    product_name=excluded.product_name,
                    category=excluded.category,
                    hpp=excluded.hpp,
                    selling_price=excluded.selling_price,
                    vendor=excluded.vendor
                """,
                p,
            )


def upsert_order_headers(headers: list[dict]):
    with get_conn() as conn:
        for h in headers:
            cols = ", ".join(h.keys())
            placeholders = ", ".join(f":{k}" for k in h.keys())
            update_clause = ", ".join(f"{k}=excluded.{k}" for k in h.keys() if k != "no_pesanan")
            conn.execute(
                f"""
                INSERT INTO order_headers ({cols}) VALUES ({placeholders})
                ON CONFLICT(no_pesanan) DO UPDATE SET {update_clause}
                """,
                h,
            )


def insert_sales_orders(orders: list[dict]):
    with get_conn() as conn:
        for o in orders:
            o.setdefault("no_pesanan", None)
            o.setdefault("variant_name", None)
            o.setdefault("returned_quantity", 0)
            conn.execute(
                """
                INSERT OR REPLACE INTO sales_orders
                    (order_id, no_pesanan, sku, variant_name, order_date, units_sold,
                     returned_quantity, revenue, channel)
                VALUES (:order_id, :no_pesanan, :sku, :variant_name, :order_date, :units_sold,
                        :returned_quantity, :revenue, :channel)
                """,
                o,
            )


def insert_inventory_snapshots(snapshots: list[dict]):
    with get_conn() as conn:
        for s in snapshots:
            conn.execute(
                """
                INSERT INTO inventory_snapshots (sku, stock_on_hand, reserved_stock)
                VALUES (:sku, :stock_on_hand, :reserved_stock)
                """,
                s,
            )


def insert_marketing_metrics(rows: list[dict]):
    with get_conn() as conn:
        for r in rows:
            conn.execute(
                """
                INSERT INTO marketing_metrics
                    (sku, metric_date, ads_spend, attributed_revenue, is_paid)
                VALUES (:sku, :metric_date, :ads_spend, :attributed_revenue, :is_paid)
                """,
                r,
            )


def add_product_intelligence(entry: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO product_intelligence
                (sku, market_sentiment, internal_observation, customer_likes,
                 customer_dislikes, vendor_concerns, entered_by)
            VALUES (:sku, :market_sentiment, :internal_observation, :customer_likes,
                    :customer_dislikes, :vendor_concerns, :entered_by)
            """,
            entry,
        )


def log_alert(alert_type: str, sku: str, message: str, severity: str = "warning"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts_log (alert_type, sku, message, severity) VALUES (?, ?, ?, ?)",
            (alert_type, sku, message, severity),
        )


def get_existing_products() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT sku, hpp FROM products").fetchall()
        return {r["sku"]: r["hpp"] for r in rows}


def upsert_income_summary(record: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO marketplace_income_summary
                (period_start, period_end, marketplace, username,
                 total_pendapatan, total_pengeluaran, total_dilepas)
            VALUES (:period_start, :period_end, :marketplace, :username,
                    :total_pendapatan, :total_pengeluaran, :total_dilepas)
            ON CONFLICT(period_start, period_end, marketplace) DO UPDATE SET
                username=excluded.username,
                total_pendapatan=excluded.total_pendapatan,
                total_pengeluaran=excluded.total_pengeluaran,
                total_dilepas=excluded.total_dilepas,
                imported_at=datetime('now')
            """,
            record,
        )


def upsert_order_settlements(settlements: list[dict]):
    with get_conn() as conn:
        for s in settlements:
            conn.execute(
                """
                INSERT INTO order_settlements
                    (no_pesanan, order_date, release_date, total_income, biaya_administrasi,
                     biaya_proses_pesanan, biaya_transaksi, biaya_komisi_ams, biaya_kampanye,
                     pph22, other_fees, source)
                VALUES (:no_pesanan, :order_date, :release_date, :total_income, :biaya_administrasi,
                        :biaya_proses_pesanan, :biaya_transaksi, :biaya_komisi_ams, :biaya_kampanye,
                        :pph22, :other_fees, :source)
                ON CONFLICT(no_pesanan) DO UPDATE SET
                    order_date=excluded.order_date,
                    release_date=excluded.release_date,
                    total_income=excluded.total_income,
                    biaya_administrasi=excluded.biaya_administrasi,
                    biaya_proses_pesanan=excluded.biaya_proses_pesanan,
                    biaya_transaksi=excluded.biaya_transaksi,
                    biaya_komisi_ams=excluded.biaya_komisi_ams,
                    biaya_kampanye=excluded.biaya_kampanye,
                    pph22=excluded.pph22,
                    other_fees=excluded.other_fees,
                    source=excluded.source,
                    imported_at=datetime('now')
                """,
                s,
            )


def fetch_df(query: str, params: tuple = ()):
    import pandas as pd

    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)
