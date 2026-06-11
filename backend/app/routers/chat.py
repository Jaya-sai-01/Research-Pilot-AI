from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.paper import Paper
from app.models.user import User
from app.models.workspace import Workspace
from app.routers.auth import get_current_user
from app.routers.papers import check_workspace_access
from app.schemas.chat import ChatExchangeOut, ChatMessageCreate, ChatMessageOut, ChatSessionOut, ChatSessionBrief, ChatSessionRename, ChatSessionPin
from app.services.guard_service import REJECTION_MESSAGE, guard_service
from app.services.llm_service import AllProvidersUnavailableError, llm_service
from app.services.vector_service import vector_service

router = APIRouter(prefix="/chat", tags=["chat"])


import re

def generate_local_title(first_message: str) -> str:
    text = first_message.strip()
    
    # Strip some common patterns
    patterns_to_remove = [
        r"^what\s+(?:are\s+the\s+differences\s+between|is\s+the\s+difference\s+between|are|is|does|do)\s+",
        r"^explain\s+(?:the\s+)?",
        r"^summarize\s+(?:the\s+)?",
        r"^how\s+(?:do|does|can|to)\s+",
        r"^tell\s+me\s+about\s+",
        r"^can\s+you\s+",
        r"^please\s+",
        r"^discuss\s+(?:the\s+)?",
        r"^write\s+a\s+",
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        match = re.match(pattern, cleaned, re.IGNORECASE)
        if match:
            cleaned = cleaned[match.end():]
            break
            
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = text
        
    words = cleaned.split()
    if len(words) > 5:
        title = " ".join(words[:5]) + "..."
    else:
        title = " ".join(words)
        
    title = title.rstrip("?.!,;:")
    if title:
        title = title[0].upper() + title[1:]
        
    if not title:
        title = "New Chat"
        
    if len(title) > 40:
        title = title[:37] + "..."
        
    return title


def generate_assistant_response(
    db: Session,
    workspace_id: int,
    session_id: int,
    query: str,
    user_msg_id: int,
    paper_ids: List[int],
    document_ids: List[int],
) -> str:
    if not guard_service.classify_query(query):
        return REJECTION_MESSAGE

    history_objs = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id,
        ChatMessage.id != user_msg_id,
    ).order_by(ChatMessage.timestamp.asc()).all()
    chat_history = [
        {"role": message.role, "content": message.content}
        for message in history_objs
    ]

    selected_paper_ids = list(dict.fromkeys(paper_ids))[:12]
    selected_document_ids = list(dict.fromkeys(document_ids))[:8]
    if selected_paper_ids:
        chunks, active_papers = selected_paper_context(
            db,
            workspace_id,
            selected_paper_ids,
        )
    elif llm_service.is_comparison_query(query):
        all_paper_ids = [
            paper_id
            for (paper_id,) in db.query(Paper.id).filter(
                Paper.workspace_id == workspace_id
            ).all()
        ]
        chunks, active_papers = selected_paper_context(
            db,
            workspace_id,
            all_paper_ids,
        )
    else:
        chunks = vector_service.search_workspace(
            workspace_id=workspace_id,
            query=query,
            top_k=8,
        )
        active_papers = source_payloads_from_chunks(chunks)

    if selected_document_ids:
        chunks = selected_document_context(
            db,
            workspace_id,
            selected_document_ids,
        ) + chunks

    try:
        response_text = llm_service.generate_rag_response(
            query=query,
            chunks=chunks,
            chat_history=chat_history,
            active_papers=active_papers,
        )
    except AllProvidersUnavailableError as exc:
        db.rollback()
        detail = "AI service unavailable. Please try again later."
        if exc.failures:
            detail = f"{detail} Provider detail: {next(iter(exc.failures.values()))}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
    return response_text


def chat_paper_payload(paper: Paper, chunks: List[str]) -> dict:
    chunk_count_used = len(chunks)
    if chunk_count_used == 0 and (paper.text_content or paper.abstract):
        chunk_count_used = 1
    if chunk_count_used >= 6 or (paper.file_path and paper.text_content):
        evidence_confidence = "High"
    elif chunk_count_used >= 2:
        evidence_confidence = "Medium"
    else:
        evidence_confidence = "Low"
    if paper.file_path and paper.text_content:
        source_priority = "Full PDF text"
    elif chunks:
        source_priority = "Full PDF text chunks"
    elif paper.abstract:
        source_priority = "Abstract"
    else:
        source_priority = "Metadata"
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "text_content": "\n\n".join(chunks).strip() or paper.text_content or paper.abstract or "",
        "source_priority": source_priority,
        "chunk_count_used": chunk_count_used,
        "evidence_confidence": evidence_confidence,
        "has_full_text": bool(paper.file_path and paper.text_content),
    }


def source_payloads_from_chunks(chunks: List[dict]) -> List[dict]:
    by_paper = {}
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        paper_id = metadata.get("paper_id")
        if paper_id is None:
            continue
        title = metadata.get("title", "Unknown Source")
        if paper_id not in by_paper:
            by_paper[paper_id] = {
                "id": paper_id,
                "title": title,
                "source_priority": "Retrieved paper chunks",
                "chunk_count_used": 0,
                "evidence_confidence": "Low",
                "has_full_text": False,
            }
        by_paper[paper_id]["chunk_count_used"] += 1
    for payload in by_paper.values():
        count = payload["chunk_count_used"]
        if count >= 6:
            payload["evidence_confidence"] = "High"
        elif count >= 2:
            payload["evidence_confidence"] = "Medium"
    return list(by_paper.values())


def selected_paper_context(
    db: Session,
    workspace_id: int,
    paper_ids: list[int],
) -> tuple[list[dict], list[dict]]:
    papers = db.query(Paper).filter(
        Paper.workspace_id == workspace_id,
        Paper.id.in_(paper_ids),
    ).all()
    chunks: list[dict] = []
    active_papers: list[dict] = []
    for paper in papers:
        paper_chunks = vector_service.get_paper_chunks(
            paper_id=paper.id,
            workspace_id=workspace_id,
            limit=6,
        )
        if not paper_chunks and (paper.text_content or paper.abstract):
            paper_chunks = [(paper.text_content or paper.abstract or "")[:3500]]
        active_papers.append(chat_paper_payload(paper, paper_chunks))
        for index, content in enumerate(paper_chunks):
            chunks.append({
                "content": content,
                "metadata": {
                    "paper_id": paper.id,
                    "title": paper.title,
                    "chunk_index": index,
                },
                "score": 1.0,
            })
    return chunks, active_papers


def selected_document_context(
    db: Session,
    workspace_id: int,
    document_ids: list[int],
) -> list[dict]:
    documents = db.query(Document).filter(
        Document.workspace_id == workspace_id,
        Document.id.in_(document_ids),
    ).all()
    return [
        {
            "content": document.content[:12000],
            "metadata": {
                "paper_id": None,
                "title": document.title,
                "chunk_index": 0,
                "section": "generated report",
            },
            "score": 1.0,
        }
        for document in documents
    ]


from pydantic import BaseModel, Field

class ChatSessionCreate(BaseModel):
    workspace_id: int
    title: str | None = None
    first_message: str | None = None
    document_ids: list[int] = Field(default_factory=list)
    paper_ids: list[int] = Field(default_factory=list)


# --- New Persistent Chat History APIs ---

@router.get("/workspace/{workspace_id}/sessions", response_model=List[ChatSessionBrief])
def get_workspace_sessions(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    workspace = check_workspace_access(workspace_id, current_user.id, db)
    sessions = db.query(ChatSession).filter(
        ChatSession.workspace_id == workspace.id,
        ChatSession.user_id == current_user.id,
    ).order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc()).all()
    return sessions


@router.post("/session", response_model=Any)
def create_chat_session(
    session_in: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    workspace = check_workspace_access(session_in.workspace_id, current_user.id, db)
    
    title = session_in.title
    if not title and session_in.first_message:
        title = generate_local_title(session_in.first_message)
    if not title:
        title = "New Chat"
        
    session = ChatSession(
        workspace_id=workspace.id,
        user_id=current_user.id,
        title=title,
        is_pinned=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    if session_in.first_message:
        query = session_in.first_message.strip()
        user_msg = ChatMessage(session_id=session.id, role="user", content=query)
        db.add(user_msg)
        db.flush()
        
        response_text = generate_assistant_response(
            db=db,
            workspace_id=workspace.id,
            session_id=session.id,
            query=query,
            user_msg_id=user_msg.id,
            paper_ids=session_in.paper_ids,
            document_ids=session_in.document_ids,
        )
        
        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=response_text,
        )
        db.add(assistant_msg)
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user_msg)
        db.refresh(assistant_msg)
        
        return ChatExchangeOut(
            session_id=session.id,
            messages=[user_msg, assistant_msg],
            updated_at=session.updated_at,
        )
        
    return ChatSessionBrief.from_orm(session)


@router.get("/session/{session_id}/messages", response_model=List[ChatMessageOut])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    check_workspace_access(session.workspace_id, current_user.id, db)
    return session.messages


@router.post("/session/{session_id}/message", response_model=ChatExchangeOut)
def add_chat_message(
    session_id: int,
    message_in: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    workspace = check_workspace_access(session.workspace_id, current_user.id, db)
    query = message_in.content.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Message is required")

    user_msg = ChatMessage(session_id=session.id, role="user", content=query)
    db.add(user_msg)
    db.flush()

    response_text = generate_assistant_response(
        db=db,
        workspace_id=workspace.id,
        session_id=session.id,
        query=query,
        user_msg_id=user_msg.id,
        paper_ids=message_in.paper_ids,
        document_ids=message_in.document_ids,
    )

    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_text,
    )
    db.add(assistant_msg)
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return ChatExchangeOut(
        session_id=session.id,
        messages=[user_msg, assistant_msg],
        updated_at=session.updated_at,
    )


@router.patch("/session/{session_id}/rename", response_model=ChatSessionBrief)
def rename_chat_session(
    session_id: int,
    rename_in: ChatSessionRename,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    check_workspace_access(session.workspace_id, current_user.id, db)
    session.title = rename_in.title.strip()
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


@router.patch("/session/{session_id}/pin", response_model=ChatSessionBrief)
def pin_chat_session(
    session_id: int,
    pin_in: ChatSessionPin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    check_workspace_access(session.workspace_id, current_user.id, db)
    session.is_pinned = pin_in.is_pinned
    db.commit()
    db.refresh(session)
    return session


@router.delete("/session/{session_id}", status_code=status.HTTP_200_OK)
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    check_workspace_access(session.workspace_id, current_user.id, db)
    db.delete(session)
    db.commit()
    return {"message": "Chat session deleted successfully", "session_id": session_id}


# --- Backward Compatibility API Fallbacks ---

@router.get("/workspace/{workspace_id}", response_model=ChatSessionOut)
def get_chat_history(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    workspace = check_workspace_access(workspace_id, current_user.id, db)
    session = db.query(ChatSession).filter(
        ChatSession.workspace_id == workspace.id,
        ChatSession.user_id == current_user.id,
    ).order_by(ChatSession.updated_at.desc()).first()
    
    if session:
        return session
        
    now = datetime.utcnow()
    return ChatSessionOut(
        id=0,
        workspace_id=workspace.id,
        user_id=current_user.id,
        title="New Chat",
        is_pinned=False,
        created_at=now,
        updated_at=now,
        messages=[],
    )


@router.post("/workspace/{workspace_id}", response_model=ChatExchangeOut)
def send_chat_message(
    workspace_id: int,
    message_in: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    workspace = check_workspace_access(workspace_id, current_user.id, db)
    session = db.query(ChatSession).filter(
        ChatSession.workspace_id == workspace.id,
        ChatSession.user_id == current_user.id,
    ).order_by(ChatSession.updated_at.desc()).first()

    query = message_in.content.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Message is required")
        
    if not session:
        title = generate_local_title(query)
        session = ChatSession(
            workspace_id=workspace.id,
            user_id=current_user.id,
            title=title,
            is_pinned=False,
        )
        db.add(session)
        db.flush()

    user_msg = ChatMessage(session_id=session.id, role="user", content=query)
    db.add(user_msg)
    db.flush()

    response_text = generate_assistant_response(
        db=db,
        workspace_id=workspace.id,
        session_id=session.id,
        query=query,
        user_msg_id=user_msg.id,
        paper_ids=message_in.paper_ids,
        document_ids=message_in.document_ids,
    )

    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_text,
    )
    db.add(assistant_msg)
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant_msg)

    return ChatExchangeOut(
        session_id=session.id,
        messages=[user_msg, assistant_msg],
        updated_at=session.updated_at,
    )


@router.delete("/workspace/{workspace_id}", status_code=status.HTTP_200_OK)
def clear_chat_history(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = check_workspace_access(workspace_id, current_user.id, db)
    session = db.query(ChatSession).filter(
        ChatSession.workspace_id == workspace.id,
        ChatSession.user_id == current_user.id,
    ).order_by(ChatSession.updated_at.desc()).first()
    
    if session:
        db.query(ChatMessage).filter(
            ChatMessage.session_id == session.id
        ).delete(synchronize_session=False)
        session.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Chat history cleared successfully", "session_id": session.id}
    
    return {"message": "No chat history to clear", "session_id": 0}
