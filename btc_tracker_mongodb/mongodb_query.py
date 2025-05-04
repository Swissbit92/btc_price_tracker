#!/usr/bin/env python3
from dotenv import load_dotenv
import os
from pymongo import MongoClient
import pandas as pd

# Load your MONGODB_URI from .env
load_dotenv()
uri = os.getenv("MONGODB_URI")

# Connect
client     = MongoClient(uri)
db         = client["btc_data"]
collection = db["1h_price_data"]

# Query: latest 100 docs by timestamp descending
cursor = (
    collection
    .find({}, {"_id":0})            # project everything except _id
    .sort("timestamp", -1)          # newest first
    .limit(10)
)
df = pd.DataFrame(list(cursor))

# Show only the timestamp column (plus any fields you like)
print(df[["timestamp", "Open", "High", "Low", "Close", "Volume"]])
