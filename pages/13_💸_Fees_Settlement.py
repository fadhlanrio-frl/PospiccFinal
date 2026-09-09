import streamlit as st

import database as db

st.set_page_config(page_title="Fees & Settlement - Pospicc", page_icon="💸", layout="wide")
st.title("💸 Fees & Settlement")
st.caption("Breakdown biaya Shopee yang SEBENARNYA (dari Income Report), bukan estimasi - untuk profitabilitas yang akurat.")

settlements = db.fetch_df("SELECT * FROM order_settlements")
summary = db.fetch_df("SELECT * FROM marketplace_income_summary ORDER BY period_start DESC")

if settlements.empty:
    st.info(
        "Belum ada data settlement. Catatan: fitur upload Excel 'Shopee Income Report' sudah "
        "dihapus (digantikan sync Shopee API), dan Shopee Open API tidak punya endpoint payout/fee "
        "resmi yang sesederhana Income Report - jadi modul ini butuh sumber data baru. Kalau kamu "
        "masih perlu breakdown biaya ini, minta dibangun sync lewat endpoint escrow Shopee "
        "(get_escrow_detail per order) sebagai langkah lanjutan."
    )
else:
    fee_cols = ["biaya_administrasi", "biaya_proses_pesanan", "biaya_transaksi",
                "biaya_komisi_ams", "biaya_kampanye", "pph22", "other_fees"]
    total_fees_by_type = settlements[fee_cols].abs().sum()
    total_net = settlements["total_income"].sum()
    total_fees = total_fees_by_type.sum()
    gross_estimate = total_net + total_fees

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Net Income (cair)", f"Rp{total_net:,.0f}")
    col2.metric("Total Biaya Shopee", f"Rp{total_fees:,.0f}")
    col3.metric("Efektif Fee Rate", f"{total_fees/gross_estimate*100:.1f}%" if gross_estimate else "N/A")

    st.divider()
    st.markdown("**Breakdown Biaya per Kategori**")
    fee_labels = {
        "biaya_administrasi": "Biaya Administrasi",
        "biaya_proses_pesanan": "Biaya Proses Pesanan",
        "biaya_transaksi": "Biaya Transaksi",
        "biaya_komisi_ams": "Biaya Komisi AMS (Ads)",
        "biaya_kampanye": "Biaya Kampanye",
        "pph22": "PPh 22 (Pajak)",
        "other_fees": "Biaya Lainnya",
    }
    fee_df = total_fees_by_type.reset_index()
    fee_df.columns = ["Kategori", "Total (Rp)"]
    fee_df["Kategori"] = fee_df["Kategori"].map(fee_labels)
    fee_df = fee_df.sort_values("Total (Rp)", ascending=False)

    c1, c2 = st.columns([1, 2])
    c1.dataframe(fee_df, use_container_width=True, hide_index=True)
    c2.bar_chart(fee_df.set_index("Kategori"))

    biggest_fee = fee_df.iloc[0]
    st.warning(
        f"💡 Biaya terbesar: **{biggest_fee['Kategori']}** (Rp{biggest_fee['Total (Rp)']:,.0f}). "
        + ("Ini biaya iklan (AMS) - cek halaman Marketing untuk lihat ROAS-nya." if "AMS" in biggest_fee["Kategori"] else "")
    )

    st.divider()
    st.markdown("**Detail per Order**")
    st.dataframe(
        settlements[["no_pesanan", "order_date", "release_date", "total_income"] + fee_cols]
        .sort_values("order_date", ascending=False),
        use_container_width=True, hide_index=True,
    )

st.divider()
st.markdown("**Ringkasan per Periode (dari sheet Summary)**")
if summary.empty:
    st.info("Belum ada Income Report yang diimport.")
else:
    st.dataframe(summary, use_container_width=True, hide_index=True)
