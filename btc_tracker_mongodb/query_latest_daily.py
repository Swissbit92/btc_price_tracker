# query_latest_daily.py
from dotenv import load_dotenv
import os
from pymongo import MongoClient
import pandas as pd

load_dotenv()
uri = os.getenv("MONGODB_URI")

client = MongoClient(uri)
db = client["btc_data"]
coll = db["1h_price_data"]

cursor = (
    coll.find({}, { "_id": 0 })
        .sort("timestamp", -1)
        .limit(100)
)
df = pd.DataFrame(list(cursor))
print(df[["timestamp", "Open", "High", "Low", "Close", "Volume"]])
