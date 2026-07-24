from pdf2image import convert_from_path
from bson import ObjectId
import os
import re
import base64
import shutil
import time
import certifi
from openai import OpenAI
from datetime import datetime
from PyPDF2 import PdfReader
from pymongo import MongoClient
from redis import Redis

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://admin:admin@mongodb:27017")
REDIS_URL = os.environ.get("REDIS_URL", "redis://valkey:6379")

client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

redis_client = Redis.from_url(REDIS_URL)

# Circuit breaker config
CIRCUIT_FAILURE_THRESHOLD = 5  # failures before opening
CIRCUIT_COOLDOWN = 30  # seconds before trying again
CIRCUIT_WINDOW = 60  # failure count window


def circuit_is_open() -> bool:
    """Check if circuit breaker is open (API considered down)."""
    state = redis_client.get("circuit:gemini:state")
    return state == b"open"


def record_failure():
    """Record a failure. If threshold reached, open the circuit."""
    pipe = redis_client.pipeline()
    pipe.incr("circuit:gemini:failures")
    pipe.expire("circuit:gemini:failures", CIRCUIT_WINDOW)
    pipe.execute()

    failures = int(redis_client.get("circuit:gemini:failures") or 0)
    if failures >= CIRCUIT_FAILURE_THRESHOLD:
        redis_client.set("circuit:gemini:state", "open", ex=CIRCUIT_COOLDOWN)


def record_success():
    """Reset failure count on success."""
    redis_client.delete("circuit:gemini:failures")
    redis_client.delete("circuit:gemini:state")


def get_sync_collection():
    """Get a synchronous MongoDB collection for use in RQ workers."""
    if "mongodb+srv" in MONGODB_URI or "mongodb.net" in MONGODB_URI:
        mongo_client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), tls=True)
    else:
        mongo_client = MongoClient(MONGODB_URI)
    return mongo_client["mydb"]["files"]


def call_with_retry(func, max_retries=3, base_delay=2):
    """Call a function with exponential backoff retry and circuit breaker."""
    # Circuit breaker: if open, fail fast
    if circuit_is_open():
        raise Exception("Circuit breaker OPEN — Gemini API is temporarily unavailable. Try again later.")

    for attempt in range(max_retries):
        try:
            result = func()
            record_success()
            return result
        except Exception as e:
            record_failure()
            if attempt == max_retries - 1:
                raise e
            delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s
            time.sleep(delay)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def process_file(id: str, file_path: str, jd_content: str = ""):
    files_collection = get_sync_collection()

    try:
        files_collection.update_one({"_id": ObjectId(id)}, {
            "$set": {"status": "Converting PDF"}
        })

        pages = convert_from_path(file_path)
        images = []

        for i, page in enumerate(pages):
            image_save_path = f"/mnt/uploads/images/{id}/image-{i}.jpg"
            os.makedirs(os.path.dirname(image_save_path), exist_ok=True)
            page.save(image_save_path, 'JPEG')
            images.append(image_save_path)

        files_collection.update_one({"_id": ObjectId(id)}, {
            "$set": {"status": "Extracting text"}
        })

        # Extract text from PDF
        extracted_text = ""
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
        except Exception:
            extracted_text = ""

        files_collection.update_one({"_id": ObjectId(id)}, {
            "$set": {"status": "Analyzing with AI"}
        })

        image_base64 = [encode_image(img) for img in images]

        # Build image content for all pages
        image_content = []
        for img_b64 in image_base64:
            image_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}"
                },
            })

        # Build user prompt with text if available
        user_text = "Analyze this resume. Provide an ATS compatibility score and detailed professional feedback."
        if extracted_text.strip():
            user_text += f"\n\nHere is the extracted text from the resume for accurate analysis:\n\n{extracted_text.strip()}"
        if jd_content.strip():
            user_text += f"\n\nHere is the job description to match against:\n\n{jd_content.strip()}"

        # Build system prompt based on whether JD is provided
        if jd_content.strip():
            system_prompt = """You are an expert resume analyst and ATS (Applicant Tracking System) specialist.
Today's date is """ + datetime.now().strftime("%B %d, %Y") + """.
A job description has been provided. Analyze how well the resume matches this specific role.
Respond in this EXACT format:

ATS_SCORE: [number 0-100]

## JD Match Analysis
[How well does the resume align with this specific job description? What keywords and requirements are matched vs missing?]

## ATS Compatibility
[How well it passes ATS systems for this specific role - keyword optimization, formatting, parsability]

## Strengths
[What the resume does well relative to this job]

## Gaps
[Skills, experience, or keywords from the JD that are missing from the resume]

## Suggestions
[Specific changes to better match this job description]

Be professional, specific, and constructive. Reference actual content from both the resume and job description."""
        else:
            system_prompt = """You are an expert resume analyst and ATS (Applicant Tracking System) specialist.
Today's date is """ + datetime.now().strftime("%B %d, %Y") + """.
Analyze the resume and respond in this EXACT format:

ATS_SCORE: [number 0-100]

## ATS Compatibility
[Bullet points on how well it passes ATS systems - keyword optimization, formatting issues, parsability]

## Strengths
[What the resume does well]

## Weaknesses
[What needs improvement]

## Suggestions
[Specific actionable improvements]

Be professional, specific, and constructive. Reference actual content from the resume."""

        result = call_with_retry(lambda: client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text,
                        },
                        *image_content
                    ],
                }
            ],
        ))
        response_text = result.choices[0].message.content

        # Parse ATS score from response
        score_match = re.search(r'ATS_SCORE:\s*(\d+)', response_text)
        ats_score = int(score_match.group(1)) if score_match else None
        clean_result = re.sub(r'ATS_SCORE:\s*\d+\n*', '', response_text).strip()

        files_collection.update_one({"_id": ObjectId(id)}, {
            "$set": {
                "status": "Processed",
                "result": clean_result,
                "ats_score": ats_score
            }
        })

    except Exception as e:
        files_collection.update_one({"_id": ObjectId(id)}, {
            "$set": {
                "status": "Failed",
                "result": f"Something went wrong: {str(e)}"
            }
        })

    finally:
        # Cleanup uploaded files and images
        upload_dir = os.path.dirname(file_path)
        images_dir = f"/mnt/uploads/images/{id}"
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        if os.path.exists(images_dir):
            shutil.rmtree(images_dir)
    