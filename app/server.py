# from uuid import uuid4
import asyncio
from fastapi import FastAPI, UploadFile, Path, Form, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from .utils.file import save_to_disk
from .db.collections.files import files_collection, FileSchema, setup_ttl_index
from .queue.workers import process_file
from bson import ObjectId
from datetime import datetime
from typing import Optional
import subprocess
import os

app = FastAPI()

worker_process = None
REDIS_URL = os.environ.get("REDIS_URL", "redis://valkey:6379")

# Check if Redis is available
REDIS_AVAILABLE = False
try:
    from .queue.q import queue, redis_connection
    redis_connection.ping()
    REDIS_AVAILABLE = True
except Exception:
    pass

# Rate limiting config
RATE_LIMIT_MAX = 5  # max requests per IP
RATE_LIMIT_WINDOW = 60  # per 60 seconds

# Backpressure config
MAX_QUEUE_SIZE = 15  # matches Gemini's 15 req/min limit
MAX_BURST_WORKERS = 4  # max burst workers (total workers = 1 main + 4 burst = 5)


def is_rate_limited(client_ip: str) -> bool:
    """Check if client IP has exceeded rate limit using Redis sliding window."""
    if not REDIS_AVAILABLE:
        return False  # Skip rate limiting if Redis is down
    key = f"rate_limit:{client_ip}"
    current = redis_connection.get(key)
    if current and int(current) >= RATE_LIMIT_MAX:
        return True
    pipe = redis_connection.pipeline()
    pipe.incr(key)
    pipe.expire(key, RATE_LIMIT_WINDOW)
    pipe.execute()
    return False


@app.on_event("startup")
async def startup():
    await setup_ttl_index()
    if REDIS_AVAILABLE:
        # Start one persistent RQ worker
        global worker_process
        worker_process = subprocess.Popen(
            ["rq", "worker", "--url", REDIS_URL, "--name", "worker-main"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@app.on_event("shutdown")
def shutdown():
    global worker_process
    if worker_process:
        worker_process.terminate()
        worker_process.wait()


burst_worker_count = 0


def spawn_burst_worker():
    """Spawn a temporary worker that processes one job and exits."""
    global burst_worker_count
    if burst_worker_count >= MAX_BURST_WORKERS:
        return
    burst_worker_count += 1
    subprocess.Popen(
        ["rq", "worker", "--url", REDIS_URL, "--burst", "--name", f"worker-burst-{datetime.now().timestamp()}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/{id}")
async def get_file_by_id(id: str = Path(..., description="ID of the file")):
    if len(id) != 24:
        return {"error": "Invalid ID"}
    db_file = await files_collection.find_one({"_id": ObjectId(id)})
    if not db_file:
        return {"error": "File not found"}
    return {
        "_id": str(db_file["_id"]),
        "name": db_file["name"],
        "status": db_file["status"],
        "result": db_file.get("result"),
        "ats_score": db_file.get("ats_score"),
    }


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
):
    # Rate limiting: 5 uploads per minute per IP
    client_ip = request.client.host
    if is_rate_limited(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Max 5 uploads per minute."}
        )

    # Backpressure: reject if queue is full (protects Gemini API limit)
    if REDIS_AVAILABLE and len(queue) >= MAX_QUEUE_SIZE:
        return JSONResponse(
            status_code=503,
            content={"error": "System is busy. Please try again in a minute."}
        )

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
    
    if REDIS_AVAILABLE:
        # Production path: Redis Queue with workers
        queue.enqueue(process_file, str(db_file.inserted_id), file_path, jd_content, job_timeout=120)
        # If queue already has jobs waiting, spawn a burst worker
        if len(queue) > 0:
            spawn_burst_worker()
    else:
        # Fallback: in-process async execution (no Redis needed)
        asyncio.create_task(
            asyncio.to_thread(process_file, str(db_file.inserted_id), file_path, jd_content)
        )
    
    await files_collection.update_one({"_id": db_file.inserted_id}, {
        "$set": {"status": "queued"}
        }
    )
    
    return {"file_id": str(db_file.inserted_id)}
