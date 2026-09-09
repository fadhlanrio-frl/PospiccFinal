"""
app.py
Home page of the Pospicc Product Intelligence Dashboard.
Shows the top-level alert summary and the Sales module. Other modules live
under pages/ (Streamlit multipage app).
"""
from datetime import datetime

import streamlit as st

import config
import database as db

st.set_page_config(page_title="Pospicc Intelligence Dashboard", page_icon="🧥", layout="wide")

db.init_db()

if config.ENABLE_PLUGO_SYNC:
    import scheduler
    scheduler.start_scheduler(interval_minutes=config.PLUGO_SYNC_INTERVAL_MINUTES)

if config.SHOPEE_API_CONFIGURED and db.get_shopee_tokens():
    import shopee_scheduler
    shopee_scheduler.start_scheduler(interval_minutes=config.SHOPEE_SYNC_INTERVAL_MINUTES)

st.title("🧥 Pospicc Product Intelligence Dashboard")
st.caption("Data-driven second opinion for product, restock, funding, and marketing decisions.")

# --- Top bar: sync/import status, depends on which sources are active -------
col1, col2, col3, col4 = st.columns([2, 2, 2, 4])

with col1:
    st.page_link("pages/00_📥_Import_Data.py", label="📥 Import Data / Shopee", use_container_width=True)

if config.ENABLE_PLUGO_SYNC:
    with col2:
        if st.button("🔄 Sync Plugo now", use_container_width=True):
            import plugo_client
            with st.spinner("Syncing sales, inventory, and running alert checks..."):
                try:
                    scheduler.sync_once()
                except plugo_client.PlugoAPIError as e:
                    st.error(f"Sync Plugo gagal: {e}")
                else:
                    st.success("Sync complete.")

shopee_connected = bool(config.SHOPEE_API_CONFIGURED and db.get_shopee_tokens())
if shopee_connected:
    with col3:
        if st.button("🔄 Sync Shopee now", use_container_width=True):
            import shopee_scheduler
            import shopee_api_client
            with st.spinner("Menarik order, produk, dan stok terbaru dari Shopee..."):
                try:
                    shopee_scheduler.sync_once()
                except shopee_api_client.ShopeeAPIError as e:
                    st.error(f"Sync Shopee gagal: {e}")
                else:
                    st.success("Sync Shopee selesai.")

with col4:
    freshness = db.fetch_df("SELECT module, last_updated, status FROM data_sources")
    if not freshness.empty:
        stale_count = (freshness["status"] != "current").sum()
        if stale_count == 0:
            st.success("All modules current")
        else:
            st.warning(f"{stale_count} module(s) stale/incomplete")
    elif shopee_connected:
        st.info("Shopee terhubung - sync otomatis tiap "
                 f"{config.SHOPEE_SYNC_INTERVAL_MINUTES} menit, atau klik 'Sync Shopee now'.")
    else:
        st.info("Belum ada data. Hubungkan Shopee atau import data lewat halaman Import Data.")

st.divider()

# --- Alert Summary (this is the GM's first stop every day) --------------
st.subheader("🔔 Active Alerts")
recent_alerts = db.fetch_df(
    "SELECT triggered_at, alert_type, sku, message, severity FROM alerts_log "
    "WHERE triggered_at >= datetime('now', '-24 hours') ORDER BY triggered_at DESC"
)
if recent_alerts.empty:
    hint = " and/or ".join(
        filter(
            None,
            [
                "connect/sync Shopee" if shopee_connected else None,
                "import data via the Import Data page" if config.ENABLE_EXCEL_IMPORT else None,
                "run a Plugo sync" if config.ENABLE_PLUGO_SYNC else None,
            ],
        )
    )
    st.info(f"No alerts in the last 24 hours. Try to {hint} if you haven't yet.")
else:
    severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    for _, row in recent_alerts.iterrows():
        icon = severity_icon.get(row["severity"], "⚪")
        st.write(
            f"{icon} **[{row['alert_type']}]** {row['message']}  \n"
            f"<span style='color:gray;font-size:0.8em'>{row['triggered_at']} UTC</span>",
            unsafe_allow_html=True,
        )

st.divider()

# --- Sales Module ---------------------------------------------------------
st.subheader("📈 Sales")

sales_ref = db.get_sales_reference_datetime()
sales = db.fetch_df(
    """
    SELECT p.sku, p.product_name,
           SUM(s.units_sold) AS units_sold,
           SUM(s.revenue) AS revenue,
           ROUND(SUM(s.revenue) * 1.0 / NULLIF(SUM(s.units_sold), 0), 0) AS avg_selling_price,
           ROUND(SUM(s.units_sold) * 1.0 / 7, 2) AS daily_velocity
    FROM sales_orders s
    JOIN products p ON p.sku = s.sku
    WHERE s.order_date >= datetime(?, '-7 days')
    GROUP BY p.sku, p.product_name
    ORDER BY revenue DESC
    """,
    (sales_ref,),
)
if not sales.empty:
    st.caption(f"Menampilkan 7 hari data terakhir yang tersedia (hingga {sales_ref[:10]}).")

if sales.empty:
    hint = " atau ".join(
        filter(
            None,
            [
                "hubungkan/sync Shopee di atas" if shopee_connected else None,
                "upload data lewat halaman 'Import Data' di sidebar" if config.ENABLE_EXCEL_IMPORT else None,
                "klik 'Sync Plugo now' di atas" if config.ENABLE_PLUGO_SYNC else None,
            ],
        )
    )
    st.info(f"Belum ada data sales. Coba {hint} untuk menarik data terbaru.")
else:
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Revenue (7d)", f"Rp{sales['revenue'].sum():,.0f}")
    col_b.metric("Total Units (7d)", f"{sales['units_sold'].sum():,.0f}")
    col_c.metric("Avg. Selling Price", f"Rp{sales['avg_selling_price'].mean():,.0f}")

    st.markdown("**Top Sellers**")
    st.dataframe(sales.head(5), use_container_width=True, hide_index=True)

    st.markdown("**Slow Movers** (lowest daily velocity, still in catalog)")
    all_products = db.fetch_df("SELECT sku, product_name FROM products")
    slow = all_products.merge(sales[["sku", "daily_velocity"]], on="sku", how="left").fillna(0)
    slow = slow.sort_values("daily_velocity").head(5)
    st.dataframe(slow, use_container_width=True, hide_index=True)

    st.markdown("**Revenue by Product**")
    st.bar_chart(sales.set_index("product_name")["revenue"])

st.divider()
st.caption(
    "Modules: use the sidebar to navigate to Import Data, Inventory, Profitability, Marketing, "
    "Product Intelligence, Data Reliability, AI Assistant, Alerts, Shipping & Logistics, "
    "Customer Geography, Customer Insights, Discounts & Vouchers, Returns & Cancellations, "
    "and Fees & Settlement."
)
