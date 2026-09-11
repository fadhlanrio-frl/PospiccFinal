import pandas as pd
import streamlit as st

import database as db

db.init_db()

st.set_page_config(page_title="Shipping & Logistics - Pospicc", page_icon="🚚", layout="wide")
st.title("🚚 Shipping & Logistics")
st.caption("Kurir, ketepatan waktu kirim, dan berat paket - dari data order Shopee.")

headers = db.fetch_df(
    """
    SELECT no_pesanan, courier, shipping_option, ship_by_date, arranged_shipping_time,
           completed_time, order_date, total_weight_gr
    FROM order_headers
    """
)

if headers.empty:
    st.info("Belum ada data order. Hubungkan Shopee API lewat halaman Import Data, atau tunggu sync otomatis berikutnya.")
else:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Order Terkirim", len(headers))
    col2.metric("Rata-rata Berat Paket", f"{headers['total_weight_gr'].mean():,.0f} gr" if headers["total_weight_gr"].notna().any() else "N/A")

    # On-time performance: arranged shipping time vs the "must ship before" deadline
    headers["ship_by_dt"] = pd.to_datetime(headers["ship_by_date"], errors="coerce")
    headers["arranged_dt"] = pd.to_datetime(headers["arranged_shipping_time"], errors="coerce")
    valid = headers.dropna(subset=["ship_by_dt", "arranged_dt"])
    if not valid.empty:
        on_time = (valid["arranged_dt"] <= valid["ship_by_dt"]).sum()
        col3.metric("Ketepatan Waktu Kirim", f"{on_time}/{len(valid)} ({on_time/len(valid)*100:.0f}%)")

    st.divider()
    st.markdown("**Kurir yang Dipakai**")
    courier_counts = headers["courier"].value_counts().reset_index()
    courier_counts.columns = ["Kurir", "Jumlah Order"]
    c1, c2 = st.columns([1, 2])
    c1.dataframe(courier_counts, use_container_width=True, hide_index=True)
    c2.bar_chart(courier_counts.set_index("Kurir"))

    st.divider()
    st.markdown("**Fulfillment Time** (dari order dibuat sampai selesai)")
    headers["order_dt"] = pd.to_datetime(headers["order_date"], errors="coerce")
    headers["completed_dt"] = pd.to_datetime(headers["completed_time"], errors="coerce")
    fulfillment = headers.dropna(subset=["order_dt", "completed_dt"]).copy()
    if not fulfillment.empty:
        fulfillment["fulfillment_days"] = (fulfillment["completed_dt"] - fulfillment["order_dt"]).dt.total_seconds() / 86400
        st.metric("Rata-rata Waktu Fulfillment", f"{fulfillment['fulfillment_days'].mean():.1f} hari")
        st.dataframe(
            fulfillment[["no_pesanan", "courier", "order_date", "completed_time", "fulfillment_days"]]
            .sort_values("fulfillment_days", ascending=False).head(10),
            use_container_width=True, hide_index=True,
        )
        st.caption("10 order dengan waktu fulfillment paling lama - kandidat untuk investigasi delay.")
