import os
from pymongo import AsyncMongoClient

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://admin:admin@mongodb:27017")

mongo_client: AsyncMongoClient = AsyncMongoClient(MONGODB_URI)