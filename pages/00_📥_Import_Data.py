import streamlit as st

import config
import database as db
import excel_importer
import shopee_api_client

st.set_page_config(page_title="Import Data - Pospicc", page_icon="📥", layout="wide")
st.title("📥 Import Data")
st.caption(
    "Sales/produk/order Shopee ditarik otomatis lewat Shopee Open API (tab pertama). "
    "Template manual di tab kedua tetap dipakai untuk Inventory dan Marketing, yang tidak "
    "disediakan Shopee lewat API sekalipun."
)

tab_shopee, tab_manual = st.tabs(["🛒 Shopee API (Semi Real-time)", "📝 Template Manual"])

# ============================================================================
# TAB 1: Shopee Open Platform API - OAuth connect + manual sync
# ============================================================================
with tab_shopee:
    # Shopee redirects the browser back here with ?code=...&shop_id=... right
    # after the seller approves access - catch that once, exchange it for
    # tokens, then clear the URL so a page refresh doesn't re-submit it.
    params = st.query_params
    if "code" in params and "shop_id" in params:
        try:
            shopee_api_client.complete_authorization(params["code"], params["shop_id"])
        except shopee_api_client.ShopeeAPIError as e:
            st.error(f"Gagal menghubungkan toko Shopee: {e}")
        else:
            st.success("Toko Shopee berhasil terhubung!")
        st.query_params.clear()

    if not config.SHOPEE_API_CONFIGURED:
        st.warning(
            "`SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, dan `SHOPEE_REDIRECT_URL` belum diisi di `.env`. "
            "Lihat README untuk cara mendapatkannya dari https://open.shopee.com/ (Partner Portal -> "
            "App Management), lalu isi `.env` dan restart aplikasi."
        )
    else:
        tokens = db.get_shopee_tokens()
        if tokens:
            st.success(f"✅ Terhubung ke toko Shopee (shop_id: `{tokens['shop_id']}`)")
            c1, c2 = st.columns(2)
            c1.metric("Access token berlaku sampai", tokens["access_token_expires_at"][:16].replace("T", " "))
            c2.metric("Sync otomatis setiap", f"{config.SHOPEE_SYNC_INTERVAL_MINUTES} menit")
            st.caption(
                "Access token di-refresh otomatis di background (berlaku 4 jam, refresh_token 30 hari). "
                "Kalau refresh_token sudah expired (toko tidak pernah sync >30 hari), hubungkan ulang di bawah."
            )

            if st.button("🔄 Sync Shopee sekarang", type="primary", key="shopee_sync_now"):
                import shopee_scheduler
                with st.spinner("Menarik order, produk, dan stok terbaru dari Shopee..."):
                    try:
                        shopee_scheduler.sync_once()
                    except shopee_api_client.ShopeeAPIError as e:
                        st.error(f"Sync gagal: {e}")
                    else:
                        st.success("Sync selesai. Buka halaman **Home** untuk lihat data terbaru.")

            with st.expander("Hubungkan ulang / ganti toko"):
                st.link_button("🔗 Connect Shopee (ulang)", shopee_api_client.get_auth_url(), use_container_width=True)
        else:
            st.info(
                "Toko Shopee belum terhubung. Klik tombol di bawah, login sebagai penjual toko **Pospicc** "
                "di Shopee, lalu setujui akses. Kamu akan diarahkan balik ke halaman ini secara otomatis."
            )
            st.link_button("🔗 Connect Shopee", shopee_api_client.get_auth_url(), type="primary", use_container_width=True)
            st.caption(
                f"Redirect URL terdaftar: `{config.SHOPEE_REDIRECT_URL}` - harus PERSIS sama dengan yang "
                "didaftarkan di App Management pada https://open.shopee.com/, kalau tidak Shopee akan menolak."
            )

# ============================================================================
# TAB 2: Generic manual template (Inventory & Marketing - not in Shopee's API)
# ============================================================================
with tab_manual:
    st.caption(
        "Shopee Open API tidak menyediakan **Inventory** (stock on hand) dan **Marketing** (ads spend/ROAS) "
        "dengan mudah, jadi dua modul ini tetap diisi manual lewat sini. Juga berguna kalau kamu jual "
        "lewat channel lain di luar Shopee."
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        try:
            with open("templates/Pospicc_Data_Template.xlsx", "rb") as f:
                st.download_button(
                    "⬇️ Download Template Excel",
                    data=f.read(),
                    file_name="Pospicc_Data_Template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        except FileNotFoundError:
            st.error("Template belum ada. Jalankan `python build_excel_template.py` dulu.")

    st.markdown(
        """
        **Cara isi template:**
        - **Products** — biasanya sudah terisi otomatis dari sync Shopee API, isi ini hanya untuk produk di luar Shopee.
        - **Sales** — opsional, biasanya sudah masuk otomatis lewat sync Shopee API.
        - **Inventory** — satu baris per SKU, snapshot stock terbaru. **Wajib diisi manual**.
        - **Marketing** — satu baris per produk per tanggal. **Wajib diisi manual**.
        - Baris kuning di tiap sheet adalah **contoh** — hapus atau timpa dengan data asli.
        """
    )

    st.divider()
    uploaded_file = st.file_uploader("Upload file Excel (.xlsx) - format template manual", type=["xlsx"], key="manual_upload")

    if uploaded_file is not None:
        try:
            summary = excel_importer.preview_workbook(uploaded_file)
            has_error = any(s["error"] for s in summary.values())
            cols = st.columns(4)
            for i, (sheet_name, info) in enumerate(summary.items()):
                with cols[i]:
                    if info["error"]:
                        st.error(f"**{sheet_name}**\n\n{info['error']}")
                    else:
                        st.metric(sheet_name, f"{info['rows']} baris")

            if has_error:
                st.warning("Perbaiki error di atas dulu sebelum import, lalu upload ulang file-nya.")
            else:
                entered_by = st.text_input("Diimport oleh (nama kamu)", value="", key="manual_by")
                if st.button("✅ Import ke Dashboard", type="primary", disabled=not entered_by, key="manual_btn"):
                    db.init_db()
                    uploaded_file.seek(0)
                    with st.spinner("Mengimport data..."):
                        try:
                            result = excel_importer.import_workbook(uploaded_file, imported_by=entered_by or "Manual Excel Upload")
                        except excel_importer.ExcelImportError as e:
                            st.error(f"Import gagal: {e}")
                        else:
                            st.success("Import berhasil!")
                            st.json(result)
                            if any(k.endswith("_skipped_unknown_sku") for k in result):
                                st.warning("Beberapa baris di-skip karena SKU-nya tidak ditemukan di sheet Products.")
                            st.info("Buka halaman **Home** untuk lihat data yang baru masuk.")
        except Exception as e:  # noqa: BLE001
            st.error(f"File tidak bisa dibaca: {e}. Pastikan formatnya sesuai template.")

st.divider()
st.caption(
    "Catatan: Plugo API masih standby menunggu approval key dari admin Plugo - lihat halaman "
    "**Data Reliability** untuk status semua sumber data. Kalau SKU yang sama muncul dari beberapa "
    "sumber, data produk mengikuti sumber yang paling terakhir sync/import."
)
