"""
Root-level FastAPI entry point for uvicorn.
Delegates to backend.api.main:app for all routing.

This wrapper ensures:
  - `uvicorn main:app` continues to work without changes
  - Backend package remains self-contained and testable
"""

from backend.api.main import app

__all__ = ["app"]
