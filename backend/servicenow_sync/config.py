import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SERVICENOW_INSTANCE_URL = os.getenv("SERVICENOW_INSTANCE_URL", "").rstrip("/")
SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "")
SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "")
SERVICENOW_TABLE = os.getenv("SERVICENOW_TABLE", "incident")

SN_PG_HOST = os.getenv("SN_PG_HOST", "localhost")
SN_PG_PORT = int(os.getenv("SN_PG_PORT", "5432"))
SN_PG_DB = os.getenv("SN_PG_DB", "servicenow_tickets")
SN_PG_USER = os.getenv("SN_PG_USER", "yaswanthg")
SN_PG_PASSWORD = os.getenv("SN_PG_PASSWORD", "")

SERVICENOW_WEBHOOK_SECRET = os.getenv("SERVICENOW_WEBHOOK_SECRET", "")

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8800"))
