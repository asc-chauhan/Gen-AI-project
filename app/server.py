# from uuid import uuid4
import importlib
from fastapi import FastAPI, UploadFile, Path
from .utils.file import save_to_disk
from .db.collections.files import files_collection, FileSchema
from .queue.q import queue
from .queue.workers import process_file
from bson import ObjectId

# from .queue.connection import queue
# from .queue.worker import process_query

app = FastAPI()


@app.get("/")
def health():
    return {"status": "Server is up and running"}


@app.get("/{id}")
async def get_file_by_id(id: str = Path(..., description="ID of the file")):
    db_file = await files_collection.find_one({"_id": ObjectId(id)})
    # print(db_file)
    return {
        "_id": str(db_file["_id"]),
        "name": db_file["name"],
        "status": db_file["status"],
        "result":  db_file["result"] if "result" in db_file else None,
    }


@app.post("/upload")
async def upload_file(
    file: UploadFile
):
    # id = uuid4()
    db_file = await files_collection.insert_one(
        document=FileSchema(
            name=file.filename,
            status="saving"
        )
    )
    
    file_path = f"/mnt/uploads/{str(db_file.inserted_id)}/{file.filename}"
    await save_to_disk(file=await file.read(), path=file_path)
    
    queue.enqueue(process_file, str(db_file.inserted_id), file_path)
    
    await files_collection.update_one({"_id": str(db_file.inserted_id)}, {
        "$set": {"status": "queued"}
        }
    )
    
    return {"file_id": str(db_file.inserted_id)}

# @app.post("/chat")
# def chat(query: str = Query(..., description="Chat message...")):
#     # Take the query & push the query to queue
#     # Internally calls as process_query(query)
#     job = queue.enqueue(process_query, query)

#     # Give a response to user about job received
#     return {"status": "Queued", "job_id": job.id}


# @app.get("/result/{job_id}")
# def get_result(
#     job_id: str = Path(..., description="Job ID...")
# ):
#     job = queue.fetch_job(job_id=job_id)

#     result = job.return_value()

#     return {"result": result}