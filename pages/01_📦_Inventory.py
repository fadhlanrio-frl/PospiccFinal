import streamlit as st

import config
import database as db

db.init_db()

st.set_page_config(page_title="Inventory - Pospicc", page_icon="📦", layout="wide")
st.title("📦 Inventory")

inv = db.fetch_df(
    """
    SELECT p.sku, p.product_name, i.stock_on_hand, i.reserved_stock,
           (i.stock_on_hand - i.reserved_stock) AS sellable_stock, i.snapshot_at
    FROM inventory_snapshots i
    JOIN products p ON p.sku = i.sku
    WHERE i.id IN (SELECT MAX(id) FROM inventory_snapshots GROUP BY sku)
    ORDER BY sellable_stock ASC
    """
)
velocity = db.fetch_df(
    """
    SELECT sku, SUM(units_sold) * 1.0 / 7 AS daily_velocity
    FROM sales_orders WHERE order_date >= datetime(?, '-7 days') GROUP BY sku
    """,
    (db.get_sales_reference_datetime(),),
)

if inv.empty:
    st.info("Belum ada data inventory. Isi lewat halaman Import Data atau Sync dari Home.")
else:
    inv = inv.merge(velocity, on="sku", how="left").fillna({"daily_velocity": 0})
    inv["low_stock"] = inv["sellable_stock"] <= config.LOW_STOCK_THRESHOLD_UNITS
    inv["est_days_to_stockout"] = inv.apply(
        lambda r: round(r["sellable_stock"] / r["daily_velocity"], 1) if r["daily_velocity"] > 0 else None, axis=1,
    )
    inv["possible_unfulfilled_demand"] = inv.apply(
        lambda r: r["daily_velocity"] > 0 and r["sellable_stock"] == 0, axis=1
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("SKUs Tracked", len(inv))
    col2.metric("Low Stock SKUs", int(inv["low_stock"].sum()))
    col3.metric("Possible Unfulfilled Demand", int(inv["possible_unfulfilled_demand"].sum()))

    def highlight_low(row):
        return ["background-color: #ffe5e5" if row["low_stock"] else "" for _ in row]

    st.dataframe(
        inv[["sku", "product_name", "stock_on_hand", "reserved_stock", "sellable_stock",
             "low_stock", "est_days_to_stockout", "possible_unfulfilled_demand", "snapshot_at"]]
        .style.apply(highlight_low, axis=1),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        f"Low-stock threshold: {config.LOW_STOCK_THRESHOLD_UNITS} units sellable. "
        f"Stockout alert fires when projected days-to-stockout ≤ {config.LOW_STOCK_DAYS_TO_STOCKOUT} days."
    )
