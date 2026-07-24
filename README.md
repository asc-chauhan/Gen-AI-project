# Resume Analysis Application - Interview Prep Guide

## Project Overview

A full-stack application that processes PDF resumes and generates AI-powered feedback using multimodal vision models. The system handles file uploads, converts PDFs to images, and uses Gemini 2.0 Flash API to analyze and critique resume content.

## Architecture & Flow

### High-Level Flow
1. **Upload**: User uploads PDF → Saved to disk → Metadata stored in MongoDB → Job queued in Redis
2. **Processing**: Worker picks up job → Converts PDF to images → Encodes images to base64 → Calls Gemini API
3. **Result**: AI response stored in MongoDB → User can query status/result via API

### System Architecture
```
FastAPI Server → MongoDB (Metadata) → Redis Queue → Background Workers
                                      ↓
                              PDF → Images → Base64 → Gemini API
```

## Key Components

### 1. FastAPI Backend (`app/server.py`)
- **Endpoints**:
  - `GET /`: Health check
  - `POST /upload`: Accepts PDF file, saves to disk, queues job
  - `GET /{id}`: Retrieves file status and AI result by ID

**Key Points to Explain**:
- Used async/await for non-blocking I/O operations
- FastAPI's automatic validation and documentation
- File upload handling with `UploadFile`

### 2. MongoDB Integration (`app/db/`)
- **Purpose**: Stores file metadata (name, status, result)
- **Schema**: FileSchema with name, status, and optional result field
- **Why MongoDB**: 
  - Document-based storage fits JSON-like data
  - Flexible schema for evolving requirements
  - Good for storing nested data (status updates, results)

**Key Points to Explain**:
- Used `AsyncMongoClient` for async operations
- ObjectId for unique document identification
- Status tracking: saving → queued → processing → processed

### 3. Redis Queue (`app/queue/`)
- **Purpose**: Background job processing
- **Why RQ (Redis Queue)**:
  - Prevents API blocking during long-running operations
  - Decouples upload from processing
  - Allows horizontal scaling of workers

**Key Points to Explain**:
- Redis as message broker
- Workers run independently from API server
- Job enqueuing is synchronous, execution is asynchronous

### 4. Background Worker (`app/queue/workers.py`)
- **Process Flow**:
  1. Update status to "processing"
  2. Convert PDF pages to JPEG images using `pdf2image`
  3. Encode images to base64
  4. Call Gemini API with multimodal input
  5. Store result in MongoDB

**Key Points to Explain**:
- Why convert PDF to images? Gemini vision models need image input
- Base64 encoding for embedding images in API requests
- Status updates at each stage for user visibility

### 5. File Storage (`app/utils/file.py`)
- Uses `aiofiles` for async file operations
- Saves files to `/mnt/uploads/` with unique ID-based paths

## Technical Decisions & Trade-offs

### Why FastAPI?
- **Async support**: Better performance for I/O-bound operations
- **Automatic docs**: OpenAPI/Swagger UI out of the box
- **Type hints**: Better IDE support and fewer runtime errors
- **Modern Python**: Built on Pydantic and Starlette

### Why Async MongoDB?
- Non-blocking database operations
- Better concurrency when handling multiple requests
- Works well with FastAPI's async nature

### Why Background Jobs?
- **Problem**: PDF conversion and AI processing takes time (seconds to minutes)
- **Solution**: Queue jobs so API responds immediately
- **Benefit**: Better user experience, API stays responsive

### Why Base64 Encoding?
- Gemini API accepts images via data URLs
- Format: `data:image/jpeg;base64,{encoded_string}`
- Allows embedding images directly in JSON payload

## Docker & Deployment

### Docker Compose Services
- **app**: Main application container
- **mongodb**: Database service
- **valkey**: Redis-compatible in-memory store
- **Services communicate via Docker network hostnames**

### Why Docker?
- Consistent development/production environments
- Easy dependency management
- Isolated services
- Simplified deployment

## Common Interview Questions & Answers

### Q1: Walk me through what happens when a user uploads a file.
**Answer**: 
1. User sends POST request with PDF file to `/upload` endpoint
2. FastAPI receives file, creates MongoDB document with status "saving"
3. File saved to disk at `/mnt/uploads/{id}/{filename}` using async file operations
4. Job enqueued to Redis Queue with file ID and path
5. Status updated to "queued" in MongoDB
6. API immediately returns file_id to user
7. Background worker picks up job, processes file, updates status throughout

### Q2: Why did you use Redis Queue instead of processing synchronously?
**Answer**: 
- PDF conversion and AI API calls can take 10-30 seconds
- Synchronous processing would block the API, making it unresponsive
- With RQ, API responds immediately, improving user experience
- Allows scaling workers independently based on load

### Q3: How does the status tracking work?
**Answer**:
- Status field in MongoDB document tracks current state
- States: "saving" → "queued" → "processing" → "Converting to images" → "Processed"
- Worker updates status at each stage
- User can poll `GET /{id}` to check status and get result when ready

### Q4: Why convert PDF to images instead of extracting text?
**Answer**:
- Gemini 2.0 Flash is a vision model that analyzes visual layout
- Preserves formatting, design, and visual structure
- Can provide feedback on resume design, not just content
- Multimodal models excel at understanding document structure

### Q5: How would you handle errors or failures?
**Answer** (if not implemented, explain approach):
- Add try-catch blocks in worker function
- Update status to "failed" with error message
- Implement retry logic for transient failures (API timeouts)
- Add logging for debugging
- Consider dead letter queue for permanently failed jobs

### Q6: How would you scale this system?
**Answer**:
- **Horizontal scaling**: Add more worker processes/containers
- **Database**: MongoDB replica sets for read scaling
- **Queue**: Redis Cluster for high availability
- **File storage**: Move to S3/cloud storage instead of local disk
- **Caching**: Cache frequently accessed results
- **Load balancing**: Multiple API instances behind load balancer

### Q7: What are the potential bottlenecks?
**Answer**:
- **PDF conversion**: CPU-intensive, could parallelize per page
- **AI API calls**: Rate limits, network latency
- **File I/O**: Disk speed for large files
- **Database writes**: Many status updates per file

### Q8: How does async/await improve performance?
**Answer**:
- Allows handling multiple requests concurrently
- While waiting for DB/API/file I/O, server can process other requests
- Better resource utilization than blocking synchronous code
- Especially important for I/O-bound operations (this project)

### Q9: Explain the base64 encoding step.
**Answer**:
- Read image file as binary
- Encode binary data to base64 string
- Embed in JSON as data URL: `data:image/jpeg;base64,{string}`
- Gemini API decodes and processes the image
- Standard way to send binary data in JSON payloads

### Q10: What would you improve in this project?
**Answer**:
- **Error handling**: Comprehensive try-catch and retry logic
- **Validation**: Check file type, size limits before processing
- **Security**: Authentication, rate limiting, input sanitization
- **Testing**: Unit tests, integration tests
- **Monitoring**: Logging, metrics, alerting
- **Optimization**: Process multiple pages in parallel
- **Storage**: Use cloud storage (S3) instead of local disk

## Technical Deep Dives

### Async Programming Pattern
```python
# Async allows non-blocking operations
async def upload_file(file: UploadFile):
    # These operations don't block the event loop
    await files_collection.insert_one(...)  # DB write
    await save_to_disk(...)                  # File I/O
    queue.enqueue(...)                       # Queue (sync but fast)
    await files_collection.update_one(...)   # DB update
```

### Status State Machine
```
saving → queued → processing → Converting to images → 
Converting to images success → Processed
```

### Data Flow
1. **Upload**: File bytes → Disk storage
2. **Conversion**: PDF → PIL Images → JPEG files
3. **Encoding**: JPEG files → Base64 strings
4. **API Call**: Base64 + text prompt → Gemini API
5. **Storage**: AI response → MongoDB result field

## Key Technologies Explained

### FastAPI
- Modern Python web framework
- Built on Starlette (ASGI) and Pydantic
- Automatic request validation and serialization
- Async/await support

### MongoDB
- NoSQL document database
- Stores JSON-like documents
- Flexible schema
- Good for rapid development

### Redis/Valkey
- In-memory data store
- Used as message broker for RQ
- Fast, lightweight
- Supports pub/sub, queues

### RQ (Redis Queue)
- Simple Python job queue library
- Uses Redis as backend
- Easy to use, good for Python projects
- Workers run as separate processes

### pdf2image
- Converts PDF pages to PIL Image objects
- Requires poppler-utils system dependency
- Handles multi-page documents
- Can specify DPI for quality

### Gemini API
- Google's multimodal AI model
- Accepts text + images
- OpenAI-compatible SDK
- Returns structured text responses

## Running the Project

### Prerequisites
- Docker and Docker Compose
- Python 3.12 (if running locally)

### Setup
1. Start services: `docker-compose up`
2. Install dependencies: `pip install -r requirements.txt`
3. Run API: `uvicorn app.server:app --host 0.0.0.0 --port 8000`
4. Run worker: `rq worker --url redis://valkey`

### API Usage
```bash
# Upload file
curl -X POST "http://localhost:8000/upload" \
  -F "file=@resume.pdf"

# Check status
curl "http://localhost:8000/{file_id}"
```

## Project Strengths to Highlight

1. **Full-stack development**: API, database, background jobs
2. **Async architecture**: Modern Python async patterns
3. **Scalable design**: Decoupled components, horizontal scaling
4. **AI integration**: Multimodal API usage
5. **Production-ready patterns**: Docker, status tracking, error handling structure
6. **Clean code**: Modular structure, separation of concerns

## Areas for Discussion

Be prepared to discuss:
- Trade-offs between sync and async
- Database choice (MongoDB vs PostgreSQL)
- Queue system alternatives (Celery, RabbitMQ)
- File storage strategies (local vs cloud)
- Error handling and retry strategies
- Testing approaches
- Security considerations
- Performance optimization ideas

---

**Remember**: Focus on explaining the "why" behind decisions, not just the "what". Show understanding of trade-offs and scalability considerations.
