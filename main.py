import os
import uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

app = FastAPI(title="Realtor Media API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists and is mounted as static
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
def read_root():
    return {"message": "Realtor Media API running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# Media endpoints
@app.post("/api/media")
async def upload_media(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None)
):
    """Upload an image or video and store metadata in database"""
    try:
        content_type = file.content_type or "application/octet-stream"
        kind = "video" if content_type.startswith("video/") else (
            "image" if content_type.startswith("image/") else "other"
        )
        if kind == "other":
            raise HTTPException(status_code=400, detail="Only images and videos are allowed")

        # Create safe unique filename
        ext = os.path.splitext(file.filename or "")[1] or (".mp4" if kind == "video" else ".jpg")
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(UPLOAD_DIR, unique_name)

        # Save file to disk
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
        size = os.path.getsize(dest_path)

        # Build public URL (served by StaticFiles)
        base_url = os.getenv("PUBLIC_BACKEND_URL") or ""
        url = f"/uploads/{unique_name}" if not base_url else f"{base_url}/uploads/{unique_name}"

        # Save metadata to DB
        try:
            from database import create_document
            from schemas import Media
            media_doc = Media(
                title=title,
                description=description,
                kind=kind, filename=unique_name, url=url,
                size=size, content_type=content_type
            )
            inserted_id = create_document("media", media_doc)
        except Exception as e:
            # Cleanup file if DB fails
            try:
                os.remove(dest_path)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

        return {"id": inserted_id, "message": "Uploaded", "item": media_doc.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/media")
def list_media(limit: int = 100):
    """List uploaded media items (most recent first)"""
    try:
        from database import get_documents
        items = get_documents("media", {}, limit)
        # Sort by created_at desc if present
        try:
            items.sort(key=lambda x: x.get("created_at"), reverse=True)
        except Exception:
            items = items
        # Convert ObjectId to string if any
        for it in items:
            if it.get("_id"):
                it["_id"] = str(it["_id"])
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list media: {str(e)}")
