from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    authors = Column(String, nullable=True)
    abstract = Column(Text, nullable=True)
    published_date = Column(String, nullable=True)
    source = Column(String, nullable=True)
    doi = Column(String, nullable=True)
    doi_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    publisher_url = Column(String, nullable=True)
    ieee_url = Column(String, nullable=True)
    preferred_access_url = Column(String, nullable=True)
    preferred_access_type = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    text_content = Column(Text, nullable=True)
    indexed_status = Column(Boolean, default=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="papers")
