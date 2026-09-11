"""
shopee_api_client.py
Adapter around Shopee Open Platform API v2 (official partner/seller API -
NOT the old Excel exports). Handles OAuth authorization, automatic access
token refresh, and pulling orders/products/stock for the sync scheduler.

Status (2026-09-09): base URL, OAuth flow, signing algorithm, and the core
endpoint paths below are the well-documented, current Shopee Open Platform v2
contract (https://open.shopee.com/) - cross-checked against multiple
independent integration guides. What's still UNVERIFIED because this dashboard
hasn't completed a real OAuth authorization yet:
  - exact field names inside get_order_detail / get_item_base_info / get_escrow_detail
    responses (Shopee's schema does drift between versions) - normalization
    below is best-effort and defensive (.get with fallbacks), and should be
    checked against a real response once you have a connected shop, then
    adjusted if any field comes back empty/wrong.
Get partner_id/partner_key by registering an app at https://open.shopee.com/
(Partner Portal -> App Management). See README for the one-time "Connect
Shopee" steps.
"""
import hashlib
import hmac
import time
from datetime import datetime, timedelta

import requests

import config
import database as db

MAX_ORDER_WINDOW_DAYS = 15  # Shopee's get_order_list hard limit per call


class ShopeeAPIError(Exception):
    pass


class ShopeeNotConnectedError(ShopeeAPIError):
    pass


def _sign(path: str, timestamp: int, access_token: str = "", shop_id: str = "") -> str:
    base_string = f"{config.SHOPEE_PARTNER_ID}{path}{timestamp}{access_token}{shop_id}"
    return hmac.new(
        config.SHOPEE_PARTNER_KEY.encode(), base_string.encode(), hashlib.sha256
    ).hexdigest()


def get_auth_url() -> str:
    """One-time authorization link - the seller opens this, logs into Shopee,
    approves access, and gets redirected back to SHOPEE_REDIRECT_URL with
    ?code=...&shop_id=... which complete_authorization() below consumes."""
    path = "/api/v2/shop/auth_partner"
    timestamp = int(time.time())
    sign = _sign(path, timestamp)
    return (
        f"{config.SHOPEE_API_HOST}{path}"
        f"?partner_id={config.SHOPEE_PARTNER_ID}&timestamp={timestamp}&sign={sign}"
        f"&redirect={config.SHOPEE_REDIRECT_URL}"
    )


def complete_authorization(code: str, shop_id: str) -> dict:
    """Exchanges the one-time `code` from Shopee's redirect for the
    access_token/refresh_token pair, and persists them to the database."""
    path = "/api/v2/auth/token/get"
    timestamp = int(time.time())
    sign = _sign(path, timestamp)
    url = f"{config.SHOPEE_API_HOST}{path}?partner_id={config.SHOPEE_PARTNER_ID}&timestamp={timestamp}&sign={sign}"
    resp = requests.post(
        url,
        json={"code": code, "shop_id": int(shop_id), "partner_id": int(config.SHOPEE_PARTNER_ID)},
        timeout=15,
    )
    data = resp.json()
    if data.get("error"):
        raise ShopeeAPIError(f"Gagal menukar authorization code: {data.get('error')} - {data.get('message')}")

    now = datetime.utcnow()
    db.save_shopee_tokens(
        shop_id=str(shop_id),
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        access_token_expires_at=(now + timedelta(seconds=data.get("expire_in", 14400))).isoformat(),
        refresh_token_expires_at=(now + timedelta(days=30)).isoformat(),
    )
    return data


def _refresh_token(tokens: dict) -> dict:
    path = "/api/v2/auth/access_token/get"
    timestamp = int(time.time())
    sign = _sign(path, timestamp)
    url = f"{config.SHOPEE_API_HOST}{path}?partner_id={config.SHOPEE_PARTNER_ID}&timestamp={timestamp}&sign={sign}"
    resp = requests.post(
        url,
        json={
            "refresh_token": tokens["refresh_token"],
            "shop_id": int(tokens["shop_id"]),
            "partner_id": int(config.SHOPEE_PARTNER_ID),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get("error"):
        raise ShopeeAPIError(
            f"Gagal refresh Shopee access token: {data.get('error')} - {data.get('message')}. "
            "Kemungkinan refresh_token sudah expired (30 hari) - sambungkan ulang lewat halaman Import Data."
        )
    now = datetime.utcnow()
    db.save_shopee_tokens(
        shop_id=tokens["shop_id"],
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", tokens["refresh_token"]),
        access_token_expires_at=(now + timedelta(seconds=data.get("expire_in", 14400))).isoformat(),
        refresh_token_expires_at=tokens.get("refresh_token_expires_at"),
    )
    return db.get_shopee_tokens()


def _get_valid_tokens() -> dict:
    tokens = db.get_shopee_tokens()
    if not tokens:
        raise ShopeeNotConnectedError(
            "Toko Shopee belum terhubung. Buka halaman Import Data -> tab Shopee API "
            "dan klik 'Connect Shopee' dulu."
        )
    expires_at = datetime.fromisoformat(tokens["access_token_expires_at"])
    # Refresh a bit early (5 min buffer) rather than racing the exact expiry.
    if datetime.utcnow() >= expires_at - timedelta(minutes=5):
        tokens = _refresh_token(tokens)
    return tokens


def _request(method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> dict:
    tokens = _get_valid_tokens()
    timestamp = int(time.time())
    sign = _sign(path, timestamp, access_token=tokens["access_token"], shop_id=tokens["shop_id"])
    query = {
        "partner_id": config.SHOPEE_PARTNER_ID,
        "timestamp": timestamp,
        "sign": sign,
        "access_token": tokens["access_token"],
        "shop_id": tokens["shop_id"],
        **(params or {}),
    }
    url = f"{config.SHOPEE_API_HOST}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, params=query, timeout=20)
        else:
            resp = requests.post(url, params=query, json=json_body or {}, timeout=20)
        data = resp.json()
    except requests.RequestException as e:
        raise ShopeeAPIError(f"Shopee API request failed for {path}: {e}") from e
    if data.get("error"):
        raise ShopeeAPIError(f"Shopee API error on {path}: {data.get('error')} - {data.get('message')}")
    return data.get("response", {})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def _list_order_sns(time_from: int, time_to: int) -> list[str]:
    order_sns = []
    cursor = ""
    for _ in range(50):  # hard safety cap on pagination loops
        resp = _request(
            "GET", "/api/v2/order/get_order_list",
            params={
                "time_range_field": "update_time",
                "time_from": time_from,
                "time_to": time_to,
                "page_size": 100,
                "cursor": cursor,
                # order_status is OPTIONAL (confirmed via Shopee's own API Test
                # Tool - no required-field marker, and "ALL" is NOT a valid
                # value despite earlier assumption otherwise) - omit it
                # entirely to get orders of every status.
            },
        )
        order_sns.extend(o["order_sn"] for o in resp.get("order_list", []))
        if not resp.get("more"):
            break
        cursor = resp.get("next_cursor", "")
        if not cursor:
            break
    return order_sns


def _fetch_order_details(order_sns: list[str]) -> list[dict]:
    details = []
    fields = (
        "order_status,buyer_username,recipient_address,item_list,total_amount,"
        "create_time,payment_method,shipping_carrier,actual_shipping_fee,"
        "voucher,coin_offset,discount,note"
    )
    for i in range(0, len(order_sns), 50):  # Shopee caps order_sn_list at 50 per call
        batch = order_sns[i:i + 50]
        resp = _request(
            "GET", "/api/v2/order/get_order_detail",
            params={"order_sn_list": ",".join(batch), "response_optional_fields": fields},
        )
        details.extend(resp.get("order_list", []))
    return details


def fetch_recent_orders(since_minutes: float = 60) -> tuple[list[dict], list[dict]]:
    """Returns (order_headers, sales_orders) normalized for db.upsert_order_headers
    / db.insert_sales_orders. Shopee limits get_order_list to a 15-day window
    per call, so the lookback is capped even if the scheduler was down longer."""
    now = int(time.time())
    time_from = now - int(min(since_minutes, MAX_ORDER_WINDOW_DAYS * 24 * 60) * 60)
    order_sns = _list_order_sns(time_from, now)
    if not order_sns:
        return [], []

    headers, line_items = [], []
    for order in _fetch_order_details(order_sns):
        order_sn = order.get("order_sn")
        create_time = order.get("create_time")
        order_date = (
            datetime.utcfromtimestamp(create_time).isoformat() if create_time else datetime.utcnow().isoformat()
        )
        addr = order.get("recipient_address") or {}
        headers.append(
            {
                "no_pesanan": order_sn,
                "status_pesanan": order.get("order_status"),
                "cancellation_status": None,
                "order_date": order_date,
                "payment_time": None,
                "ship_by_date": None,
                "arranged_shipping_time": None,
                "completed_time": None,
                "payment_method": order.get("payment_method"),
                "shipping_option": order.get("shipping_carrier"),
                "courier": order.get("shipping_carrier"),
                "tracking_number": None,
                "total_weight_gr": None,
                "total_payment": order.get("total_amount", 0),
                "shipping_fee_paid_by_buyer": order.get("actual_shipping_fee", 0),
                "total_discount": order.get("discount", 0),
                "voucher_seller": order.get("voucher", 0),
                "voucher_shopee": 0,
                "cashback_koin": order.get("coin_offset", 0),
                "creditcard_discount": 0,
                "buyer_username": order.get("buyer_username"),
                "buyer_note": order.get("note"),
                "city": addr.get("city"),
                "province": addr.get("state"),
            }
        )
        for idx, item in enumerate(order.get("item_list", [])):
            sku = item.get("model_sku") or item.get("item_sku") or f"SHOPEE-{item.get('item_id')}"
            line_items.append(
                {
                    "order_id": f"{order_sn}-{idx}",
                    "no_pesanan": order_sn,
                    "sku": sku,
                    "variant_name": item.get("model_name"),
                    "order_date": order_date,
                    "units_sold": item.get("model_quantity_purchased", 1),
                    "returned_quantity": 0,
                    "revenue": item.get("model_discounted_price", 0) * item.get("model_quantity_purchased", 1),
                    "channel": "Shopee",
                    "_product_name": item.get("item_name"),
                    "_selling_price": item.get("model_discounted_price", 0),
                }
            )
    return headers, line_items


# ---------------------------------------------------------------------------
# Products + stock
# ---------------------------------------------------------------------------
def _list_item_ids() -> list[int]:
    item_ids = []
    offset = 0
    for _ in range(50):
        resp = _request(
            "GET", "/api/v2/product/get_item_list",
            params={"offset": offset, "page_size": 100, "item_status": "NORMAL"},
        )
        items = resp.get("item", [])
        item_ids.extend(i["item_id"] for i in items)
        if not resp.get("has_next_page"):
            break
        offset += len(items)
        if not items:
            break
    return item_ids


def fetch_products_and_inventory() -> tuple[list[dict], list[dict]]:
    """Returns (products, inventory_snapshots). Variant-level (model) products
    use get_model_list for per-SKU price/stock; simple products without
    variants use the item-level fields directly."""
    item_ids = _list_item_ids()
    if not item_ids:
        return [], []

    products, inventory = [], []
    for i in range(0, len(item_ids), 50):  # Shopee caps item_id_list at 50 per call
        batch = item_ids[i:i + 50]
        resp = _request(
            "GET", "/api/v2/product/get_item_base_info",
            params={"item_id_list": ",".join(str(x) for x in batch)},
        )
        for item in resp.get("item_list", []):
            item_id = item["item_id"]
            item_name = item.get("item_name", f"Item {item_id}")
            if item.get("has_model"):
                for model in _list_models(item_id):
                    sku = model.get("model_sku") or f"SHOPEE-{item_id}-{model.get('model_id')}"
                    price = (model.get("price_info") or [{}])[0].get("current_price", 0)
                    stock = (model.get("stock_info_v2") or {}).get("summary_info", {}).get("total_available_stock", 0)
                    products.append({
                        "sku": sku, "product_name": f"{item_name} - {model.get('model_name', '')}",
                        "category": "Uncategorized", "hpp": 0, "selling_price": price, "vendor": "Shopee",
                    })
                    inventory.append({"sku": sku, "stock_on_hand": stock, "reserved_stock": 0})
            else:
                sku = item.get("item_sku") or f"SHOPEE-{item_id}"
                price = (item.get("price_info") or [{}])[0].get("current_price", 0)
                stock = (item.get("stock_info_v2") or {}).get("summary_info", {}).get("total_available_stock", 0)
                products.append({
                    "sku": sku, "product_name": item_name,
                    "category": "Uncategorized", "hpp": 0, "selling_price": price, "vendor": "Shopee",
                })
                inventory.append({"sku": sku, "stock_on_hand": stock, "reserved_stock": 0})
    return products, inventory


def _list_models(item_id: int) -> list[dict]:
    resp = _request("GET", "/api/v2/product/get_model_list", params={"item_id": item_id})
    return resp.get("model", [])
