import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
load_dotenv()  # <-- loads .env automatically

# ✅ Print environment variable values for debugging
url = os.getenv("ELASTICSEARCH_URL")
username = os.getenv("ELASTICSEARCH_USERNAME")
password = os.getenv("ELASTICSEARCH_PASSWORD")

print(f"ELASTICSEARCH_URL   = {url!r}")
print(f"ELASTICSEARCH_USERNAME = {username!r}")
print(f"ELASTICSEARCH_PASSWORD = {'<hidden>' if password else None}")

# ⚠️ Warn if any are missing
if not url or not username or not password:
    raise SystemExit("❗ ERROR: Missing one or more Elasticsearch environment variables (URL/user/password)")

# 🔧 Build the client
es = Elasticsearch(
    hosts=[url],
    basic_auth=(username, password),
    verify_certs=False  # For local dev with self-signed TLS
)

# 🧪 Test connection
try:
    info = es.info()
    print("✅ Connection successful!")
    print("Cluster info:", info)
except Exception as e:
    print("❌ Connection failed:")
    print(e)
    raise
