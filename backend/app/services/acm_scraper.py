import asyncio
from typing import Any, Dict, List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings


class ACMScraper:
    SEARCH_URL = "https://dl.acm.org/action/doSearch?AllField={query}"

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
        for item in soup.select(".issue-item-container, .search__item")[:max_results]:
            link = item.select_one(".issue-item__title a, h5 a")
            if not link:
                continue
            papers.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "authors": [
                        author.get_text(" ", strip=True)
                        for author in item.select(".loa__author-name, .author-name")
                    ],
                    "abstract": self._text(item.select_one(".issue-item__abstract, .abstractSection")),
                    "source": "ACM",
                    "published_date": self._text(item.select_one(".bookPubDate, .issue-item__detail")),
                    "pdf_url": "",
                    "paper_url": urljoin("https://dl.acm.org", link.get("href", "")),
                    "citation_count": 0,
                }
            )
        return papers

    @staticmethod
    def _text(element: Any) -> str:
        return element.get_text(" ", strip=True) if element else ""


acm_scraper = ACMScraper()
