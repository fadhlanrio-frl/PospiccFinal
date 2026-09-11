import streamlit as st

import database as db

db.init_db()

st.set_page_config(page_title="Alerts - Pospicc", page_icon="🔔", layout="wide")
st.title("🔔 Alerts History")
st.caption("Semua automation: low-stock, stockout, sales spike, stale data, low ROAS, dan SKU conflicts.")

severity_filter = st.multiselect("Filter severity", ["critical", "warning", "info"], default=["critical", "warning", "info"])
days = st.slider("Tampilkan alert dari berapa hari terakhir?", 1, 30, 7)

placeholders = ",".join("?" * len(severity_filter)) if severity_filter else "''"
query = f"""
    SELECT triggered_at, alert_type, sku, message, severity
    FROM alerts_log
    WHERE triggered_at >= datetime('now', ?) AND severity IN ({placeholders})
    ORDER BY triggered_at DESC
"""
params = (f"-{days} days", *severity_filter) if severity_filter else (f"-{days} days",)
alerts_df = db.fetch_df(query, params)

if alerts_df.empty:
    st.info("Tidak ada alert pada rentang waktu ini.")
else:
    severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    alerts_df.insert(0, "  ", alerts_df["severity"].map(severity_icon))
    st.dataframe(alerts_df, use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("**Ringkasan per Jenis Alert**")
    summary = alerts_df.groupby("alert_type").size().reset_index(name="count").sort_values("count", ascending=False)
    st.bar_chart(summary.set_index("alert_type"))
