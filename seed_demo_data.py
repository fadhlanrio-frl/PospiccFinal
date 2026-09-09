"""
seed_demo_data.py
Optional: seeds a few example product theses so Product Intelligence isn't
empty. With DATA_SOURCE_MODE=excel (the default), your main data (products/
sales/inventory/marketing) comes from the Import Data page instead - run
this only if you want a couple of demo notes on top of that.
"""
import database as db

db.init_db()

theses = {
    "PSP-JKT-001": "Warna pink dianggap under-served di kategori jaket kulit lokal; target female buyer 20-28th.",
    "PSP-JKT-002": "Bomber jacket lebih casual/daily-wear dibanding jaket formal, harusnya sell-through lebih cepat.",
    "PSP-BAG-001": "Kombinasi knit+leather+denim jadi diferensiasi vs backpack polos kompetitor.",
}
with db.get_conn() as conn:
    for sku, thesis in theses.items():
        conn.execute("UPDATE products SET product_thesis = ? WHERE sku = ?", (thesis, sku))

print("Demo product theses applied (only affects SKUs that already exist in the DB).")
print("Import your real data first via the 'Import Data' page, then run this if you want.")
