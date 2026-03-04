import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check backend/.env")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

SLA_UPDATE_HOURS = 2

EMBEDDING_PROVIDER = "local"
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 1536

# Web search configuration
# Bing Search API credentials (optional, falls back to alternative methods)
BING_SEARCH_API_KEY = os.getenv("BING_SEARCH_API_KEY")
BING_SEARCH_ENDPOINT = os.getenv(
    "BING_SEARCH_ENDPOINT",
    "https://api.bing.microsoft.com/v7.0/search"
)

# Web search behavior
WEB_SEARCH_MAX_RESULTS = 5  # Maximum solutions to return
WEB_SEARCH_TIMEOUT = 10  # Timeout for web requests in seconds