"""
excel_importer.py
Interim data source while Plugo/Shopee API access is still being sorted out.

Reads a structured Excel workbook (see excel_template_builder.py for the exact
template) with 4 sheets - Products, Sales, Inventory, Marketing - validates
the columns, and loads them into the SAME SQLite tables that plugo_client.py
writes to. Because every dashboard page reads from the database (never
directly from Plugo or Excel), nothing else needs to change: once real API
access is sorted, just flip DATA_SOURCE_MODE back to "plugo" in .env.
"""
from datetime import datetime

import pandas as pd

import database as db

REQUIRED_COLUMNS = {
    "Products": ["SKU", "Product Name", "Category", "HPP", "Selling Price", "Vendor"],
    "Sales": ["Order ID", "SKU", "Order Date", "Units Sold", "Revenue", "Channel"],
    "Inventory": ["SKU", "Stock on Hand", "Reserved Stock"],
    "Marketing": ["SKU", "Date", "Ads Spend", "Attributed Revenue", "Is Paid"],
}


class ExcelImportError(Exception):
    pass


def _read_sheet(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    if sheet_name not in xls.sheet_names:
        raise ExcelImportError(
            f"Sheet '{sheet_name}' tidak ditemukan di file Excel. "
            f"Sheet yang ada: {', '.join(xls.sheet_names)}. "
            f"Pastikan kamu pakai template yang benar."
        )
    # Row 1 of the template is a merged legend/instruction row, not data -
    # header=1 tells pandas the real column headers are on the 2nd row (0-indexed row 1).
    df = xls.parse(sheet_name, header=1)
    # Drop fully-empty rows (common when the user leaves gaps in the template)
    df = df.dropna(how="all")

    missing = [c for c in REQUIRED_COLUMNS[sheet_name] if c not in df.columns]
    if missing:
        raise ExcelImportError(
            f"Sheet '{sheet_name}' kehilangan kolom wajib: {', '.join(missing)}. "
            f"Jangan ubah nama header di baris ke-2 template (baris pertama adalah instruksi)."
        )
    return df


def _clean_date(value) -> str:
    """Handles both Excel date objects and plain strings, returns ISO format."""
    if pd.isna(value):
        return datetime.utcnow().isoformat()
    if isinstance(value, str):
        return value
    return pd.Timestamp(value).isoformat()


def preview_workbook(file) -> dict:
    """Returns row counts per sheet without writing to the DB - used for a
    'review before import' step in the UI."""
    xls = pd.ExcelFile(file)
    summary = {}
    for sheet_name in REQUIRED_COLUMNS:
        try:
            df = _read_sheet(xls, sheet_name)
            summary[sheet_name] = {"rows": len(df), "error": None}
        except ExcelImportError as e:
            summary[sheet_name] = {"rows": 0, "error": str(e)}
    return summary


def import_workbook(file, imported_by: str = "Manual Excel Upload") -> dict:
    """
    Reads all 4 sheets and loads them into the database.
    Returns a dict of {sheet_name: rows_imported} for a confirmation message.
    Raises ExcelImportError with a specific, actionable message on bad data -
    never fails silently, since bad data here quietly breaks every dashboard page.
    """
    xls = pd.ExcelFile(file)
    result = {}

    # --- Products (import first - Sales/Inventory/Marketing all reference SKU via FK) ---
    products_df = _read_sheet(xls, "Products")
    products = []
    for _, row in products_df.iterrows():
        if pd.isna(row["SKU"]) or pd.isna(row["Product Name"]):
            continue  # skip incomplete rows rather than crash the whole import
        products.append(
            {
                "sku": str(row["SKU"]).strip(),
                "product_name": str(row["Product Name"]).strip(),
                "category": str(row.get("Category", "") or "Uncategorized"),
                "hpp": float(row.get("HPP", 0) or 0),
                "selling_price": float(row.get("Selling Price", 0) or 0),
                "vendor": str(row.get("Vendor", "") or "Unknown"),
            }
        )
    if not products:
        raise ExcelImportError("Sheet 'Products' tidak punya baris data yang valid (SKU/Product Name kosong semua).")
    known_skus = {p["sku"] for p in products}
    db.upsert_products(products)
    db.mark_data_source("Sales", imported_by, "Manual Excel Upload", "current")
    db.mark_data_source("Profitability", imported_by, "Manual Excel Upload", "current")
    result["Products"] = len(products)

    # --- Sales ---
    sales_df = _read_sheet(xls, "Sales")
    orders = []
    skipped_unknown_sku = 0
    for _, row in sales_df.iterrows():
        if pd.isna(row["Order ID"]) or pd.isna(row["SKU"]):
            continue
        sku = str(row["SKU"]).strip()
        if sku not in known_skus:
            skipped_unknown_sku += 1
            continue  # SKU not in Products sheet - would violate the foreign key
        orders.append(
            {
                "order_id": str(row["Order ID"]).strip(),
                "sku": sku,
                "order_date": _clean_date(row["Order Date"]),
                "units_sold": int(row.get("Units Sold", 0) or 0),
                "revenue": float(row.get("Revenue", 0) or 0),
                "channel": str(row.get("Channel", "") or "website"),
            }
        )
    if orders:
        db.insert_sales_orders(orders)
        db.mark_data_source("Sales", imported_by, "Manual Excel Upload", "current")
    result["Sales"] = len(orders)
    if skipped_unknown_sku:
        result["Sales_skipped_unknown_sku"] = skipped_unknown_sku

    # --- Inventory ---
    inv_df = _read_sheet(xls, "Inventory")
    snapshots = []
    skipped_unknown_sku_inv = 0
    for _, row in inv_df.iterrows():
        if pd.isna(row["SKU"]):
            continue
        sku = str(row["SKU"]).strip()
        if sku not in known_skus:
            skipped_unknown_sku_inv += 1
            continue
        snapshots.append(
            {
                "sku": sku,
                "stock_on_hand": int(row.get("Stock on Hand", 0) or 0),
                "reserved_stock": int(row.get("Reserved Stock", 0) or 0),
            }
        )
    if snapshots:
        db.insert_inventory_snapshots(snapshots)
        db.mark_data_source("Inventory", imported_by, "Manual Excel Upload", "current")
    result["Inventory"] = len(snapshots)
    if skipped_unknown_sku_inv:
        result["Inventory_skipped_unknown_sku"] = skipped_unknown_sku_inv

    # --- Marketing ---
    mkt_df = _read_sheet(xls, "Marketing")
    marketing_rows = []
    for _, row in mkt_df.iterrows():
        if pd.isna(row["SKU"]):
            continue
        sku = str(row["SKU"]).strip()
        if sku not in known_skus:
            continue
        is_paid_raw = str(row.get("Is Paid", "Yes")).strip().lower()
        marketing_rows.append(
            {
                "sku": sku,
                "metric_date": _clean_date(row["Date"])[:10],  # date only, no time
                "ads_spend": float(row.get("Ads Spend", 0) or 0),
                "attributed_revenue": float(row.get("Attributed Revenue", 0) or 0),
                "is_paid": 1 if is_paid_raw in ("yes", "y", "true", "1") else 0,
            }
        )
    if marketing_rows:
        db.insert_marketing_metrics(marketing_rows)
        db.mark_data_source("Marketing", imported_by, "Manual Excel Upload", "current")
    result["Marketing"] = len(marketing_rows)

    return result
