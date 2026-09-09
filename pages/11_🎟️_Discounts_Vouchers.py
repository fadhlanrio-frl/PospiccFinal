import streamlit as st

import database as db

st.set_page_config(page_title="Discounts & Vouchers - Pospicc", page_icon="🎟️", layout="wide")
st.title("🎟️ Discounts & Vouchers")
st.caption("Berapa banyak revenue yang 'bocor' ke diskon/voucher, dan siapa yang menanggungnya (penjual vs Shopee).")

headers = db.fetch_df(
    """
    SELECT no_pesanan, total_payment, total_discount, voucher_seller, voucher_shopee,
           cashback_koin, creditcard_discount
    FROM order_headers
    """
)

if headers.empty:
    st.info("Belum ada data order. Hubungkan Shopee API lewat halaman Import Data, atau tunggu sync otomatis berikutnya.")
else:
    total_voucher_seller = headers["voucher_seller"].sum()
    total_voucher_shopee = headers["voucher_shopee"].sum()
    total_cashback = headers["cashback_koin"].sum()
    total_cc_discount = headers["creditcard_discount"].sum()
    total_all_discount = total_voucher_seller + total_voucher_shopee + total_cashback + total_cc_discount

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Diskon (semua sumber)", f"Rp{total_all_discount:,.0f}")
    col2.metric("Ditanggung Penjual (Pospicc)", f"Rp{total_voucher_seller:,.0f}")
    col3.metric("Ditanggung Shopee", f"Rp{total_voucher_shopee:,.0f}")

    st.divider()
    breakdown = {
        "Sumber Diskon": ["Voucher Penjual", "Voucher Shopee", "Cashback Koin", "Diskon Kartu Kredit"],
        "Total (Rp)": [total_voucher_seller, total_voucher_shopee, total_cashback, total_cc_discount],
    }
    c1, c2 = st.columns([1, 2])
    c1.dataframe(breakdown, use_container_width=True, hide_index=True)
    import pandas as pd
    c2.bar_chart(pd.DataFrame(breakdown).set_index("Sumber Diskon"))

    if total_voucher_seller > 0 and headers["total_payment"].sum() > 0:
        pct_of_revenue = total_voucher_seller / headers["total_payment"].sum() * 100
        st.warning(
            f"💡 Voucher yang ditanggung Pospicc sendiri setara **{pct_of_revenue:.1f}%** dari total pembayaran "
            "pembeli di periode ini - ini biaya riil yang mengurangi margin, di luar biaya platform Shopee."
        )

    st.divider()
    st.markdown("**Order dengan Diskon Penjual Terbesar**")
    top_discount = headers[headers["voucher_seller"] > 0].sort_values("voucher_seller", ascending=False).head(10)
    if not top_discount.empty:
        st.dataframe(top_discount, use_container_width=True, hide_index=True)
    else:
        st.info("Tidak ada order dengan voucher dari penjual di periode ini.")
