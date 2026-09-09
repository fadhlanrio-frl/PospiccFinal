"""alerts.py - alert rule engine, see README."""
from datetime import datetime, timedelta

import config
import database as db


def run_all_checks():
    check_low_stock_and_stockout()
    check_sales_spike()
    check_stale_data()
    check_marketing_overspend_low_roas()
    check_sku_conflicts()


def check_low_stock_and_stockout():
    inv = db.fetch_df(
        """
        SELECT i.sku, p.product_name, i.stock_on_hand
        FROM inventory_snapshots i
        JOIN products p ON p.sku = i.sku
        WHERE i.id IN (SELECT MAX(id) FROM inventory_snapshots GROUP BY sku)
        """
    )
    sales_ref = db.get_sales_reference_datetime()
    sales_velocity = db.fetch_df(
        """
        SELECT sku, SUM(units_sold) * 1.0 / 7 AS daily_velocity
        FROM sales_orders
        WHERE order_date >= datetime(?, '-7 days')
        GROUP BY sku
        """,
        (sales_ref,),
    )
    velocity_map = dict(zip(sales_velocity["sku"], sales_velocity["daily_velocity"]))

    for _, row in inv.iterrows():
        stock = row["stock_on_hand"]
        velocity = velocity_map.get(row["sku"], 0)
        if stock <= config.LOW_STOCK_THRESHOLD_UNITS:
            db.log_alert(
                "low_stock", row["sku"],
                f"{row['product_name']} stok tersisa {stock} unit (di bawah ambang {config.LOW_STOCK_THRESHOLD_UNITS}).",
                severity="warning",
            )
        if velocity > 0:
            days_to_stockout = stock / velocity
            if days_to_stockout <= config.LOW_STOCK_DAYS_TO_STOCKOUT:
                db.log_alert(
                    "projected_stockout", row["sku"],
                    f"{row['product_name']} diperkirakan habis dalam {days_to_stockout:.1f} hari "
                    f"berdasarkan kecepatan jual {velocity:.1f} unit/hari.",
                    severity="critical",
                )


def check_sales_spike():
    sales_ref = db.get_sales_reference_datetime()
    recent = db.fetch_df(
        """
        SELECT sku, SUM(units_sold) AS units
        FROM sales_orders WHERE order_date >= datetime(?, '-1 days') GROUP BY sku
        """,
        (sales_ref,),
    )
    baseline = db.fetch_df(
        """
        SELECT sku, SUM(units_sold) * 1.0 / 7 AS avg_daily
        FROM sales_orders
        WHERE order_date >= datetime(?, '-7 days') AND order_date < datetime(?, '-1 days')
        GROUP BY sku
        """,
        (sales_ref, sales_ref),
    )
    baseline_map = dict(zip(baseline["sku"], baseline["avg_daily"]))
    for _, row in recent.iterrows():
        base = baseline_map.get(row["sku"], 0)
        if base > 0 and row["units"] >= base * config.SALES_SPIKE_MULTIPLIER:
            db.log_alert(
                "sales_spike", row["sku"],
                f"Penjualan {row['sku']} melonjak: {row['units']} unit dalam 24 jam vs rata-rata {base:.1f} unit/hari.",
                severity="info",
            )


def check_stale_data():
    sources = db.fetch_df("SELECT * FROM data_sources")
    cutoff = datetime.utcnow() - timedelta(hours=config.STALE_DATA_HOURS)
    for _, row in sources.iterrows():
        if not row["last_updated"]:
            continue
        last_updated = datetime.fromisoformat(row["last_updated"])
        if last_updated < cutoff:
            db.log_alert(
                "stale_data", None,
                f"Modul '{row['module']}' belum diperbarui sejak {row['last_updated']} (sumber: {row['source']}).",
                severity="warning",
            )


def check_marketing_overspend_low_roas():
    marketing_ref = db.get_marketing_reference_date()
    perf = db.fetch_df(
        """
        SELECT sku, SUM(ads_spend) AS spend, SUM(attributed_revenue) AS revenue
        FROM marketing_metrics
        WHERE metric_date >= date(?, '-7 days') AND is_paid = 1
        GROUP BY sku HAVING spend > 0
        """,
        (marketing_ref,),
    )
    for _, row in perf.iterrows():
        roas = row["revenue"] / row["spend"] if row["spend"] else 0
        if roas < config.LOW_ROAS_THRESHOLD:
            db.log_alert(
                "low_roas", row["sku"],
                f"ROAS {row['sku']} hanya {roas:.2f}x dalam 7 hari terakhir "
                f"(spend Rp{row['spend']:,.0f}, revenue Rp{row['revenue']:,.0f}).",
                severity="warning",
            )


def check_sku_conflicts():
    dupes = db.fetch_df(
        """
        SELECT product_name, COUNT(DISTINCT sku) AS sku_count
        FROM products GROUP BY product_name HAVING sku_count > 1
        """
    )
    for _, row in dupes.iterrows():
        db.log_alert(
            "sku_conflict", None,
            f"Nama produk '{row['product_name']}' terhubung ke {row['sku_count']} SKU berbeda - cek duplikasi.",
            severity="warning",
        )
