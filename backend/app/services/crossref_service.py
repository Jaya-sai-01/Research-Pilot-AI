from typing import Any, Dict, List

import aiohttp

from app.core.config import settings


class CrossrefService:
    API_URL = "https://api.crossref.org/works"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        headers = {"User-Agent": settings.ACADEMIC_USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=12)
        params = {
            "query": query,
            "rows": max_results,
            "select": "DOI,title,author,abstract,published,URL,is-referenced-by-count,link,publisher,container-title",
        }
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as client:
            async with client.get(self.API_URL, params=params) as response:
                response.raise_for_status()
                payload = await response.json()

        papers = []
        for item in payload.get("message", {}).get("items", []):
            date_parts = (
                (item.get("published") or {}).get("date-parts") or [[]]
            )[0]
            published_date = "-".join(str(part) for part in date_parts)
            links = item.get("link") or []
            pdf_url = next(
                (
                    link.get("URL", "")
                    for link in links
                    if link.get("content-type") == "application/pdf"
                ),
                "",
            )
            papers.append(
                {
                    "title": " ".join(item.get("title") or []),
                    "doi": item.get("DOI") or "",
                    "authors": [
                        " ".join(
                            part
                            for part in (author.get("given", ""), author.get("family", ""))
                            if part
                        )
                        for author in item.get("author") or []
                    ],
                    "abstract": self._strip_tags(item.get("abstract") or ""),
                    "source": "Crossref",
                    "published_date": published_date,
                    "pdf_url": pdf_url,
                    "paper_url": item.get("URL") or "",
                    "citation_count": item.get("is-referenced-by-count") or 0,
                    "publisher": item.get("publisher") or "",
                    "journal": " ".join(item.get("container-title") or []),
                    "venue": " ".join(item.get("container-title") or []),
                }
            )
        return papers

    @staticmethod
    def _strip_tags(value: str) -> str:
        from bs4 import BeautifulSoup

        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


crossref_service = CrossrefService()
