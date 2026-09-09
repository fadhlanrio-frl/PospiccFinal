"""ai_assistant.py - AI Q&A grounded in dashboard data via OpenAI API."""
from openai import OpenAI

import config
import database as db

SYSTEM_PROMPT = """You are the Pospicc Product Intelligence Assistant, an internal decision-support \
tool for the GM of an Indonesian leather-fashion brand.

You have access to real Shopee order/settlement data: sales, inventory, profitability, marketing/ROAS, \
qualitative product intelligence (including buyer notes captured automatically from orders), data \
freshness status, actual Shopee fee breakdown (admin/processing/AMS ads/campaign/tax fees from the \
Income Report), shipping/courier data, buyer geography (province/city), payment method mix, repeat \
buyer patterns, product returns, and discount/voucher costs (seller-borne vs Shopee-borne).

STRICT RULES:
1. You give a SECOND OPINION only. You never claim to change stock, place orders, \
activate ads, modify budgets, or execute payments - you only recommend.
2. Every claim you make must be traceable to the DATA CONTEXT provided below. \
If the data needed to answer is missing or stale, say so explicitly instead of guessing.
3. Always mention data freshness/status when relevant to how much the GM should trust the answer.
4. Answer in the same language the GM asks in (Indonesian or English).
5. Be concise and decision-oriented: lead with the recommendation, then the evidence.
"""


def _build_data_context() -> str:
    parts = []
    products = db.fetch_df("SELECT * FROM products")
    parts.append("=== PRODUCTS ===\n" + (products.to_string(index=False) if not products.empty else "(no data yet)"))

    sales_ref = db.get_sales_reference_datetime()
    sales_7d = db.fetch_df(
        """
        SELECT sku, SUM(units_sold) AS units_7d, SUM(revenue) AS revenue_7d
        FROM sales_orders WHERE order_date >= datetime(?, '-7 days') GROUP BY sku
        """,
        (sales_ref,),
    )
    parts.append(f"=== SALES (7 days up to {sales_ref[:10]}) ===\n" + (sales_7d.to_string(index=False) if not sales_7d.empty else "(no sales in that window)"))

    inventory = db.fetch_df(
        """
        SELECT sku, stock_on_hand, reserved_stock, snapshot_at
        FROM inventory_snapshots WHERE id IN (SELECT MAX(id) FROM inventory_snapshots GROUP BY sku)
        """
    )
    parts.append("=== CURRENT INVENTORY ===\n" + (inventory.to_string(index=False) if not inventory.empty else "(no inventory data yet)"))

    marketing_ref = db.get_marketing_reference_date()
    marketing_7d = db.fetch_df(
        """
        SELECT sku, SUM(ads_spend) AS spend_7d, SUM(attributed_revenue) AS attributed_revenue_7d
        FROM marketing_metrics WHERE metric_date >= date(?, '-7 days') GROUP BY sku
        """,
        (marketing_ref,),
    )
    parts.append(f"=== MARKETING (7 days up to {marketing_ref}) ===\n" + (marketing_7d.to_string(index=False) if not marketing_7d.empty else "(no marketing data in that window)"))

    intel = db.fetch_df(
        """
        SELECT sku, market_sentiment, internal_observation, customer_likes,
               customer_dislikes, vendor_concerns, entry_date
        FROM product_intelligence ORDER BY entry_date DESC LIMIT 20
        """
    )
    parts.append("=== PRODUCT INTELLIGENCE (recent notes) ===\n" + (intel.to_string(index=False) if not intel.empty else "(no notes yet)"))

    freshness = db.fetch_df("SELECT * FROM data_sources")
    parts.append("=== DATA FRESHNESS / RELIABILITY ===\n" + (freshness.to_string(index=False) if not freshness.empty else "(no sync/import has run yet)"))

    income_summary = db.fetch_df(
        "SELECT period_start, period_end, marketplace, total_pendapatan, total_pengeluaran, total_dilepas "
        "FROM marketplace_income_summary ORDER BY period_start DESC LIMIT 6"
    )
    parts.append(
        "=== MARKETPLACE INCOME SETTLEMENT (actual payout after fees, from Shopee Income Report) ===\n"
        + (income_summary.to_string(index=False) if not income_summary.empty
           else "(no income report imported yet - only gross order revenue is available)")
    )

    fee_breakdown = db.fetch_df(
        """
        SELECT ROUND(SUM(ABS(biaya_administrasi)),0) AS biaya_administrasi,
               ROUND(SUM(ABS(biaya_proses_pesanan)),0) AS biaya_proses_pesanan,
               ROUND(SUM(ABS(biaya_transaksi)),0) AS biaya_transaksi,
               ROUND(SUM(ABS(biaya_komisi_ams)),0) AS biaya_komisi_ams_ads,
               ROUND(SUM(ABS(biaya_kampanye)),0) AS biaya_kampanye,
               ROUND(SUM(ABS(pph22)),0) AS pph22_pajak,
               ROUND(SUM(ABS(other_fees)),0) AS other_fees,
               ROUND(SUM(total_income),0) AS total_net_income
        FROM order_settlements
        """
    )
    parts.append(
        "=== ACTUAL SHOPEE FEE BREAKDOWN (from Income Report, real numbers not estimates) ===\n"
        + (fee_breakdown.to_string(index=False) if not fee_breakdown.empty and fee_breakdown.iloc[0].notna().any()
           else "(no order-level settlement data imported yet)")
    )

    geo = db.fetch_df(
        """
        SELECT province, COUNT(*) AS orders, SUM(total_payment) AS total_payment
        FROM order_headers GROUP BY province ORDER BY orders DESC LIMIT 8
        """
    )
    parts.append("=== TOP PROVINCES BY ORDER COUNT ===\n" + (geo.to_string(index=False) if not geo.empty else "(no order header data yet)"))

    payment_methods = db.fetch_df(
        "SELECT payment_method, COUNT(*) AS orders FROM order_headers GROUP BY payment_method ORDER BY orders DESC"
    )
    parts.append("=== PAYMENT METHOD BREAKDOWN ===\n" + (payment_methods.to_string(index=False) if not payment_methods.empty else "(no order header data yet)"))

    courier_stats = db.fetch_df(
        "SELECT courier, COUNT(*) AS orders FROM order_headers GROUP BY courier ORDER BY orders DESC"
    )
    parts.append("=== COURIER USAGE ===\n" + (courier_stats.to_string(index=False) if not courier_stats.empty else "(no order header data yet)"))

    repeat_buyers = db.fetch_df(
        """
        SELECT buyer_username, COUNT(*) AS orders, SUM(total_payment) AS total_spent
        FROM order_headers GROUP BY buyer_username HAVING orders > 1 ORDER BY orders DESC LIMIT 10
        """
    )
    parts.append(
        "=== REPEAT BUYERS ===\n"
        + (repeat_buyers.to_string(index=False) if not repeat_buyers.empty else "(no repeat buyers found in imported data)")
    )

    returns = db.fetch_df(
        """
        SELECT p.sku, p.product_name, SUM(so.returned_quantity) AS returned, SUM(so.units_sold) AS sold
        FROM sales_orders so JOIN products p ON p.sku = so.sku
        GROUP BY p.sku, p.product_name HAVING returned > 0 ORDER BY returned DESC
        """
    )
    parts.append("=== PRODUCT RETURNS ===\n" + (returns.to_string(index=False) if not returns.empty else "(no returns recorded)"))

    discounts = db.fetch_df(
        """
        SELECT ROUND(SUM(voucher_seller),0) AS voucher_by_seller, ROUND(SUM(voucher_shopee),0) AS voucher_by_shopee,
               ROUND(SUM(cashback_koin),0) AS cashback_koin, ROUND(SUM(creditcard_discount),0) AS creditcard_discount
        FROM order_headers
        """
    )
    parts.append(
        "=== DISCOUNTS & VOUCHERS (who bears the cost) ===\n"
        + (discounts.to_string(index=False) if not discounts.empty and discounts.iloc[0].notna().any() else "(no order header data yet)")
    )

    recent_alerts = db.fetch_df(
        "SELECT triggered_at, alert_type, sku, message, severity FROM alerts_log ORDER BY triggered_at DESC LIMIT 15"
    )
    parts.append("=== RECENT ALERTS ===\n" + (recent_alerts.to_string(index=False) if not recent_alerts.empty else "(no alerts yet)"))

    return "\n\n".join(parts)


def ask(question: str) -> str:
    if not config.OPENAI_API_KEY:
        return (
            "OPENAI_API_KEY belum diset di file .env. "
            "Tambahkan API key dari platform.openai.com untuk mengaktifkan fitur ini."
        )

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    data_context = _build_data_context()

    completion = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"DATA CONTEXT (pulled from the dashboard database just now):\n\n{data_context}\n\n---\n\nGM's question: {question}",
            },
        ],
    )
    return completion.choices[0].message.content
