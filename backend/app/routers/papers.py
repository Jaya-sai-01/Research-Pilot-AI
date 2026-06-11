import os
import re
import shutil
import logging
from statistics import median
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
import requests
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from pypdf import PdfReader
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.paper import Paper
from app.schemas.paper import PaperImport, PaperOut, PaperSearchResponse
from app.services.hybrid_search_service import hybrid_search_service
from app.services.vector_service import vector_service

router = APIRouter(prefix="/papers", tags=["papers"])
logger = logging.getLogger(__name__)


class BulkDeletePapersRequest(BaseModel):
    paper_ids: Optional[List[int]] = None
    delete_all: bool = False


class AccessResolutionOut(BaseModel):
    access_url: Optional[str] = None
    access_type: str
    fallback_used: bool = False
    response_status: Optional[int] = None
    message: Optional[str] = None


def normalize_doi(value: Optional[str]) -> str:
    doi = " ".join(str(value or "").strip().split()).lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi)
    return doi.rstrip(".")


def doi_to_url(value: Optional[str]) -> Optional[str]:
    doi = normalize_doi(value)
    return f"https://doi.org/{doi}" if doi else None


def is_http_url(value: Optional[str]) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_ieee_document_url(value: Optional[str]) -> bool:
    parsed = urlparse(value or "")
    return "ieeexplore.ieee.org" in parsed.netloc.lower() and "/document/" in parsed.path.lower()


def is_pdf_url(value: Optional[str]) -> bool:
    parsed = urlparse(value or "")
    return parsed.path.lower().endswith(".pdf") or "pdf" in parsed.path.lower()


def probe_access_url(url: str) -> Optional[int]:
    if not is_http_url(url):
        return None
    try:
        response = requests.head(
            url,
            headers={"User-Agent": settings.ACADEMIC_USER_AGENT},
            timeout=8,
            allow_redirects=True,
        )
        if response.status_code in {405, 403}:
            response = requests.get(
                url,
                headers={"User-Agent": settings.ACADEMIC_USER_AGENT},
                timeout=8,
                allow_redirects=True,
                stream=True,
            )
            response.close()
        return response.status_code
    except Exception as exc:
        logger.warning("Access URL probe failed url=%s error=%s", url, exc)
        return None


def access_type_for_url(url: str, fallback: str = "Publisher Page") -> str:
    if is_pdf_url(url):
        return "Open PDF"
    if "doi.org/" in (url or "").lower():
        return "DOI"
    if is_ieee_document_url(url):
        return "IEEE Page"
    return fallback


def select_preferred_access(metadata: Dict[str, Optional[str]], has_local_pdf: bool = False) -> Dict[str, str]:
    if has_local_pdf:
        return {"preferred_access_url": "", "preferred_access_type": "Local PDF"}

    candidates = (
        ("pdf_url", "Open PDF"),
        ("doi_url", "DOI"),
        ("publisher_url", "Publisher Page"),
        ("source_url", "Publisher Page"),
        ("ieee_url", "IEEE Page"),
    )
    for field, access_type in candidates:
        value = metadata.get(field)
        if is_http_url(value):
            return {"preferred_access_url": value or "", "preferred_access_type": access_type}
    return {"preferred_access_url": "", "preferred_access_type": "Unavailable"}


def log_access_resolution(
    paper_id: int,
    source: Optional[str],
    access_url: Optional[str],
    response_status: Optional[int],
    fallback_used: bool,
) -> None:
    logger.info(
        "paper_access paper_id=%s source=%s access_url=%s response_status=%s fallback_used=%s",
        paper_id,
        source or "Unknown",
        access_url or "",
        response_status,
        fallback_used,
    )


def safe_filename(value: str, fallback: str = "paper") -> str:
    base = os.path.basename(urlparse(value or "").path) or fallback
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not base.lower().endswith(".pdf"):
        base = f"{base or fallback}.pdf"
    return base


def extract_pdf_text(file_path: str) -> str:
    extracted_text = ""
    reader = PdfReader(file_path)
    for i, page in enumerate(reader.pages):
        font_fragments = []

        def collect_font_fragment(text, _cm, _tm, _font_dict, font_size):
            cleaned = " ".join((text or "").split())
            if cleaned:
                font_fragments.append((float(font_size or 0), cleaned))

        text = page.extract_text(visitor_text=collect_font_fragment)
        if text:
            body_sizes = [size for size, fragment in font_fragments if size > 0 and len(fragment) >= 2]
            typical_size = median(body_sizes) if body_sizes else 0
            heading_markers = []
            seen_headings = set()
            for font_size, fragment in font_fragments:
                normalized = fragment.casefold()
                is_large = typical_size > 0 and font_size >= typical_size * 1.25
                is_title_length = 1 <= len(fragment.split()) <= 16 and len(fragment) <= 140
                if is_large and is_title_length and normalized not in seen_headings:
                    seen_headings.add(normalized)
                    heading_markers.append(
                        f'[PDF HEADING font={font_size:.1f}]: {fragment}'
                    )
            marker_text = "\n".join(heading_markers)
            extracted_text += f"\n--- Page {i+1} ---\n{marker_text}\n{text}"
    return extracted_text.strip()


def download_pdf_to_workspace(pdf_url: str, workspace_id: int, user_id: int, title: str) -> Optional[str]:
    if not pdf_url:
        return None

    filename = safe_filename(pdf_url, fallback=title[:80] or "paper")
    file_path = os.path.join(settings.UPLOAD_DIR, f"ws_{workspace_id}_{user_id}_imported_{filename}")

    try:
        with requests.get(
            pdf_url,
            headers={"User-Agent": settings.ACADEMIC_USER_AGENT},
            timeout=20,
            stream=True,
        ) as response:
            response.raise_for_status()
            with open(file_path, "wb") as buffer:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        buffer.write(chunk)

        with open(file_path, "rb") as buffer:
            header = buffer.read(5)
        if header != b"%PDF-":
            os.remove(file_path)
            return None
        return file_path
    except Exception as e:
        print(f"PDF download failed for imported paper '{title}': {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return None

def check_workspace_access(workspace_id: int, user_id: int, db: Session) -> Workspace:
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id,
        Workspace.user_id == user_id
    ).first()
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or unauthorized"
        )
    return workspace


def delete_paper_assets(paper: Paper) -> None:
    if paper.file_path and os.path.exists(paper.file_path):
        try:
            os.remove(paper.file_path)
        except Exception as e:
            print(f"Failed to delete file from disk: {e}")
    vector_service.delete_paper_embeddings(paper.id)

@router.get("/search", response_model=PaperSearchResponse)
async def search_papers(
    q: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 40,
    current_user: User = Depends(get_current_user),
):
    search_query = (q or query or "").strip()
    if not search_query:
        raise HTTPException(status_code=400, detail="Query string is required")
    max_results = max(1, min(max_results, 100))
    papers = await hybrid_search_service.search(search_query, max_results=max_results)
    return {"papers": papers}

@router.post("/workspace/{workspace_id}/import", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
def import_paper(
    workspace_id: int,
    paper_in: PaperImport,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # Verify workspace belongs to user
    check_workspace_access(workspace_id, current_user.id, db)
    
    # Store abstract as text content for RAG since we don't download PDF directly
    metadata_text_content = f"Title: {paper_in.title}\nAuthors: {paper_in.authors or 'Unknown'}\nAbstract: {paper_in.abstract or ''}"
    file_path = None
    text_content = metadata_text_content
    abstract_preview = paper_in.abstract

    if paper_in.pdf_url:
        file_path = download_pdf_to_workspace(
            pdf_url=paper_in.pdf_url,
            workspace_id=workspace_id,
            user_id=current_user.id,
            title=paper_in.title,
        )
        if file_path:
            try:
                extracted_text = extract_pdf_text(file_path)
                if extracted_text:
                    text_content = extracted_text
                    abstract_preview = paper_in.abstract or extracted_text[:1000] + "..."
                else:
                    os.remove(file_path)
                    file_path = None
            except Exception as e:
                print(f"PDF extraction failed for imported paper '{paper_in.title}': {e}")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                file_path = None

    doi = normalize_doi(paper_in.doi)
    doi_url = paper_in.doi_url or doi_to_url(doi)
    source_url = paper_in.source_url or paper_in.url or paper_in.paper_url
    publisher_candidate = paper_in.publisher_url or (None if is_ieee_document_url(source_url) else source_url)
    ieee_url = paper_in.ieee_url or (source_url if is_ieee_document_url(source_url) else None)
    if is_ieee_document_url(publisher_candidate):
        ieee_url = ieee_url or publisher_candidate
        publisher_candidate = None
    publisher_url = publisher_candidate
    access_metadata = {
        "pdf_url": paper_in.pdf_url,
        "doi_url": doi_url,
        "publisher_url": publisher_url,
        "source_url": source_url,
        "ieee_url": ieee_url,
    }
    preferred = select_preferred_access(access_metadata, has_local_pdf=bool(file_path))
    
    db_obj = Paper(
        title=paper_in.title,
        authors=paper_in.authors,
        abstract=abstract_preview,
        published_date=paper_in.published_date,
        source=paper_in.source,
        doi=doi,
        doi_url=doi_url,
        pdf_url=paper_in.pdf_url,
        source_url=source_url,
        publisher_url=publisher_url,
        ieee_url=ieee_url,
        preferred_access_url=preferred["preferred_access_url"],
        preferred_access_type=preferred["preferred_access_type"],
        file_path=file_path,
        text_content=text_content,
        workspace_id=workspace_id,
        indexed_status=False
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    
    # Vectorize the abstract
    success = vector_service.index_paper(
        paper_id=db_obj.id,
        workspace_id=workspace_id,
        title=db_obj.title,
        text=text_content
    )
    
    if success:
        db_obj.indexed_status = True
        db.commit()
        db.refresh(db_obj)
        
    return db_obj

@router.post("/workspace/{workspace_id}/upload", response_model=PaperOut, status_code=status.HTTP_201_CREATED)
def upload_pdf(
    workspace_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    # Verify workspace
    check_workspace_access(workspace_id, current_user.id, db)
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF file uploads are supported."
        )
        
    # File save path
    filename_clean = f"ws_{workspace_id}_{current_user.id}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename_clean)
    
    try:
        # Save file to disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Extract Text from PDF
        extracted_text = extract_pdf_text(file_path)
                
        if not extracted_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to extract text from PDF. It might be scanned or image-only."
            )
            
        # Determine paper title
        paper_title = title if title else file.filename.rsplit(".", 1)[0].replace("_", " ").title()
        
        # Save paper to db
        db_obj = Paper(
            title=paper_title,
            authors="Uploaded Document",
            abstract=extracted_text[:1000] + "...", # Store first 1000 chars as preview
            published_date="N/A",
            source="Local Upload",
            preferred_access_type="Local PDF",
            file_path=file_path,
            text_content=extracted_text,
            workspace_id=workspace_id,
            indexed_status=False
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        # Index in ChromaDB
        success = vector_service.index_paper(
            paper_id=db_obj.id,
            workspace_id=workspace_id,
            title=paper_title,
            text=extracted_text
        )
        
        if success:
            db_obj.indexed_status = True
            db.commit()
            db.refresh(db_obj)
            
        return db_obj
        
    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        print(f"Error handling PDF upload: {e}")
        # Clean up file if it exists
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while parsing the PDF: {str(e)}"
        )

@router.get("/workspace/{workspace_id}", response_model=List[PaperOut])
def list_workspace_papers(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    check_workspace_access(workspace_id, current_user.id, db)
    return db.query(Paper).filter(Paper.workspace_id == workspace_id).all()


@router.get("/workspace/{workspace_id}/paper/{paper_id}/access", response_model=AccessResolutionOut)
def resolve_paper_access(
    workspace_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccessResolutionOut:
    check_workspace_access(workspace_id, current_user.id, db)
    paper = db.query(Paper).filter(
        Paper.id == paper_id,
        Paper.workspace_id == workspace_id,
    ).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found in this workspace")

    if paper.file_path and os.path.exists(paper.file_path):
        access_url = f"{settings.API_V1_STR}/papers/workspace/{workspace_id}/paper/{paper_id}/local-pdf"
        log_access_resolution(paper.id, paper.source, access_url, 200, False)
        return AccessResolutionOut(
            access_url=access_url,
            access_type="Local PDF",
            response_status=200,
        )

    candidates = [
        (paper.pdf_url, "Open PDF"),
        (paper.doi_url or doi_to_url(paper.doi), "DOI"),
        (paper.source_url if not is_ieee_document_url(paper.source_url) else None, "Publisher Page"),
        (paper.publisher_url if not is_ieee_document_url(paper.publisher_url) else None, "Publisher Page"),
        (paper.preferred_access_url if not is_ieee_document_url(paper.preferred_access_url) else None, paper.preferred_access_type or "Publisher Page"),
        (paper.ieee_url or (paper.source_url if is_ieee_document_url(paper.source_url) else None), "IEEE Page"),
    ]

    seen = set()
    ordered_candidates = []
    for url, access_type in candidates:
        if not is_http_url(url) or url in seen:
            continue
        seen.add(url)
        ordered_candidates.append((url or "", access_type or access_type_for_url(url or "")))

    fallback_used = False
    for url, access_type in ordered_candidates:
        if is_ieee_document_url(url):
            status_code = probe_access_url(url)
            if status_code == 418:
                log_access_resolution(paper.id, paper.source, url, status_code, True)
                fallback_used = True
                continue
            if status_code and status_code >= 400:
                log_access_resolution(paper.id, paper.source, url, status_code, True)
                fallback_used = True
                continue
            log_access_resolution(paper.id, paper.source, url, status_code, fallback_used)
            return AccessResolutionOut(
                access_url=url,
                access_type="IEEE Page",
                response_status=status_code,
                fallback_used=fallback_used,
            )

        status_code = probe_access_url(url)
        if status_code is None or status_code < 400:
            log_access_resolution(paper.id, paper.source, url, status_code, fallback_used)
            return AccessResolutionOut(
                access_url=url,
                access_type=access_type_for_url(url, access_type),
                response_status=status_code,
                fallback_used=fallback_used,
            )
        fallback_used = True
        log_access_resolution(paper.id, paper.source, url, status_code, True)

    message = "Publisher temporarily unavailable. Please use PDF or DOI access."
    log_access_resolution(paper.id, paper.source, None, None, fallback_used)
    return AccessResolutionOut(
        access_url=None,
        access_type="Unavailable",
        fallback_used=fallback_used,
        message=message,
    )


@router.get("/workspace/{workspace_id}/paper/{paper_id}/local-pdf")
def open_local_pdf(
    workspace_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    check_workspace_access(workspace_id, current_user.id, db)
    paper = db.query(Paper).filter(
        Paper.id == paper_id,
        Paper.workspace_id == workspace_id,
    ).first()
    if not paper or not paper.file_path or not os.path.exists(paper.file_path):
        raise HTTPException(status_code=404, detail="Local PDF not found")

    log_access_resolution(paper.id, paper.source, paper.file_path, 200, False)
    return FileResponse(
        paper.file_path,
        media_type="application/pdf",
        filename=safe_filename(paper.title, fallback=f"paper_{paper.id}"),
    )

@router.post("/workspace/{workspace_id}/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_papers(
    workspace_id: int,
    req: BulkDeletePapersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_workspace_access(workspace_id, current_user.id, db)

    query = db.query(Paper).filter(Paper.workspace_id == workspace_id)
    if not req.delete_all:
        paper_ids = list(set(req.paper_ids or []))
        if not paper_ids:
            raise HTTPException(status_code=400, detail="Select at least one document to delete")
        query = query.filter(Paper.id.in_(paper_ids))

    papers = query.all()
    deleted_count = len(papers)
    for paper in papers:
        delete_paper_assets(paper)
        db.delete(paper)

    db.commit()
    return {"message": "Workspace documents deleted successfully", "deleted_count": deleted_count}

@router.delete("/workspace/{workspace_id}/paper/{paper_id}", status_code=status.HTTP_200_OK)
def delete_paper(
    workspace_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    check_workspace_access(workspace_id, current_user.id, db)
    
    paper = db.query(Paper).filter(
        Paper.id == paper_id,
        Paper.workspace_id == workspace_id
    ).first()
    
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found in this workspace"
        )
        
    delete_paper_assets(paper)
    db.delete(paper)
    db.commit()
    
    return {"message": "Paper deleted successfully"}
