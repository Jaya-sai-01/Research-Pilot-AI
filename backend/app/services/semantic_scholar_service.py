from typing import Any, Dict, List

import httpx

from app.core.config import settings


class SemanticScholarService:
    API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        headers = {}
        if settings.SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY
        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,abstract,year,publicationDate,url,openAccessPdf,citationCount,externalIds,venue,journal,publicationVenue",
        }
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(self.API_URL, params=params, headers=headers)
            response.raise_for_status()

        return [
            {
                "title": item.get("title") or "",
                "doi": (item.get("externalIds") or {}).get("DOI") or "",
                "authors": [
                    author.get("name", "")
                    for author in item.get("authors") or []
                    if author.get("name")
                ],
                "abstract": item.get("abstract") or "",
                "source": "Semantic Scholar",
                "published_date": item.get("publicationDate") or str(item.get("year") or ""),
                "pdf_url": (item.get("openAccessPdf") or {}).get("url") or "",
                "paper_url": item.get("url") or "",
                "citation_count": item.get("citationCount") or 0,
                "publisher": ((item.get("publicationVenue") or {}).get("publisher") or ""),
                "journal": ((item.get("journal") or {}).get("name") or ""),
                "venue": item.get("venue") or ((item.get("publicationVenue") or {}).get("name") or ""),
            }
            for item in response.json().get("data", [])
        ]


semantic_scholar_service = SemanticScholarService()
