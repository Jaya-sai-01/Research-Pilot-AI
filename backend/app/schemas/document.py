from pydantic import BaseModel
from datetime import datetime

class DocumentCreate(BaseModel):
    title: str
    doc_type: str
    content: str
    workspace_id: int

class DocumentOut(BaseModel):
    id: int
    title: str
    doc_type: str
    content: str
    workspace_id: int
    created_at: datetime

    class Config:
        from_attributes = True
