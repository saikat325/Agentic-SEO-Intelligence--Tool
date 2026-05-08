import re
from typing import List, Dict, Any
from core.config import get_settings

settings = get_settings()


def extract_symbols(content: str, extension: str) -> List[Dict[str, Any]]:
    """Extract function/class definitions with their line numbers."""
    symbols = []
    lines = content.splitlines()

    patterns = {
        "python": [
            (r"^\s*(async\s+)?def\s+(\w+)\s*\(", "function"),
            (r"^\s*class\s+(\w+)\s*[\(:]", "class"),
        ],
        "javascript": [
            (r"^\s*(export\s+)?(async\s+)?function\s+(\w+)\s*\(", "function"),
            (r"^\s*(export\s+)?(default\s+)?class\s+(\w+)", "class"),
            (r"^\s*(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?\(", "arrow_function"),
            (r"^\s*(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?function", "arrow_function"),
        ],
        "java": [
            (r"^\s*(public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(", "method"),
            (r"^\s*(public|abstract|final|static|\s)*class\s+(\w+)", "class"),
            (r"^\s*(public|private)?(\s+static)?\s+interface\s+(\w+)", "interface"),
        ],
        "go": [
            (r"^func\s+(\w+)\s*\(", "function"),
            (r"^type\s+(\w+)\s+struct", "struct"),
        ],
        "rust": [
            (r"^\s*(pub\s+)?fn\s+(\w+)\s*\(", "function"),
            (r"^\s*(pub\s+)?struct\s+(\w+)", "struct"),
        ],
        "ruby": [
            (r"^\s*def\s+(\w+)", "method"),
            (r"^\s*class\s+(\w+)", "class"),
        ],
    }

    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "javascript",
        ".jsx": "javascript", ".tsx": "javascript", ".java": "java",
        ".go": "go", ".rs": "rust", ".rb": "ruby",
    }

    lang = ext_map.get(extension, "")
    lang_patterns = patterns.get(lang, [])

    for i, line in enumerate(lines):
        for pattern, sym_type in lang_patterns:
            m = re.search(pattern, line)
            if m:
                name = m.group(m.lastindex) if m.lastindex else m.group(1)
                symbols.append({
                    "name": name,
                    "type": sym_type,
                    "line": i + 1,
                    "snippet": line.strip(),
                })
                break

    return symbols


def chunk_file(file_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Split a file into overlapping chunks with metadata."""
    content = file_data["content"]
    path = file_data["path"]
    ext = file_data["extension"]
    lines = file_data["lines"]

    symbols = extract_symbols(content, ext)
    chunks = []

    chunk_size = settings.chunk_size
    overlap = settings.chunk_overlap

    # Symbol-aware chunking: anchor each chunk to a symbol boundary if possible
    if symbols:
        for idx, sym in enumerate(symbols):
            start_line = sym["line"] - 1  # 0-indexed
            # find end: next symbol start or +chunk_size lines
            if idx + 1 < len(symbols):
                end_line = min(symbols[idx + 1]["line"] - 1, start_line + chunk_size)
            else:
                end_line = min(start_line + chunk_size, len(lines))

            chunk_lines = lines[start_line:end_line]
            chunk_text = "\n".join(chunk_lines)

            if len(chunk_text.strip()) < 20:
                continue

            chunks.append({
                "text": chunk_text,
                "file_path": path,
                "start_line": start_line + 1,
                "end_line": end_line,
                "symbol_name": sym["name"],
                "symbol_type": sym["type"],
                "language": ext,
                "chunk_id": f"{path}::{sym['name']}::{start_line+1}",
            })
    
    # Fallback: sliding window for files without detected symbols
    if not chunks:
        total = len(lines)
        start = 0
        while start < total:
            end = min(start + chunk_size, total)
            chunk_text = "\n".join(lines[start:end])
            if len(chunk_text.strip()) >= 20:
                chunks.append({
                    "text": chunk_text,
                    "file_path": path,
                    "start_line": start + 1,
                    "end_line": end,
                    "symbol_name": None,
                    "symbol_type": None,
                    "language": ext,
                    "chunk_id": f"{path}::chunk::{start+1}",
                })
            start += chunk_size - overlap

    return chunks
