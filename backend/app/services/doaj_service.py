from typing import Any, Dict, List
from urllib.parse import quote

import httpx


class DoajService:
    API_URL = "https://doaj.org/api/search/articles/{query}"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        params = {"pageSize": max_results}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(self.API_URL.format(query=quote(query)), params=params)
            response.raise_for_status()

        papers = []
        for item in response.json().get("results", []):
            bibjson = item.get("bibjson") or {}
            identifiers = bibjson.get("identifier") or []
            doi = next(
                (identifier.get("id", "") for identifier in identifiers if identifier.get("type") == "doi"),
                "",
            )
            links = bibjson.get("link") or []
            pdf_url = next((link.get("url", "") for link in links if link.get("type") == "fulltext"), "")
            papers.append(
                {
                    "title": bibjson.get("title") or "",
                    "doi": doi,
                    "authors": [author.get("name", "") for author in bibjson.get("author") or [] if author.get("name")],
                    "abstract": bibjson.get("abstract") or "",
                    "source": "DOAJ",
                    "published_date": str(bibjson.get("year") or ""),
                    "pdf_url": pdf_url,
                    "paper_url": pdf_url,
                    "citation_count": 0,
                    "publisher": bibjson.get("publisher") or "",
                    "journal": (bibjson.get("journal") or {}).get("title", ""),
                    "venue": (bibjson.get("journal") or {}).get("title", ""),
                }
            )
        return papers


doaj_service = DoajService()
