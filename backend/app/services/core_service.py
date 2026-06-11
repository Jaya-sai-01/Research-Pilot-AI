from typing import Any, Dict, List

import httpx

from app.core.config import settings


class CoreService:
    API_URL = "https://api.core.ac.uk/v3/search/works"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        headers = {}
        api_key = getattr(settings, "CORE_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {"q": query, "limit": max_results}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.post(self.API_URL, json=payload, headers=headers)
            response.raise_for_status()

        papers = []
        for item in response.json().get("results", []):
            download_url = item.get("downloadUrl") or ""
            links = item.get("links") or []
            paper_url = item.get("sourceFulltextUrls", [""])[0] if item.get("sourceFulltextUrls") else ""
            paper_url = paper_url or (links[0].get("url", "") if links and isinstance(links[0], dict) else "")
            papers.append(
                {
                    "title": item.get("title") or "",
                    "doi": item.get("doi") or "",
                    "authors": [author.get("name", "") for author in item.get("authors") or [] if author.get("name")],
                    "abstract": item.get("abstract") or "",
                    "source": "CORE",
                    "published_date": str(item.get("yearPublished") or item.get("publishedDate") or ""),
                    "pdf_url": download_url,
                    "paper_url": paper_url,
                    "citation_count": item.get("citationCount") or 0,
                    "publisher": item.get("publisher") or "",
                    "journal": item.get("journal") or "",
                    "venue": item.get("repositoryDocument", {}).get("repository", {}).get("name", "") if isinstance(item.get("repositoryDocument"), dict) else "",
                }
            )
        return papers


core_service = CoreService()
