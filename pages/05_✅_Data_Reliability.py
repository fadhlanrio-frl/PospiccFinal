import streamlit as st

import database as db

st.set_page_config(page_title="Data Reliability - Pospicc", page_icon="✅", layout="wide")
st.title("✅ Data Reliability")
st.caption("Setiap modul menunjukkan kapan terakhir diperbarui, siapa/apa sumbernya, dan status current/stale/incomplete.")

sources = db.fetch_df("SELECT * FROM data_sources ORDER BY module")

if sources.empty:
    st.info("Belum ada sinkronisasi/import data sama sekali.")
else:
    status_icon = {"current": "🟢", "stale": "🟡", "incomplete": "🔴"}
    for _, row in sources.iterrows():
        icon = status_icon.get(row["status"], "⚪")
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        col1.markdown(f"{icon} **{row['module']}**")
        col2.write(f"Updated by: {row['updated_by']}")
        col3.write(f"Source: {row['source']}")
        col4.write(f"Last updated: {row['last_updated']}")

    st.divider()
    st.subheader("Governance - Siapa Pemilik Data Apa")
    governance = {
        "Function": ["Inventory and stock updates", "Financial and payment data", "Marketing and advertising data",
                     "Commercial decisions", "Strategic review and consultation", "Product development status"],
        "Suggested Owner": ["Operations", "Finance", "Marketing", "Sales / Commercial Lead", "GM", "Product Development"],
    }
    st.dataframe(governance, use_container_width=True, hide_index=True)
