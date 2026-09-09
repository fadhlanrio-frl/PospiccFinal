import streamlit as st

import database as db

st.set_page_config(page_title="Product Intelligence - Pospicc", page_icon="🧠", layout="wide")
st.title("🧠 Product Intelligence")
st.caption("Product thesis, market sentiment, internal observations, customer feedback, and vendor concerns.")

products = db.fetch_df("SELECT sku, product_name, product_thesis, vendor FROM products")

with st.expander("➕ Tambah catatan produk"):
    if products.empty:
        st.info("Isi produk lewat Import Data dulu.")
    else:
        with st.form("intel_entry"):
            sku = st.selectbox("Produk", products["sku"])
            market_sentiment = st.text_area("Market sentiment (dari social media, review, dll)")
            internal_observation = st.text_area("Observasi internal tim")
            customer_likes = st.text_area("Alasan customer suka")
            customer_dislikes = st.text_area("Alasan customer menolak/komplain")
            vendor_concerns = st.text_area("Concern terkait vendor/produksi")
            entered_by = st.text_input("Diinput oleh")
            submitted = st.form_submit_button("Simpan catatan")
            if submitted:
                db.add_product_intelligence({
                    "sku": sku, "market_sentiment": market_sentiment,
                    "internal_observation": internal_observation, "customer_likes": customer_likes,
                    "customer_dislikes": customer_dislikes, "vendor_concerns": vendor_concerns,
                    "entered_by": entered_by,
                })
                db.mark_data_source("Product Intelligence", entered_by, "Manual entry", "current")
                st.success("Catatan tersimpan.")
                st.rerun()

st.divider()

with st.expander("✏️ Set / update product thesis"):
    if not products.empty:
        sku_for_thesis = st.selectbox("Produk", products["sku"], key="thesis_sku")
        current_thesis = products.loc[products["sku"] == sku_for_thesis, "product_thesis"].values
        thesis_text = st.text_area("Product thesis", value=current_thesis[0] if len(current_thesis) and current_thesis[0] else "")
        if st.button("Simpan thesis"):
            with db.get_conn() as conn:
                conn.execute("UPDATE products SET product_thesis = ? WHERE sku = ?", (thesis_text, sku_for_thesis))
            st.success("Thesis diperbarui.")
            st.rerun()

st.divider()
st.subheader("📋 Riwayat Catatan per Produk")

notes = db.fetch_df(
    """
    SELECT pi.entry_date, p.sku, p.product_name, pi.market_sentiment, pi.internal_observation,
           pi.customer_likes, pi.customer_dislikes, pi.vendor_concerns, pi.entered_by
    FROM product_intelligence pi
    JOIN products p ON p.sku = pi.sku
    ORDER BY pi.entry_date DESC
    """
)

if notes.empty:
    st.info("Belum ada catatan product intelligence.")
else:
    for sku in notes["sku"].unique():
        product_notes = notes[notes["sku"] == sku]
        product_name = product_notes["product_name"].iloc[0]
        thesis_row = products.loc[products["sku"] == sku, "product_thesis"]
        thesis = thesis_row.values[0] if len(thesis_row) and thesis_row.values[0] else "(belum diisi)"
        with st.expander(f"{sku} - {product_name}"):
            st.markdown(f"**Product thesis:** {thesis}")
            st.dataframe(
                product_notes[["entry_date", "market_sentiment", "internal_observation",
                                "customer_likes", "customer_dislikes", "vendor_concerns", "entered_by"]],
                use_container_width=True, hide_index=True,
            )
