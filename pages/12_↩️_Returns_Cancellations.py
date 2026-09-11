import streamlit as st

import database as db

db.init_db()

st.set_page_config(page_title="Returns & Cancellations - Pospicc", page_icon="↩️", layout="wide")
st.title("↩️ Returns & Cancellations")
st.caption("Produk mana yang paling sering dikembalikan/dibatalkan - sinyal penting untuk kualitas produk atau ekspektasi vs realita.")

returns = db.fetch_df(
    """
    SELECT p.sku, p.product_name, so.variant_name, SUM(so.returned_quantity) AS total_returned,
           SUM(so.units_sold) AS total_sold
    FROM sales_orders so
    JOIN products p ON p.sku = so.sku
    GROUP BY p.sku, p.product_name, so.variant_name
    HAVING total_returned > 0
    ORDER BY total_returned DESC
    """
)

cancellations = db.fetch_df(
    """
    SELECT no_pesanan, cancellation_status, order_date, total_payment
    FROM order_headers
    WHERE cancellation_status IS NOT NULL
    """
)

col1, col2 = st.columns(2)
col1.metric("Baris Produk dengan Retur", len(returns))
col2.metric("Order dengan Status Pembatalan/Pengembalian", len(cancellations))

st.divider()
st.markdown("**Produk dengan Retur Terbanyak**")
if returns.empty:
    st.success("Tidak ada retur tercatat di data yang sudah diimport. 🎉")
else:
    returns["return_rate_pct"] = (returns["total_returned"] / returns["total_sold"] * 100).round(1)
    st.dataframe(returns, use_container_width=True, hide_index=True)
    worst = returns.iloc[0]
    st.warning(
        f"💡 **{worst['product_name']}** ({worst['variant_name']}) punya return rate tertinggi: "
        f"{worst['return_rate_pct']:.1f}% - pertimbangkan cek size chart, deskripsi produk, atau kualitas."
    )

st.divider()
st.markdown("**Riwayat Pembatalan/Pengembalian**")
if cancellations.empty:
    st.info("Tidak ada order dengan status pembatalan/pengembalian di data yang sudah diimport.")
else:
    st.dataframe(cancellations, use_container_width=True, hide_index=True)
