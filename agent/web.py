"""
FastAPI Web Application and REST API for the AI Research Agent.
Serves static assets, HTML templates, and provides real-time Server-Sent Events (SSE)
for live execution tracking.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from agent.config import settings
from agent.evaluation.dataset import BENCHMARK_TEST_SUITE
from agent.llm import get_llm_client
from agent.orchestrator import ResearchAgent

app = FastAPI(
    title="OmniResearch Agent API",
    description="Production-grade Autonomous Research Agent API with real-time SSE streaming",
    version="0.1.0"
)

# Static files & template paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ResearchRequest(BaseModel):
    query: str
    provider: Optional[str] = None
    compare_baseline: bool = False


class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serves the main application interface."""
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=404, detail="Template file not found.")
    return HTMLResponse(content=TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/health")
def health_check():
    """Returns agent health, provider configuration, and cache status."""
    return {
        "status": "healthy",
        "provider": settings.resolved_provider(),
        "cache_enabled": settings.cache_enabled,
        "openai_configured": bool(settings.openai_api_key),
        "gemini_configured": bool(settings.gemini_api_key),
        "version": "0.1.0"
    }


@app.get("/api/examples")
def get_example_queries():
    """Returns curated benchmark queries for the user interface."""
    return [{"id": tc.id, "query": tc.query, "category": tc.category} for tc in BENCHMARK_TEST_SUITE]


@app.post("/api/cache/clear")
def clear_cache():
    """Flushes in-memory tool cache."""
    agent = ResearchAgent()
    agent.registry.cache.clear()
    return {"status": "success", "message": "Tool cache cleared successfully."}


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    """Updates runtime configuration settings."""
    if req.provider:
        settings.llm_provider = req.provider  # type: ignore
    if req.openai_api_key:
        settings.openai_api_key = req.openai_api_key
    if req.gemini_api_key:
        settings.gemini_api_key = req.gemini_api_key
    return {
        "status": "success",
        "provider": settings.resolved_provider(),
        "openai_configured": bool(settings.openai_api_key),
        "gemini_configured": bool(settings.gemini_api_key)
    }


@app.post("/api/research")
def conduct_research(request: ResearchRequest):
    """Executes research synchronously and returns the complete dossier."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Research query cannot be empty.")

    provider_to_use = request.provider or settings.resolved_provider()
    llm = get_llm_client(provider=provider_to_use)
    agent = ResearchAgent(llm_client=llm)

    baseline_data = None
    if request.compare_baseline:
        baseline_data = agent.run_baseline(request.query)

    report = agent.run(request.query)
    return {
        "report": report.model_dump(),
        "baseline": baseline_data
    }


@app.post("/api/research/stream")
def stream_research(request: ResearchRequest):
    """
    Executes research while streaming real-time stage progress events via SSE.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Research query cannot be empty.")

    provider_to_use = request.provider or settings.resolved_provider()
    llm = get_llm_client(provider=provider_to_use)
    agent = ResearchAgent(llm_client=llm)

    def event_generator():
        # Stream live progress events as the agent runs
        for event in agent.run_stream(request.query):
            if event.get("type") == "complete" and request.compare_baseline:
                event["baseline"] = agent.run_baseline(request.query)
            payload = json.dumps(event)
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def main():
    uvicorn.run("agent.web:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
