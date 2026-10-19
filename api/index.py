"""Eval Co-pilot API: one FastAPI app holding every /api door."""
from fastapi import FastAPI

app = FastAPI(title="Eval Co-pilot", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/health")
def health():
    return {"ok": True}
