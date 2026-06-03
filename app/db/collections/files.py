from typing import TypedDict, Optional
from datetime import datetime
from pydantic import Field
from pymongo.asynchronous.collection import AsyncCollection
from ..db import database


class FileSchema(TypedDict):
    name: str = Field(..., description="The name of the file")
    status: str = Field(..., description="The status of the file")
    result: Optional[str] = Field(..., description="The result from AI")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Auto-delete after TTL")
    
    
COLLECTION_NAME = "files"
files_collection: AsyncCollection = database[COLLECTION_NAME]


async def setup_ttl_index():
    """Auto-delete documents after 2 minutes"""
    await files_collection.create_index("created_at", expireAfterSeconds=120)