"""
plugo_client.py
Adapter around Plugo's REST API. Only used when DATA_SOURCE_MODE=plugo/both.

Status (2026-09-06): base URL and auth mechanism below are CONFIRMED against
the live server (api.plugo.world responds 401 INVALID_API_KEY instead of a
generic error, meaning the request shape - path/method/headers - is accepted;
only the key value itself was rejected). What's still UNCONFIRMED because no
valid API key has produced a real response yet:
  - the exact JSON body /v1/products and /v1/orders expect (pagination,
    filters) - currently sent as an empty object
  - the exact response field names, hence _normalize_* below are still a
    best-effort guess and may need adjusting once real data comes back
  - a working inventory/stock endpoint - /v1/inventory and /v1/stocks both
    404; stock may be embedded in the product response instead
Get a valid key from https://admin.plugo.world/preferences/integrations,
retest, and adjust _normalize_* / fetch_inventory to match the real payload.
"""
import random
from datetime import datetime, timedelta

import requests

import config


def _headers() -> dict:
    return {
        "x-apikey": config.PLUGO_API_KEY,
        "x-vendor-id": config.PLUGO_VENDOR_ID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


class PlugoAPIError(Exception):
    pass


def _post(path: str, body: dict | None = None) -> dict:
    url = f"{config.PLUGO_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        resp = requests.post(url, headers=_headers(), json=body or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise PlugoAPIError(f"Plugo API request failed for {url}: {e}") from e


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{config.PLUGO_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        raise PlugoAPIError(f"Plugo API request failed for {url}: {e}") from e


def fetch_products() -> list[dict]:
    if config.PLUGO_USE_MOCK_DATA:
        return _mock_products()
    # Confirmed: this endpoint only accepts POST/DELETE/OPTIONS (GET -> 405).
    data = _post("v1/products")
    return [_normalize_product(p) for p in data.get("data", [])]


def fetch_recent_orders(since_minutes: float = 10) -> list[dict]:
    if config.PLUGO_USE_MOCK_DATA:
        return _mock_orders(since_minutes)
    since = (datetime.utcnow() - timedelta(minutes=since_minutes)).isoformat()
    # Confirmed: this endpoint accepts GET (unlike /v1/products).
    data = _get("v1/orders", params={"updated_since": since})
    return [_normalize_order(o) for o in data.get("data", [])]


def fetch_inventory() -> list[dict]:
    if config.PLUGO_USE_MOCK_DATA:
        return _mock_inventory()
    # UNCONFIRMED: /v1/inventory and /v1/stocks both 404 on the real server -
    # no working endpoint found yet. Raising loudly instead of silently
    # returning nothing, since a silent empty list would look like "synced,
    # zero stock everywhere" rather than "this isn't wired up yet".
    raise PlugoAPIError(
        "Endpoint inventory Plugo belum terkonfirmasi (v1/inventory dan v1/stocks "
        "sama-sama 404). Cek https://admin.plugo.world untuk dokumentasi endpoint yang "
        "benar, atau stock mungkin sudah ada di dalam response /v1/products - update "
        "fungsi ini begitu tahu strukturnya. Sementara isi Inventory manual lewat "
        "halaman Import Data."
    )


def _normalize_product(raw: dict) -> dict:
    return {
        "sku": raw.get("sku") or raw.get("id"),
        "product_name": raw.get("name") or raw.get("title"),
        "category": raw.get("category", "Uncategorized"),
        "hpp": float(raw.get("cost_price", 0) or 0),
        "selling_price": float(raw.get("price", 0) or 0),
        "vendor": raw.get("vendor", "Unknown"),
    }


def _normalize_order(raw: dict) -> dict:
    return {
        "order_id": raw.get("id") or raw.get("order_id"),
        "sku": raw.get("sku"),
        "order_date": raw.get("created_at", datetime.utcnow().isoformat()),
        "units_sold": int(raw.get("quantity", 1)),
        "revenue": float(raw.get("total", 0) or 0),
        "channel": raw.get("channel", "website"),
    }


def _normalize_inventory(raw: dict) -> dict:
    return {
        "sku": raw.get("sku"),
        "stock_on_hand": int(raw.get("stock", 0) or 0),
        "reserved_stock": int(raw.get("reserved", 0) or 0),
    }


_MOCK_CATALOG = [
    {"sku": "PSP-JKT-001", "product_name": "Essentiel DETIV Fitted Jacket - Candy Pink", "category": "Jacket", "hpp": 320000, "selling_price": 699000, "vendor": "Vendor A"},
    {"sku": "PSP-JKT-002", "product_name": "Stonage Bomber Jacket", "category": "Jacket", "hpp": 350000, "selling_price": 749000, "vendor": "Vendor A"},
    {"sku": "PSP-BAG-001", "product_name": "Knit-Leather Denim Backpack", "category": "Backpack", "hpp": 210000, "selling_price": 459000, "vendor": "Vendor B"},
    {"sku": "PSP-PNT-001", "product_name": "Essentiel Leather Pants", "category": "Pants", "hpp": 180000, "selling_price": 429000, "vendor": "Vendor B"},
    {"sku": "PSP-HOD-001", "product_name": "Telepati x Pospicc Hoodie", "category": "Hoodie", "hpp": 95000, "selling_price": 289000, "vendor": "Vendor C"},
    {"sku": "PSP-PNT-002", "product_name": "Baggy Jeans", "category": "Pants", "hpp": 140000, "selling_price": 349000, "vendor": "Vendor B"},
]


def _mock_products() -> list[dict]:
    return _MOCK_CATALOG


def _mock_orders(since_minutes: float) -> list[dict]:
    """Simulates ~2 new orders per 15 real-world minutes elapsed since the last
    sync, scaled by since_minutes - so re-clicking sync seconds after the
    previous one mostly yields 0 new orders, instead of always inventing 0-4
    regardless of how much real time actually passed."""
    orders = []
    now = datetime.utcnow()
    order_probability = min(1.0, since_minutes / 15) * 0.5
    n_orders = sum(1 for _ in range(4) if random.random() < order_probability)
    for _ in range(n_orders):
        product = random.choice(_MOCK_CATALOG)
        units = random.randint(1, 3)
        order_time = now - timedelta(minutes=random.uniform(0, max(since_minutes, 0.01)))
        orders.append(
            {
                "order_id": f"ORD-{int(order_time.timestamp())}-{random.randint(100,999)}",
                "sku": product["sku"],
                "order_date": order_time.isoformat(),
                "units_sold": units,
                "revenue": units * product["selling_price"],
                "channel": random.choice(["website", "marketplace", "instagram"]),
            }
        )
    return orders


def _mock_inventory() -> list[dict]:
    snapshots = []
    for product in _MOCK_CATALOG:
        base_stock = {"PSP-JKT-001": 6, "PSP-JKT-002": 22, "PSP-BAG-001": 4}.get(
            product["sku"], random.randint(5, 40)
        )
        snapshots.append(
            {
                "sku": product["sku"],
                "stock_on_hand": base_stock,
                "reserved_stock": random.randint(0, 2),
            }
        )
    return snapshots
