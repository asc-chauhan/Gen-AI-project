import os
import certifi
from pymongo import AsyncMongoClient

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://admin:admin@mongodb:27017")

# Use certifi for Atlas SSL, skip for local
if "mongodb+srv" in MONGODB_URI or "mongodb.net" in MONGODB_URI:
    mongo_client: AsyncMongoClient = AsyncMongoClient(
        MONGODB_URI, 
        tlsCAFile=certifi.where(),
        tls=True
    )
else:
    mongo_client: AsyncMongoClient = AsyncMongoClient(MONGODB_URI)