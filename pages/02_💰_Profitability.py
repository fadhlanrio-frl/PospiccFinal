import streamlit as st

import database as db

db.init_db()

st.set_page_config(page_title="Profitability - Pospicc", page_icon="💰", layout="wide")
st.title("💰 Profitability")
st.caption("Estimasi profit menggunakan HPP dan harga jual per produk. Bandingkan skenario restock pakai kas internal vs pendanaan eksternal.")

data = db.fetch_df(
    """
    SELECT p.sku, p.product_name, p.hpp, p.selling_price,
           COALESCE(SUM(s.units_sold), 0) AS units_sold_7d,
           COALESCE(SUM(s.revenue), 0) AS revenue_7d
    FROM products p
    LEFT JOIN sales_orders s ON s.sku = p.sku AND s.order_date >= datetime(?, '-7 days')
    GROUP BY p.sku, p.product_name, p.hpp, p.selling_price
    """,
    (db.get_sales_reference_datetime(),),
)

if data.empty:
    st.info("Belum ada data produk. Isi lewat halaman Import Data atau Sync dari Home.")
else:
    data["gross_profit_per_unit"] = data["selling_price"] - data["hpp"]
    data["contribution_margin_pct"] = (data["gross_profit_per_unit"] / data["selling_price"] * 100).round(1)
    data["gross_profit_7d"] = data["gross_profit_per_unit"] * data["units_sold_7d"]

    col1, col2 = st.columns(2)
    col1.metric("Total Gross Profit (7d)", f"Rp{data['gross_profit_7d'].sum():,.0f}")
    col2.metric("Avg. Contribution Margin", f"{data['contribution_margin_pct'].mean():.1f}%")

    st.markdown("**Per-Product Profitability**")
    st.dataframe(
        data[["sku", "product_name", "hpp", "selling_price", "gross_profit_per_unit",
              "contribution_margin_pct", "units_sold_7d", "gross_profit_7d"]]
        .sort_values("gross_profit_7d", ascending=False),
        use_container_width=True, hide_index=True,
    )

    st.divider()
    st.subheader("🏦 Restock Funding Comparison")
    st.caption("Second-opinion estimate only - GM makes the final call. Adjust assumptions below.")

    selected_sku = st.selectbox("Pilih produk untuk simulasi restock", data["sku"])
    row = data[data["sku"] == selected_sku].iloc[0]

    col_a, col_b, col_c = st.columns(3)
    restock_qty = col_a.number_input("Jumlah restock (unit)", min_value=1, value=50)
    external_interest_rate_pct = col_b.number_input("Bunga pendanaan eksternal per periode restock (%)", min_value=0.0, value=2.0, step=0.5)
    expected_sell_through_pct = col_c.slider("Estimasi sell-through (%)", 10, 100, 80)

    restock_cost = restock_qty * row["hpp"]
    expected_units_sold = restock_qty * expected_sell_through_pct / 100
    expected_revenue = expected_units_sold * row["selling_price"]
    expected_gross_profit = expected_revenue - restock_cost
    external_cost_of_capital = restock_cost * external_interest_rate_pct / 100
    profit_internal_funding = expected_gross_profit
    profit_external_funding = expected_gross_profit - external_cost_of_capital

    st.markdown(f"**Restock cost:** Rp{restock_cost:,.0f} for {restock_qty} units of `{selected_sku}`")
    col_x, col_y = st.columns(2)
    col_x.metric("Est. Profit - Internal Cash", f"Rp{profit_internal_funding:,.0f}")
    col_y.metric("Est. Profit - External Funding", f"Rp{profit_external_funding:,.0f}", delta=f"-Rp{external_cost_of_capital:,.0f} cost of capital")
    st.caption("Asumsi: sell-through rate dan bunga di atas adalah input manual GM, bukan hasil forecast otomatis.")
