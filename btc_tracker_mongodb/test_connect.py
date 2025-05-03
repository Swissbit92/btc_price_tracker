from pymongo.mongo_client import MongoClient
import os
from dotenv import load_dotenv

# Load MONGODB_URI from .env (for local testing)
load_dotenv()
uri = os.getenv("MONGODB_URI")

client = MongoClient(uri)
try:
    client.admin.command("ping")
    print("✅ Successfully connected to MongoDB Atlas!")
except Exception as e:
    print("❌ Connection failed:", e)
