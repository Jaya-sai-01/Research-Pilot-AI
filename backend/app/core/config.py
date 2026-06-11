import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

BACKEND_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    PROJECT_NAME: str = "ResearchPilot AI Agent"
    API_V1_STR: str = "/api/v1"
    
    # Security
    JWT_SECRET: str = Field(default="research_pilot_super_secret_key_1234567890", alias="JWT_SECRET")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # Databases
    DATABASE_URL: str = Field(default="sqlite:///./research_pilot.db", alias="DATABASE_URL")
    CHROMA_DB_PATH: str = Field(default="data/chroma_db", alias="CHROMA_DB_PATH")
    UPLOAD_DIR: str = Field(default="data/uploads", alias="UPLOAD_DIR")
    
    # LLM Settings
    GROQ_API_KEY: str = Field(default="", alias="GROQ_API_KEY")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_API_KEY: str = Field(default="", alias="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    OPENROUTER_API_KEY: str = Field(default="", alias="OPENROUTER_API_KEY")
    OPENROUTER_MODEL: str = Field(default="meta-llama/llama-3.1-8b-instruct:free", alias="OPENROUTER_MODEL")
    OLLAMA_BASE_URL: str = Field(default="", alias="OLLAMA_BASE_URL")
    OLLAMA_MODEL: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    AI_TOOLS_GROQ_ONLY: bool = Field(default=True, alias="AI_TOOLS_GROQ_ONLY")

    # Password recovery email. If SMTP_HOST is empty, OTPs are logged to the backend console.
    SMTP_HOST: str = Field(default="", alias="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, alias="SMTP_PORT")
    SMTP_USERNAME: str = Field(default="", alias="SMTP_USERNAME")
    SMTP_PASSWORD: str = Field(default="", alias="SMTP_PASSWORD")
    SMTP_FROM: str = Field(default="", alias="SMTP_FROM")
    SMTP_FROM_EMAIL: str = Field(default="no-reply@researchpilot.local", alias="SMTP_FROM_EMAIL")
    SMTP_USE_TLS: bool = Field(default=True, alias="SMTP_USE_TLS")

    # Academic discovery
    SEMANTIC_SCHOLAR_API_KEY: str = Field(default="", alias="SEMANTIC_SCHOLAR_API_KEY")
    ACADEMIC_USER_AGENT: str = Field(
        default="ResearchPilot/1.0 (mailto:researchpilot@example.com)",
        alias="ACADEMIC_USER_AGENT",
    )
    NEURIPS_PAPERS_URL: str = Field(
        default="https://proceedings.neurips.cc/paper_files/paper/2025",
        alias="NEURIPS_PAPERS_URL",
    )
    ICML_PAPERS_URL: str = Field(
        default="https://proceedings.mlr.press/v267/",
        alias="ICML_PAPERS_URL",
    )
    ICLR_PAPERS_URL: str = Field(
        default="https://openreview.net/group?id=ICLR.cc/2025/Conference",
        alias="ICLR_PAPERS_URL",
    )
    
    class Config:
        env_file = str(BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)
