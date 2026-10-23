"""MEMORA AI Backend Entrypoint.

Exposes the unified FastAPI application from app.main so that running:
  - uvicorn main:app --port 8000 (from start.bat)
  - uvicorn app.main:app --port 8000 (from README.md)
  - python main.py
all run the identical full-featured MEMORA AI backend with Gemini AI & SQLite memory.
"""

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
