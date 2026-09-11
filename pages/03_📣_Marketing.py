from datetime import date

import numpy as np
import streamlit as st

import config
import database as db

db.init_db()

st.set_page_config(page_title="Marketing - Pospicc", page_icon="📣", layout="wide")
st.title("📣 Marketing")

with st.expander("➕ Input data marketing manual"):
    products = db.fetch_df("SELECT sku, product_name FROM products")
    if products.empty:
        st.info("Isi produk lewat Import Data dulu sebelum input data marketing.")
    else:
        with st.form("marketing_entry"):
            sku = st.selectbox("Produk", products["sku"])
            metric_date = st.date_input("Tanggal", value=date.today())
            ads_spend = st.number_input("Ads spend (Rp)", min_value=0.0, step=10000.0)
            attributed_revenue = st.number_input("Attributed revenue (Rp)", min_value=0.0, step=10000.0)
            is_paid = st.checkbox("Ini traffic berbayar (paid)?", value=True)
            entered_by = st.text_input("Diinput oleh", value="Marketing Team")
            submitted = st.form_submit_button("Simpan")
            if submitted:
                db.insert_marketing_metrics([{
                    "sku": sku, "metric_date": metric_date.isoformat(),
                    "ads_spend": ads_spend, "attributed_revenue": attributed_revenue,
                    "is_paid": int(is_paid),
                }])
                db.mark_data_source("Marketing", entered_by, "Manual entry", "current")
                st.success("Data marketing tersimpan.")
                st.rerun()

st.divider()

perf = db.fetch_df(
    """
    SELECT p.sku, p.product_name,
           SUM(m.ads_spend) AS ads_spend,
           SUM(m.attributed_revenue) AS attributed_revenue,
           SUM(CASE WHEN m.is_paid = 1 THEN m.ads_spend ELSE 0 END) AS paid_spend,
           SUM(CASE WHEN m.is_paid = 0 THEN m.attributed_revenue ELSE 0 END) AS organic_revenue
    FROM marketing_metrics m
    JOIN products p ON p.sku = m.sku
    WHERE m.metric_date >= date(?, '-30 days')
    GROUP BY p.sku, p.product_name
    """,
    (db.get_marketing_reference_date(),),
)

if perf.empty:
    st.info("Belum ada data marketing. Tambahkan lewat form di atas.")
else:
    perf["roas"] = (perf["attributed_revenue"] / perf["ads_spend"].replace(0, np.nan)).round(2)
    perf["needs_support"] = perf["roas"] < config.LOW_ROAS_THRESHOLD

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Ads Spend (30d)", f"Rp{perf['ads_spend'].sum():,.0f}")
    col2.metric("Total Attributed Revenue (30d)", f"Rp{perf['attributed_revenue'].sum():,.0f}")
    col3.metric("Blended ROAS", f"{(perf['attributed_revenue'].sum() / perf['ads_spend'].sum()):.2f}x" if perf["ads_spend"].sum() else "N/A")

    st.markdown("**Performance by Product**")
    st.dataframe(
        perf[["sku", "product_name", "ads_spend", "attributed_revenue", "roas", "needs_support"]].sort_values("roas"),
        use_container_width=True, hide_index=True,
    )
    needing_support = perf[perf["needs_support"] == True]  # noqa: E712
    if not needing_support.empty:
        st.warning(f"⚠️ {len(needing_support)} produk dengan ROAS di bawah {config.LOW_ROAS_THRESHOLD}x - kandidat untuk investigasi lebih lanjut atau penyesuaian budget.")
