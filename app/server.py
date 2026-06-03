# from uuid import uuid4
import importlib
import asyncio
from fastapi import FastAPI, UploadFile, Path, Form, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .utils.file import save_to_disk
from .db.collections.files import files_collection, FileSchema, setup_ttl_index
from .queue.workers import process_file
from bson import ObjectId
from datetime import datetime
from typing import Optional
import os

# Use RQ queue only if REDIS_URL is set and reachable
USE_QUEUE = os.environ.get("USE_QUEUE", "false").lower() == "true"

if USE_QUEUE:
    from .queue.q import queue

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
    return {
        "_id": str(db_file["_id"]),
        "name": db_file["name"],
        "status": db_file["status"],
        "result": db_file.get("result"),
        "ats_score": db_file.get("ats_score"),
    }


def run_process_file(file_id: str, file_path: str, jd_content: str):
    """Run the async process_file in a new event loop (for BackgroundTasks)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_file(file_id, file_path, jd_content))
    finally:
        loop.close()


@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
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
    
    if USE_QUEUE:
        # Production: use Redis Queue with separate worker
        queue.enqueue(process_file, str(db_file.inserted_id), file_path, jd_content)
    else:
        # Free tier: use FastAPI BackgroundTasks (in-process)
        background_tasks.add_task(run_process_file, str(db_file.inserted_id), file_path, jd_content)
    
    await files_collection.update_one({"_id": db_file.inserted_id}, {
        "$set": {"status": "queued"}
        }
    )
    
    return {"file_id": str(db_file.inserted_id)}