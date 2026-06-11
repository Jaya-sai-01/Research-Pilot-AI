from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class WorkspaceOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class WorkspaceStats(BaseModel):
    paper_count: int = 0
    uploaded_pdf_count: int = 0
    report_count: int = 0
    chat_count: int = 0
    vectorized_document_count: int = 0
    vector_chunk_count: int = 0
    last_activity_at: Optional[datetime] = None

class WorkspaceSummary(WorkspaceOut):
    stats: WorkspaceStats

class DashboardAnalytics(BaseModel):
    total_workspaces: int
    total_papers: int
    total_uploaded_pdfs: int
    total_ai_reports: int
    total_research_chats: int
    total_vectorized_documents: int
    total_vector_chunks: int

class ActivityEvent(BaseModel):
    id: str
    workspace_id: int
    workspace_name: str
    type: str
    title: str
    detail: str
    timestamp: datetime

class WorkspaceSummaryResponse(BaseModel):
    analytics: DashboardAnalytics
    workspaces: List[WorkspaceSummary]
    recent_activity: List[ActivityEvent]
