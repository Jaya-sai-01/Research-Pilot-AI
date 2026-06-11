from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.paper import Paper
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.papers import check_workspace_access
from app.services.llm_service import AllProvidersUnavailableError, llm_service
from app.services.vector_service import vector_service

router = APIRouter(prefix="/assistant", tags=["assistant"])

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_MESSAGES = 10


class AssistantHistoryMessage(BaseModel):
    role: str
    content: str = Field(default="", max_length=MAX_MESSAGE_CHARS)


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: List[AssistantHistoryMessage] = Field(default_factory=list)


class AssistantSource(BaseModel):
    paper_id: int | None = None
    title: str
    chunk_index: int | None = None
    section: str | None = None


class AssistantChatResponse(BaseModel):
    role: str = "assistant"
    content: str
    grounded: bool
    sources: List[AssistantSource] = []


def _source_payloads(chunks: List[dict]) -> List[dict]:
    seen = set()
    sources = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        key = (metadata.get("paper_id"), metadata.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "paper_id": metadata.get("paper_id"),
            "title": metadata.get("title") or "Unknown Source",
            "chunk_index": metadata.get("chunk_index"),
            "section": metadata.get("section"),
        })
    return sources


def _broad_workspace_chunks(workspace_id: int, db: Session, limit_per_paper: int = 2) -> List[dict]:
    papers = db.query(Paper).filter(Paper.workspace_id == workspace_id).all()
    chunks: list[dict] = []
    for paper in papers[:8]:
        paper_chunks = vector_service.get_paper_chunks(
            paper_id=paper.id,
            workspace_id=workspace_id,
            limit=limit_per_paper,
        )
        if not paper_chunks and (paper.text_content or paper.abstract):
            paper_chunks = [(paper.text_content or paper.abstract or "")[:2200]]
        for index, content in enumerate(paper_chunks):
            chunks.append({
                "content": content[:2600],
                "metadata": {
                    "paper_id": paper.id,
                    "title": paper.title,
                    "chunk_index": index,
                    "section": "body",
                },
                "score": 1.0,
            })
    return chunks[:12]


def _should_use_broad_context(message: str) -> bool:
    normalized = message.lower()
    broad_terms = (
        "summarize my uploaded",
        "summarise my uploaded",
        "all papers",
        "uploaded papers",
        "compare papers",
        "compare selected",
        "literature review",
        "key findings",
    )
    return any(term in normalized for term in broad_terms) or llm_service.is_comparison_query(message)


@router.post("/workspace/{workspace_id}/chat", response_model=AssistantChatResponse)
def chat_with_assistant(
    workspace_id: int,
    req: AssistantChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    check_workspace_access(workspace_id, current_user.id, db)

    message = req.message.strip()[:MAX_MESSAGE_CHARS]
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    if _should_use_broad_context(message):
        chunks = _broad_workspace_chunks(workspace_id, db)
    else:
        chunks = vector_service.search_workspace(workspace_id=workspace_id, query=message, top_k=8)

    history = [
        {"role": item.role, "content": item.content[:MAX_MESSAGE_CHARS]}
        for item in req.history[-MAX_HISTORY_MESSAGES:]
        if item.role in {"user", "assistant"} and item.content.strip()
    ]

    try:
        content = llm_service.generate_assistant_response(
            query=message,
            chunks=chunks,
            chat_history=history,
        )
    except AllProvidersUnavailableError as exc:
        detail = "Groq service unavailable. Please try again later."
        failures = exc.failures or {}
        if failures:
            detail = f"{detail} Provider detail: {next(iter(failures.values()))}"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    return AssistantChatResponse(
        content=content,
        grounded=bool(chunks),
        sources=_source_payloads(chunks),
    )
