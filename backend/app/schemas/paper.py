from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List, Optional, Union


class DiscoveredPaper(BaseModel):
    title: str
    doi: str = ""
    authors: List[str] = Field(default_factory=list)
    abstract: str = ""
    source: str
    published_date: str = ""
    publication_year: str = ""
    pdf_url: str = ""
    paper_url: str = ""
    url: str = ""
    publisher_url: str = ""
    source_url: str = ""
    doi_url: str = ""
    ieee_url: str = ""
    preferred_access_url: str = ""
    preferred_access_type: str = ""
    open_url: str = ""
    retrieved_via: str = ""
    access_type: str = ""
    citation_count: int = 0
    publisher: str = ""
    journal: str = ""
    venue: str = ""


class PaperSearchResponse(BaseModel):
    papers: List[DiscoveredPaper]

class PaperImport(BaseModel):
    title: str
    authors: Optional[Union[str, List[str]]] = None
    abstract: Optional[str] = None
    published_date: Optional[str] = None
    pdf_url: Optional[str] = None
    paper_url: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    doi_url: Optional[str] = None
    source_url: Optional[str] = None
    publisher_url: Optional[str] = None
    ieee_url: Optional[str] = None
    preferred_access_url: Optional[str] = None
    preferred_access_type: Optional[str] = None
    open_url: Optional[str] = None
    access_type: Optional[str] = None
    source: Optional[str] = None
    citation_count: int = 0

    @field_validator("authors")
    @classmethod
    def normalize_authors(cls, value: Optional[Union[str, List[str]]]) -> Optional[str]:
        if isinstance(value, list):
            return ", ".join(author for author in value if author)
        return value

class PaperOut(BaseModel):
    id: int
    title: str
    authors: Optional[str] = None
    abstract: Optional[str] = None
    published_date: Optional[str] = None
    source: Optional[str] = None
    doi: Optional[str] = None
    doi_url: Optional[str] = None
    pdf_url: Optional[str] = None
    source_url: Optional[str] = None
    publisher_url: Optional[str] = None
    ieee_url: Optional[str] = None
    preferred_access_url: Optional[str] = None
    preferred_access_type: Optional[str] = None
    file_path: Optional[str] = None
    indexed_status: bool
    workspace_id: int
    created_at: datetime

    class Config:
        from_attributes = True
