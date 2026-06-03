# from uuid import uuid4
import importlib
from fastapi import FastAPI, UploadFile, Path, Form, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .utils.file import save_to_disk
from .db.collections.files import files_collection, FileSchema, setup_ttl_index
from .queue.q import queue
from .queue.workers import process_file
from bson import ObjectId
from datetime import datetime
from typing import Optional
import os

app = FastAPI()


@app.on_event("startup")
async def startup():
    await setup_ttl_index()

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/{id}")
async def get_file_by_id(id: str = Path(..., description="ID of the file")):
    db_file = await files_collection.find_one({"_id": ObjectId(id)})
    # print(db_file)
    return {
        "_id": str(db_file["_id"]),
        "name": db_file["name"],
        "status": db_file["status"],
        "result": db_file.get("result"),
        "ats_score": db_file.get("ats_score"),
    }


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
):
    db_file = await files_collection.insert_one(
        document=FileSchema(
            name=file.filename,
            status="saving",
            created_at=datetime.utcnow()
        )
    )
    
    file_path = f"/mnt/uploads/{str(db_file.inserted_id)}/{file.filename}"
    await save_to_disk(file=await file.read(), path=file_path)
    
    # Handle JD: text input or PDF upload
    jd_content = jd_text or ""
    if jd_file and jd_file.filename:
        jd_path = f"/mnt/uploads/{str(db_file.inserted_id)}/jd_{jd_file.filename}"
        await save_to_disk(file=await jd_file.read(), path=jd_path)
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(jd_path)
            for page in reader.pages:
                jd_content += page.extract_text() or ""
        except Exception:
            pass
    
    queue.enqueue(process_file, str(db_file.inserted_id), file_path, jd_content)
    
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