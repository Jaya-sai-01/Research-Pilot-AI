import asyncio
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import settings


class ConferenceScraper:
    SOURCES = {
        "NeurIPS": settings.NEURIPS_PAPERS_URL,
        "ICML": settings.ICML_PAPERS_URL,
        "ICLR": settings.ICLR_PAPERS_URL,
    }

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        tasks = [
            asyncio.to_thread(self._search_page, source, url, query, max_results)
            for source, url in self.SOURCES.items()
            if url
        ]
        if not tasks:
            return []
        groups = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            paper
            for group in groups
            if isinstance(group, list)
            for paper in group
        ]

    def _search_page(
        self, source: str, url: str, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        response = requests.get(
            url,
            headers={"User-Agent": settings.ACADEMIC_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        papers = []
        selectors = "li, article, .paper, .paper-card, .maincard, .proceedingsarticle"
        for item in soup.select(selectors):
            link = item.select_one("a[href]")
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            item_text = item.get_text(" ", strip=True)
            if not title or not any(term in item_text.lower() for term in query_terms):
                continue
            papers.append(
                {
                    "title": title,
                    "authors": self._extract_authors(item),
                    "abstract": "",
                    "source": source,
                    "published_date": "",
                    "pdf_url": "",
                    "paper_url": urljoin(url, link.get("href", "")),
                    "citation_count": 0,
                }
            )
            if len(papers) >= max_results:
                break
        return papers

    @staticmethod
    def _extract_authors(item: Any) -> List[str]:
        element = item.select_one(".authors, .author, .maincardFooter")
        if not element:
            return []
        text = element.get_text(" ", strip=True)
        return [name.strip() for name in text.replace(" and ", ",").split(",") if name.strip()]


conference_scraper = ConferenceScraper()
