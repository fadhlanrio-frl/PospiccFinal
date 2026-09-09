import streamlit as st

import database as db

st.set_page_config(page_title="Customer Geography - Pospicc", page_icon="🌍", layout="wide")
st.title("🌍 Customer Geography")
st.caption("Dari mana pembeli Pospicc berasal - berguna untuk keputusan ekspansi gudang, target iklan lokal, atau event offline.")

geo = db.fetch_df(
    """
    SELECT oh.province, oh.city, oh.no_pesanan, oh.total_payment
    FROM order_headers oh
    """
)

if geo.empty:
    st.info("Belum ada data order. Hubungkan Shopee API lewat halaman Import Data, atau tunggu sync otomatis berikutnya.")
else:
    col1, col2 = st.columns(2)
    col1.metric("Provinsi Terjangkau", geo["province"].nunique())
    col2.metric("Kota/Kabupaten Terjangkau", geo["city"].nunique())

    st.divider()
    st.markdown("**Sebaran Order per Provinsi**")
    prov = geo.groupby("province").agg(jumlah_order=("no_pesanan", "count"), total_payment=("total_payment", "sum")).reset_index()
    prov = prov.sort_values("jumlah_order", ascending=False)
    c1, c2 = st.columns([2, 1])
    c1.bar_chart(prov.set_index("province")["jumlah_order"])
    c2.dataframe(prov, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Top 10 Kota/Kabupaten**")
    city = geo.groupby(["city", "province"]).size().reset_index(name="jumlah_order").sort_values("jumlah_order", ascending=False).head(10)
    st.dataframe(city, use_container_width=True, hide_index=True)

    top_province = prov.iloc[0]["province"] if not prov.empty else None
    if top_province:
        st.info(f"💡 Provinsi dengan order terbanyak: **{top_province}** - pertimbangkan untuk fokus target iklan lokal atau cek waktu kirim ke area ini di halaman Shipping & Logistics.")
