import asyncio
from typing import Any, Dict, List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings


class IEEEScraper:
    SEARCH_URL = "https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={query}"

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._search_sync, query, max_results)

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        response = requests.get(
            self.SEARCH_URL.format(query=quote(query)),
            headers={"User-Agent": settings.ACADEMIC_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        papers = []
        for item in soup.select("div.List-results-items, xpl-results-item")[:max_results]:
            link = item.select_one("h2 a, a[href*='/document/']")
            if not link:
                continue
            papers.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "authors": self._authors(item.select_one(".author, .authors")),
                    "abstract": self._text(item.select_one(".description, .abstract")),
                    "source": "IEEE",
                    "published_date": self._text(item.select_one(".publisher-info-container")),
                    "pdf_url": "",
                    "paper_url": urljoin("https://ieeexplore.ieee.org", link.get("href", "")),
                    "citation_count": 0,
                }
            )
        return papers

    @staticmethod
    def _text(element: Any) -> str:
        return element.get_text(" ", strip=True) if element else ""

    def _authors(self, element: Any) -> List[str]:
        text = self._text(element)
        return [name.strip() for name in text.split(";") if name.strip()]


ieee_scraper = IEEEScraper()
