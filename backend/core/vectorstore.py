import os
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from core.config import get_settings

settings = get_settings()

_embed_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.Client] = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(settings.embed_model)
    return _embed_model


def get_chroma_client() -> chromadb.Client:
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(settings.chroma_persist_dir, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def collection_name(repo_id: str) -> str:
    return f"repo_{repo_id}"


def index_chunks(repo_id: str, chunks: List[Dict[str, Any]]) -> int:
    """Embed and store chunks in ChromaDB. Returns number of indexed chunks."""
    client = get_chroma_client()
    model = get_embed_model()
    col_name = collection_name(repo_id)

    # Delete old collection if exists (re-index)
    try:
        client.delete_collection(col_name)
    except Exception:
        pass

    col = client.create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 100
    total = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        ids = [c["chunk_id"] for c in batch]
        metadatas = [
            {
                "file_path": c["file_path"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "symbol_name": c.get("symbol_name") or "",
                "symbol_type": c.get("symbol_type") or "",
                "language": c.get("language") or "",
            }
            for c in batch
        ]

        col.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        total += len(batch)

    return total


def semantic_search(
    repo_id: str,
    query: str,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Run semantic similarity search against the repo vector index."""
    client = get_chroma_client()
    model = get_embed_model()
    col_name = collection_name(repo_id)

    try:
        col = client.get_collection(col_name)
    except Exception:
        return []

    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    results = col.query(
        query_embeddings=query_embedding,
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text": doc,
            "file_path": meta["file_path"],
            "start_line": meta["start_line"],
            "end_line": meta["end_line"],
            "symbol_name": meta["symbol_name"],
            "symbol_type": meta["symbol_type"],
            "language": meta["language"],
            "score": round(1 - dist, 4),  # cosine similarity
        })

    return hits


def repo_is_indexed(repo_id: str) -> bool:
    """Check if a repo has already been indexed."""
    client = get_chroma_client()
    try:
        col = client.get_collection(collection_name(repo_id))
        return col.count() > 0
    except Exception:
        return False
