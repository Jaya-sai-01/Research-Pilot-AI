import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Any

from app.core.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.paper import Paper
from app.models.document import Document
from app.models.chat import ChatMessage, ChatSession
from app.schemas.workspace import (
    ActivityEvent,
    DashboardAnalytics,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceStats,
    WorkspaceSummary,
    WorkspaceSummaryResponse,
    WorkspaceUpdate,
)
from app.services.vector_service import vector_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
VISIBLE_REPORT_TYPES = ("summary", "insights", "lit_review", "comparison", "review")


def require_workspace(workspace_id: int, user_id: int, db: Session) -> Workspace:
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.user_id == user_id
    ).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or unauthorized access"
        )
    return workspace


def workspace_stats(workspace: Workspace, db: Session) -> WorkspaceStats:
    paper_count = db.query(func.count(Paper.id)).filter(Paper.workspace_id == workspace.id).scalar() or 0
    uploaded_pdf_count = db.query(func.count(Paper.id)).filter(
        Paper.workspace_id == workspace.id,
        Paper.file_path.isnot(None)
    ).scalar() or 0
    report_count = db.query(func.count(Document.id)).filter(
        Document.workspace_id == workspace.id,
        Document.doc_type.in_(VISIBLE_REPORT_TYPES),
    ).scalar() or 0
    chat_count = db.query(func.count(ChatMessage.id)).join(ChatSession).filter(
        ChatSession.workspace_id == workspace.id
    ).scalar() or 0
    vectorized_documents = db.query(func.count(Paper.id)).filter(
        Paper.workspace_id == workspace.id,
        Paper.indexed_status.is_(True)
    ).scalar() or 0

    timestamps = [workspace.created_at]
    for value in (
        db.query(func.max(Paper.created_at)).filter(Paper.workspace_id == workspace.id).scalar(),
        db.query(func.max(Document.created_at)).filter(
            Document.workspace_id == workspace.id,
            Document.doc_type.in_(VISIBLE_REPORT_TYPES),
        ).scalar(),
        db.query(func.max(ChatMessage.timestamp)).join(ChatSession).filter(
            ChatSession.workspace_id == workspace.id
        ).scalar(),
    ):
        if value:
            timestamps.append(value)

    return WorkspaceStats(
        paper_count=paper_count,
        uploaded_pdf_count=uploaded_pdf_count,
        report_count=report_count,
        chat_count=chat_count,
        vectorized_document_count=vectorized_documents,
        vector_chunk_count=vector_service.count_workspace_chunks(workspace.id),
        last_activity_at=max(timestamps) if timestamps else None,
    )


def activity_label(doc_type: str) -> tuple[str, str]:
    labels = {
        "lit_review": ("Literature Review Generated", "AI literature review report"),
        "comparison": ("Paper Comparison Generated", "AI paper comparison report"),
        "summary": ("Paper Summary Generated", "AI paper summary"),
        "insights": ("Insights Generated", "AI insights report"),
        "review": ("Research Paper Review Generated", "AI academic review suggestions"),
    }
    return labels.get(doc_type, ("AI Report Generated", "Generated research report"))


def recent_activity(workspaces: List[Workspace], db: Session) -> List[ActivityEvent]:
    workspace_names = {workspace.id: workspace.name for workspace in workspaces}
    workspace_ids = list(workspace_names.keys())
    events: list[ActivityEvent] = []

    for workspace in workspaces:
        events.append(ActivityEvent(
            id=f"workspace-{workspace.id}",
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            type="Workspace Created",
            title=workspace.name,
            detail="Workspace metadata created",
            timestamp=workspace.created_at,
        ))

    papers = db.query(Paper).filter(Paper.workspace_id.in_(workspace_ids)).all() if workspace_ids else []
    for paper in papers:
        event_type = "PDF Uploaded" if paper.file_path else "Paper Imported"
        events.append(ActivityEvent(
            id=f"paper-{paper.id}",
            workspace_id=paper.workspace_id,
            workspace_name=workspace_names.get(paper.workspace_id, "Workspace"),
            type=event_type,
            title=paper.title,
            detail="Vectorized document" if paper.indexed_status else "Queued for indexing",
            timestamp=paper.created_at,
        ))

    documents = db.query(Document).filter(
        Document.workspace_id.in_(workspace_ids),
        Document.doc_type.in_(VISIBLE_REPORT_TYPES),
    ).all() if workspace_ids else []
    for document in documents:
        event_type, detail = activity_label(document.doc_type)
        events.append(ActivityEvent(
            id=f"document-{document.id}",
            workspace_id=document.workspace_id,
            workspace_name=workspace_names.get(document.workspace_id, "Workspace"),
            type=event_type,
            title=document.title,
            detail=detail,
            timestamp=document.created_at,
        ))

    chats = db.query(ChatMessage, ChatSession).join(ChatSession).filter(
        ChatSession.workspace_id.in_(workspace_ids)
    ).all() if workspace_ids else []
    for chat, chat_session in chats:
        if chat.role != "user":
            continue
        events.append(ActivityEvent(
            id=f"chat-{chat.id}",
            workspace_id=chat_session.workspace_id,
            workspace_name=workspace_names.get(chat_session.workspace_id, "Workspace"),
            type="Research Chat Activity",
            title="Research question asked",
            detail=chat.content[:120],
            timestamp=chat.timestamp,
        ))

    return sorted(events, key=lambda event: event.timestamp, reverse=True)[:12]

@router.get("/", response_model=List[WorkspaceOut])
def get_workspaces(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
) -> Any:
    return db.query(Workspace).filter(Workspace.user_id == current_user.id).all()

@router.get("/summary", response_model=WorkspaceSummaryResponse)
def get_workspace_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    workspaces = db.query(Workspace).filter(Workspace.user_id == current_user.id).all()
    summaries = [
        WorkspaceSummary(
            id=workspace.id,
            name=workspace.name,
            description=workspace.description,
            user_id=workspace.user_id,
            created_at=workspace.created_at,
            stats=workspace_stats(workspace, db),
        )
        for workspace in workspaces
    ]

    analytics = DashboardAnalytics(
        total_workspaces=len(summaries),
        total_papers=sum(item.stats.paper_count for item in summaries),
        total_uploaded_pdfs=sum(item.stats.uploaded_pdf_count for item in summaries),
        total_ai_reports=sum(item.stats.report_count for item in summaries),
        total_research_chats=sum(item.stats.chat_count for item in summaries),
        total_vectorized_documents=sum(item.stats.vectorized_document_count for item in summaries),
        total_vector_chunks=sum(item.stats.vector_chunk_count for item in summaries),
    )
    return WorkspaceSummaryResponse(
        analytics=analytics,
        workspaces=summaries,
        recent_activity=recent_activity(workspaces, db),
    )

@router.post("/", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    workspace_in: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    db_obj = Workspace(
        name=workspace_in.name,
        description=workspace_in.description,
        user_id=current_user.id
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: int,
    workspace_in: WorkspaceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    workspace = require_workspace(workspace_id, current_user.id, db)
    if workspace_in.name is not None:
        if not workspace_in.name.strip():
            raise HTTPException(status_code=400, detail="Workspace name is required")
        workspace.name = workspace_in.name.strip()
    if workspace_in.description is not None:
        workspace.description = workspace_in.description.strip() or None
    db.commit()
    db.refresh(workspace)
    return workspace

@router.post("/{workspace_id}/duplicate", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def duplicate_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    workspace = require_workspace(workspace_id, current_user.id, db)
    duplicate = Workspace(
        name=f"{workspace.name} Copy",
        description=workspace.description,
        user_id=current_user.id,
    )
    db.add(duplicate)
    db.flush()

    papers = db.query(Paper).filter(Paper.workspace_id == workspace.id).all()
    for paper in papers:
        db.add(Paper(
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            published_date=paper.published_date,
            pdf_url=paper.pdf_url,
            file_path=None,
            text_content=paper.text_content,
            indexed_status=False,
            workspace_id=duplicate.id,
        ))

    documents = db.query(Document).filter(
        Document.workspace_id == workspace.id,
        Document.doc_type.in_(VISIBLE_REPORT_TYPES),
    ).all()
    for document in documents:
        db.add(Document(
            title=document.title,
            doc_type=document.doc_type,
            content=document.content,
            workspace_id=duplicate.id,
        ))

    db.commit()
    db.refresh(duplicate)
    return duplicate

@router.delete("/{workspace_id}", status_code=status.HTTP_200_OK)
def delete_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    workspace = require_workspace(workspace_id, current_user.id, db)
    papers = db.query(Paper).filter(Paper.workspace_id == workspace.id).all()
    for paper in papers:
        if paper.file_path and os.path.exists(paper.file_path):
            try:
                os.remove(paper.file_path)
            except Exception as e:
                print(f"Failed to delete workspace file {paper.file_path}: {e}")
    vector_service.delete_workspace_embeddings(workspace.id)

    db.delete(workspace)
    db.commit()
    return {"message": "Workspace deleted successfully"}
