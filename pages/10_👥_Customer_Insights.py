import streamlit as st

import database as db

db.init_db()

st.set_page_config(page_title="Customer Insights - Pospicc", page_icon="👥", layout="wide")
st.title("👥 Customer Insights")
st.caption("Repeat buyer, metode pembayaran favorit, dan suara pembeli langsung dari catatan order.")

headers = db.fetch_df("SELECT no_pesanan, buyer_username, payment_method, total_payment, order_date FROM order_headers")

if headers.empty:
    st.info("Belum ada data order. Hubungkan Shopee API lewat halaman Import Data, atau tunggu sync otomatis berikutnya.")
else:
    buyer_stats = headers.groupby("buyer_username").agg(
        jumlah_order=("no_pesanan", "count"), total_belanja=("total_payment", "sum")
    ).reset_index().sort_values("jumlah_order", ascending=False)

    repeat_buyers = buyer_stats[buyer_stats["jumlah_order"] > 1]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pembeli Unik", len(buyer_stats))
    col2.metric("Repeat Buyer", len(repeat_buyers))
    col3.metric("Repeat Rate", f"{len(repeat_buyers)/len(buyer_stats)*100:.1f}%" if len(buyer_stats) else "N/A")

    st.divider()
    st.markdown("**Top Pembeli (berdasarkan jumlah order)**")
    st.dataframe(buyer_stats.head(10), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Metode Pembayaran Favorit**")
    payment_counts = headers["payment_method"].value_counts().reset_index()
    payment_counts.columns = ["Metode Pembayaran", "Jumlah Order"]
    c1, c2 = st.columns([1, 2])
    c1.dataframe(payment_counts, use_container_width=True, hide_index=True)
    c2.bar_chart(payment_counts.set_index("Metode Pembayaran"))

    st.divider()
    st.markdown("**Suara Pembeli** (dari catatan order, otomatis masuk juga ke Product Intelligence)")
    notes = db.fetch_df(
        """
        SELECT pi.entry_date, p.sku, p.product_name, pi.customer_likes
        FROM product_intelligence pi JOIN products p ON p.sku = pi.sku
        WHERE pi.entered_by IN ('Shopee Order Export (auto)', 'Shopee API (auto)')
        ORDER BY pi.entry_date DESC
        """
    )
    if notes.empty:
        st.info("Belum ada catatan pembeli yang tertangkap dari order manapun.")
    else:
        st.dataframe(notes, use_container_width=True, hide_index=True)
