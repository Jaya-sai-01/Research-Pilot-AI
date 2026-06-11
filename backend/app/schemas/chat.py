from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    document_ids: list[int] = Field(default_factory=list)
    paper_ids: list[int] = Field(default_factory=list)


class ChatMessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    title: str | None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut]

    class Config:
        from_attributes = True


class ChatSessionBrief(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    title: str | None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatSessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


class ChatSessionPin(BaseModel):
    is_pinned: bool


class ChatExchangeOut(BaseModel):
    session_id: int
    messages: list[ChatMessageOut]
    updated_at: datetime
