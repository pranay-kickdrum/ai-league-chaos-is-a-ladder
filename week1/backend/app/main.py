"""FastAPI application – Real-Time News Claim Verification System."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import VerifyRequest, VerifyResponse
from app.services.agent import run_verification_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Claim Verification API",
    description="Real-Time News Claim Verification using RAG + Agentic RAG",
    version="1.0.0",
)

# -- CORS (allow browser extension & local dev) --
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/verify", response_model=VerifyResponse)
async def verify_claim(req: VerifyRequest):
    """Main endpoint: accepts a claim and returns a verified verdict."""
    logger.info("Received verification request: %s", req.text[:120])
    start = time.time()

    try:
        result = await run_verification_pipeline(req.text, source_url=req.url)
    except Exception as exc:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed_ms = int((time.time() - start) * 1000)
    result.metadata["processing_time_ms"] = elapsed_ms
    logger.info(
        "Verdict=%s  confidence=%.2f  time=%dms",
        result.verdict.value,
        result.confidence,
        elapsed_ms,
    )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
