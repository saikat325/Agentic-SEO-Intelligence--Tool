import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any
import os

from core.config import get_settings
from core.ingestion import clone_repository, walk_files, get_repo_id
from core.chunker import chunk_file
from core.vectorstore import index_chunks, semantic_search, repo_is_indexed
from agents.search_agent import run_query

settings = get_settings()

app = FastAPI(
    title="GitHub Repository Intelligence API",
    description="Natural Language Code Search & Semantic Navigation Pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracker
_jobs: Dict[str, Dict[str, Any]] = {}


# ─── Schemas ──────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    github_url: str

class QueryRequest(BaseModel):
    repo_id: str
    query: str

class StatusResponse(BaseModel):
    repo_id: str
    status: str
    message: str
    indexed_chunks: Optional[int] = None
    file_count: Optional[int] = None



# ─── Background Indexing ──────────────────────────────────────────────────────

async def index_repo_background(github_url: str, repo_id: str):
    try:
        _jobs[repo_id] = {"status": "cloning", "message": "Cloning repository..."}

        loop = asyncio.get_event_loop()
        meta = await loop.run_in_executor(None, clone_repository, github_url)

        _jobs[repo_id] = {"status": "parsing", "message": "Parsing files..."}
        files = await loop.run_in_executor(None, walk_files, meta["clone_path"])

        if not files:
            _jobs[repo_id] = {"status": "error", "message": "No supported files found."}
            return

        _jobs[repo_id] = {
            "status": "chunking",
            "message": f"Chunking {len(files)} files...",
        }

        all_chunks = []
        for f in files:
            chunks = chunk_file(f)
            all_chunks.extend(chunks)

        _jobs[repo_id] = {
            "status": "indexing",
            "message": f"Indexing {len(all_chunks)} chunks...",
        }

        count = await loop.run_in_executor(None, index_chunks, repo_id, all_chunks)

        _jobs[repo_id] = {
            "status": "ready",
            "message": "Repository indexed and ready for queries.",
            "indexed_chunks": count,
            "file_count": len(files),
            "owner": meta["owner"],
            "repo": meta["repo"],
        }

    except Exception as e:
        _jobs[repo_id] = {"status": "error", "message": str(e)}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "GitHub Repository Intelligence API", "version": "1.0.0"}


@app.post("/ingest", response_model=StatusResponse)
async def ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """Accept a GitHub URL, kick off background cloning + indexing."""
    try:
        repo_id = get_repo_id(req.github_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if repo_id in _jobs and _jobs[repo_id]["status"] in ("cloning", "parsing", "chunking", "indexing"):
        return StatusResponse(
            repo_id=repo_id,
            status=_jobs[repo_id]["status"],
            message="Indexing already in progress.",
        )

    if repo_is_indexed(repo_id) and repo_id in _jobs and _jobs[repo_id]["status"] == "ready":
        j = _jobs[repo_id]
        return StatusResponse(
            repo_id=repo_id,
            status="ready",
            message="Already indexed.",
            indexed_chunks=j.get("indexed_chunks"),
            file_count=j.get("file_count"),
        )

    background_tasks.add_task(index_repo_background, req.github_url, repo_id)

    return StatusResponse(
        repo_id=repo_id,
        status="started",
        message="Indexing started. Poll /status/{repo_id} for updates.",
    )


@app.get("/status/{repo_id}", response_model=StatusResponse)
def get_status(repo_id: str):
    """Poll indexing status for a given repo_id."""
    if repo_id not in _jobs:
        if repo_is_indexed(repo_id):
            return StatusResponse(
                repo_id=repo_id,
                status="ready",
                message="Repository is indexed.",
            )
        raise HTTPException(status_code=404, detail="Repo not found. Please ingest first.")

    j = _jobs[repo_id]
    return StatusResponse(
        repo_id=repo_id,
        status=j["status"],
        message=j["message"],
        indexed_chunks=j.get("indexed_chunks"),
        file_count=j.get("file_count"),
    )


@app.post("/query")
async def query(req: QueryRequest):
    """Run a natural language query against an indexed repository."""
    if not repo_is_indexed(req.repo_id):
        raise HTTPException(
            status_code=400,
            detail="Repository not indexed. Call /ingest first.",
        )

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_query, req.repo_id, req.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search/{repo_id}")
async def raw_search(repo_id: str, q: str, top_k: int = 5):
    """Raw semantic search without LLM analysis (debug endpoint)."""
    if not repo_is_indexed(repo_id):
        raise HTTPException(status_code=400, detail="Repository not indexed.")

    loop = asyncio.get_event_loop()
    hits = await loop.run_in_executor(None, semantic_search, repo_id, q, top_k)
    return {"query": q, "hits": hits}


@app.get("/repos")
def list_repos():
    """List all tracked repositories and their status."""
    return {
        "repos": [
            {"repo_id": rid, **info}
            for rid, info in _jobs.items()
        ]
    }
