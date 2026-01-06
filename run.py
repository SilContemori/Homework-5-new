"""Entry point for running the FastAPI application.

Usage: python run.py
"""
import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        "app.services.routes:app",
        host="0.0.0.0",
        port=5000,
        reload=True
    )

