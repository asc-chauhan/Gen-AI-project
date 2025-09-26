from typing import TypedDict, Optional
from pydantic import Field
from pymongo.asynchronous.collection import AsyncCollection
from ..db import database


class FileSchema(TypedDict):
    name: str = Field(..., description="The name of the file")
    status: str = Field(..., description="The status of the file")
    result: Optional[str] = Field(..., description="The result from AI")
    # file_path: str = Field(..., description="File path")
    
    
COLLECTION_NAME = "files"
files_collection: AsyncCollection = database[COLLECTION_NAME]