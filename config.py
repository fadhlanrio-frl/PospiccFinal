"""
config.py
Central place that reads all secrets/settings from environment variables (.env).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

PLUGO_BASE_URL = os.getenv("PLUGO_BASE_URL", "https://api.plugo.co")
PLUGO_API_KEY = os.getenv("PLUGO_API_KEY", "")
PLUGO_VENDOR_ID = os.getenv("PLUGO_VENDOR_ID", "")
PLUGO_USE_MOCK_DATA = _get_bool("PLUGO_USE_MOCK_DATA", default=True)
PLUGO_SYNC_INTERVAL_MINUTES = int(os.getenv("PLUGO_SYNC_INTERVAL_MINUTES", "10"))

# Data source mode: "plugo" (API/mock), "excel" (manual Inventory/Marketing
# template only - Shopee order/income Excel upload was replaced by the live
# Shopee API below), or "both". Plugo is left wired up but pending API key
# approval from Plugo's admin - see plugo_client.py.
DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "excel")
ENABLE_PLUGO_SYNC = DATA_SOURCE_MODE in ("plugo", "both")
ENABLE_EXCEL_IMPORT = DATA_SOURCE_MODE in ("excel", "both")

# --- Shopee Open Platform API v2 (semi real-time sync, hourly by default) ---
# Get SHOPEE_PARTNER_ID/SHOPEE_PARTNER_KEY by registering an app at
# https://open.shopee.com/ (Partner Portal -> App Management). SHOPEE_SHOP_ID
# is NOT set here - it's discovered automatically during the one-time
# "Connect Shopee" OAuth flow on the Import Data page and stored in the
# database (access/refresh tokens rotate constantly, so they live there too,
# never in this static file). See README for the full connect steps.
SHOPEE_PARTNER_ID = os.getenv("SHOPEE_PARTNER_ID", "")
SHOPEE_PARTNER_KEY = os.getenv("SHOPEE_PARTNER_KEY", "")
SHOPEE_REDIRECT_URL = os.getenv("SHOPEE_REDIRECT_URL", "")
SHOPEE_API_HOST = os.getenv("SHOPEE_API_HOST", "https://partner.shopeemobile.com")
SHOPEE_SYNC_INTERVAL_MINUTES = int(os.getenv("SHOPEE_SYNC_INTERVAL_MINUTES", "60"))
SHOPEE_API_CONFIGURED = bool(SHOPEE_PARTNER_ID and SHOPEE_PARTNER_KEY and SHOPEE_REDIRECT_URL)

LOW_STOCK_THRESHOLD_UNITS = int(os.getenv("LOW_STOCK_THRESHOLD_UNITS", "10"))
LOW_STOCK_DAYS_TO_STOCKOUT = int(os.getenv("LOW_STOCK_DAYS_TO_STOCKOUT", "7"))
STALE_DATA_HOURS = int(os.getenv("STALE_DATA_HOURS", "24"))
LOW_ROAS_THRESHOLD = float(os.getenv("LOW_ROAS_THRESHOLD", "1.5"))
SALES_SPIKE_MULTIPLIER = float(os.getenv("SALES_SPIKE_MULTIPLIER", "2.0"))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "pospicc.db"))
