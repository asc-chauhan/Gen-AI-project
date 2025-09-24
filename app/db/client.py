from pymongo import AsyncMongoClient

mongo_client: AsyncMongoClient = AsyncMongoClient(
    "mongodb://admin:admin@mongodb:27017")