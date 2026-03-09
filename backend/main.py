"""FastAPI backend for openaireview web upload."""

import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ratelimit import check_and_increment
from store import get_review
from worker import run_review

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_METHOD = os.environ.get("DEFAULT_METHOD", "progressive")

app = FastAPI(title="openaireview-backend")

_extra_origins = [o for o in os.environ.get("EXTRA_CORS_ORIGINS", "").split(",") if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://openaireview.github.io",
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://localhost:8080",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        *_extra_origins,
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.post("/review")
async def submit_review(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    email: str = Form(...),
):
    method = DEFAULT_METHOD

    filename = file.filename or "paper"
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".tex", ".md", ".txt"}:
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload a PDF, .tex, or .md file.")

    if not check_and_increment(email):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: 3 reviews per email per day.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum size is 10 MB.",
        )

    token = str(uuid.uuid4())
    background_tasks.add_task(run_review, token, content, filename, email, method)
    return {"token": token}


@app.get("/status/{token}")
async def get_status(token: str):
    row = get_review(token)
    if row is None:
        raise HTTPException(status_code=404, detail="Token not found.")
    return {"status": row["status"]}


@app.get("/results/{token}")
async def get_results(token: str):
    row = get_review(token)
    if row is None:
        raise HTTPException(status_code=404, detail="Token not found.")
    if row["status"] == "pending":
        raise HTTPException(status_code=202, detail="Review is still processing.")
    if row["status"] == "error":
        raise HTTPException(status_code=500, detail=row["error"] or "Review failed.")
    return row["data"]


# Serve static frontend locally when SERVE_STATIC=1
if os.environ.get("SERVE_STATIC") == "1":
    _static_dir = Path(__file__).resolve().parent.parent
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
