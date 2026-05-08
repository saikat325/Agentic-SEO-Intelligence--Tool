from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    embed_model: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "./chroma_db"
    repos_dir: str = "./repos"
    max_file_size_kb: int = 500
    chunk_size: int = 800
    chunk_overlap: int = 150

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
