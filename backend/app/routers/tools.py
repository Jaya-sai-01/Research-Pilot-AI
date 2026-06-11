import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Any

from app.core.database import get_db
from app.core.config import settings
from app.routers.auth import get_current_user
from app.routers.papers import check_workspace_access
from app.models.user import User
from app.models.paper import Paper
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.services.llm_service import AllProvidersUnavailableError, llm_service
from app.services.vector_service import vector_service

router = APIRouter(prefix="/tools", tags=["tools"])
VISIBLE_REPORT_TYPES = ("summary", "insights", "lit_review", "comparison", "review")

# Request Schemas
class SinglePaperRequest(BaseModel):
    paper_id: int
    workspace_id: int

class MultiPaperRequest(BaseModel):
    paper_ids: List[int]
    workspace_id: int

class SemanticSearchRequest(BaseModel):
    query: str

class BulkDeleteDocumentsRequest(BaseModel):
    document_ids: List[int] | None = None
    delete_all: bool = False

def delete_report_file_if_present(doc: Document) -> None:
    file_path = getattr(doc, "file_path", None)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete report file {file_path}: {e}")

def report_query(report_type: str) -> str:
    queries = {
        "summary": "objective methodology dataset model architecture evaluation metrics results conclusion contributions limitations future work",
        "insights": "key findings trends strengths weaknesses limitations practical implications results evidence",
        "lit_review": "themes research consensus agreement contradiction methodology results limitations future directions",
        "comparison": "objective dataset methodology model architecture evaluation metrics results limitations future work novelty reliability scalability",
        "review": "abstract problem statement literature review methodology experimental design results conclusion future work references citations novelty structure academic writing",
    }
    return queries.get(report_type, queries["summary"])


def paper_payload(paper: Paper, workspace_id: int, query: str = "", evidence_pack: dict | None = None) -> dict:
    if evidence_pack is None:
        evidence_pack = vector_service.build_evidence_pack(
            paper_id=paper.id,
            workspace_id=workspace_id,
            title=paper.title,
            query=query or report_query("summary"),
            limit=10,
        )
    indexed_chunks = [chunk.get("content", "") for chunk in evidence_pack.get("chunks", [])]
    indexed_content = evidence_pack.get("text") or "\n\n".join(indexed_chunks).strip()
    if paper.file_path and paper.text_content:
        source_priority = "Full PDF text"
    elif indexed_content:
        source_priority = "Full PDF text chunks"
    elif paper.abstract:
        source_priority = "Abstract"
    else:
        source_priority = "Metadata"
    chunk_count_used = len(indexed_chunks)
    if chunk_count_used == 0 and (paper.text_content or paper.abstract):
        chunk_count_used = 1
    if chunk_count_used >= 6 or (paper.file_path and paper.text_content):
        evidence_confidence = "High"
    elif chunk_count_used >= 2:
        evidence_confidence = "Medium"
    elif chunk_count_used == 1:
        evidence_confidence = "Low"
    else:
        evidence_confidence = "Low"
    return {
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "text_content": indexed_content or paper.text_content or paper.abstract or "",
        "evidence_chunks": evidence_pack.get("chunks", []),
        "evidence_avg_score": evidence_pack.get("avg_score", 0),
        "source_priority": source_priority,
        "chunk_count_used": chunk_count_used,
        "evidence_confidence": evidence_confidence,
        "has_full_text": bool(paper.file_path and paper.text_content),
        "published_date": paper.published_date,
        "doi": paper.doi,
        "doi_url": paper.doi_url,
        "source": paper.source,
    }

def provider_failure_http_exception(error: AllProvidersUnavailableError) -> HTTPException:
    if settings.AI_TOOLS_GROQ_ONLY:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq service unavailable. Please try again later.",
        )

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "Unable to generate a grounded report because all configured AI providers failed.",
            "provider_failures": error.failures,
            "fallback_order": ["Groq", "Gemini", "OpenRouter", "Ollama"],
        },
    )

@router.post("/summarize", response_model=DocumentOut)
def summarize_paper(
    req: SinglePaperRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(req.workspace_id, current_user.id, db)
    
    paper = db.query(Paper).filter(
        Paper.id == req.paper_id,
        Paper.workspace_id == req.workspace_id
    ).first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found in workspace")
        
    evidence_pack = vector_service.build_summary_evidence_pack(
        paper_id=paper.id,
        workspace_id=req.workspace_id,
        title=paper.title,
    )
    payload = paper_payload(paper, req.workspace_id, report_query("summary"), evidence_pack=evidence_pack)
    try:
        summary_content = llm_service.generate_summary(
            title=paper.title,
            abstract=paper.abstract,
            full_text=payload["text_content"]
        )
    except AllProvidersUnavailableError as exc:
        raise provider_failure_http_exception(exc)
    
    doc = Document(
        title=f"Summary - {paper.title}",
        doc_type="summary",
        content=summary_content,
        workspace_id=req.workspace_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@router.post("/insights", response_model=DocumentOut)
def get_insights(
    req: SinglePaperRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(req.workspace_id, current_user.id, db)
    
    paper = db.query(Paper).filter(
        Paper.id == req.paper_id,
        Paper.workspace_id == req.workspace_id
    ).first()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found in workspace")
        
    payload = paper_payload(paper, req.workspace_id, report_query("insights"))
    try:
        insights_content = llm_service.generate_insights(
            title=paper.title,
            abstract=paper.abstract,
            full_text=payload["text_content"]
        )
    except AllProvidersUnavailableError as exc:
        raise provider_failure_http_exception(exc)
    
    doc = Document(
        title=f"Insights - {paper.title}",
        doc_type="insights",
        content=insights_content,
        workspace_id=req.workspace_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@router.post("/review", response_model=DocumentOut)
def review_research_paper(
    req: SinglePaperRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(req.workspace_id, current_user.id, db)

    paper = db.query(Paper).filter(
        Paper.id == req.paper_id,
        Paper.workspace_id == req.workspace_id
    ).first()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found in workspace")

    if not paper.file_path or not (paper.text_content or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Research Paper Reviewer requires an uploaded PDF with extracted text.",
        )

    try:
        review_content = llm_service.review_research_paper(
            title=paper.title,
            full_text=paper.text_content,
        )
    except AllProvidersUnavailableError as exc:
        raise provider_failure_http_exception(exc)

    doc = Document(
        title=f"Research Paper Review - {paper.title}",
        doc_type="review",
        content=review_content,
        workspace_id=req.workspace_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@router.post("/lit-review", response_model=DocumentOut)
def generate_literature_review(
    req: MultiPaperRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(req.workspace_id, current_user.id, db)
    
    if len(set(req.paper_ids)) < 2:
        raise HTTPException(status_code=400, detail="Select at least two papers for a literature review")
        
    papers = db.query(Paper).filter(
        Paper.id.in_(req.paper_ids),
        Paper.workspace_id == req.workspace_id
    ).all()
    
    if len(papers) != len(req.paper_ids):
        raise HTTPException(status_code=404, detail="One or more papers not found in workspace")
        
    papers_data = [paper_payload(p, req.workspace_id, report_query("lit_review")) for p in papers]
    
    try:
        review_content = llm_service.generate_literature_review(papers_data)
    except AllProvidersUnavailableError as exc:
        raise provider_failure_http_exception(exc)
    
    doc = Document(
        title="Literature Review Report",
        doc_type="lit_review",
        content=review_content,
        workspace_id=req.workspace_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@router.post("/compare", response_model=DocumentOut)
def compare_papers(
    req: MultiPaperRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(req.workspace_id, current_user.id, db)
    
    if len(set(req.paper_ids)) < 2:
        raise HTTPException(status_code=400, detail="Select at least two papers for comparison")
        
    papers = db.query(Paper).filter(
        Paper.id.in_(req.paper_ids),
        Paper.workspace_id == req.workspace_id
    ).all()
    
    if len(papers) != len(req.paper_ids):
        raise HTTPException(status_code=404, detail="One or more papers not found in workspace")
        
    papers_data = [paper_payload(p, req.workspace_id, report_query("comparison")) for p in papers]
    
    try:
        compare_content = llm_service.compare_papers(papers_data)
    except AllProvidersUnavailableError as exc:
        raise provider_failure_http_exception(exc)
    
    doc = Document(
        title="Paper Comparison Matrix Report",
        doc_type="comparison",
        content=compare_content,
        workspace_id=req.workspace_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@router.get("/workspace/{workspace_id}/documents", response_model=List[DocumentOut])
def list_documents(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(workspace_id, current_user.id, db)
    return db.query(Document).filter(
        Document.workspace_id == workspace_id,
        Document.doc_type.in_(VISIBLE_REPORT_TYPES),
    ).all()

@router.delete("/workspace/{workspace_id}/documents/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    workspace_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_workspace_access(workspace_id, current_user.id, db)
    
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.workspace_id == workspace_id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_report_file_if_present(doc)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}

@router.post("/workspace/{workspace_id}/documents/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_documents(
    workspace_id: int,
    req: BulkDeleteDocumentsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_workspace_access(workspace_id, current_user.id, db)

    query = db.query(Document).filter(
        Document.workspace_id == workspace_id,
        Document.doc_type.in_(VISIBLE_REPORT_TYPES),
    )
    if not req.delete_all:
        document_ids = list(set(req.document_ids or []))
        if not document_ids:
            raise HTTPException(status_code=400, detail="Select at least one report to delete")
        query = query.filter(Document.id.in_(document_ids))

    docs = query.all()
    deleted_count = len(docs)
    for doc in docs:
        delete_report_file_if_present(doc)
        db.delete(doc)

    db.commit()
    return {"message": "Reports deleted successfully", "deleted_count": deleted_count}

@router.post("/workspace/{workspace_id}/documents/search")
def semantic_search(
    workspace_id: int,
    req: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_workspace_access(workspace_id, current_user.id, db)
    
    # Run query against vector database
    results = vector_service.search_workspace(workspace_id=workspace_id, query=req.query, top_k=8)
    return results
