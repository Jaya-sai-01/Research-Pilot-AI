import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import httpx


class ArxivService:
    API_URL = "https://export.arxiv.org/api/query"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        }
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(self.API_URL, params=params)
            response.raise_for_status()

        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in root.findall("atom:entry", ns):
            links = entry.findall("atom:link", ns)
            paper_url = next(
                (link.get("href", "") for link in links if link.get("rel") == "alternate"),
                "",
            )
            pdf_url = next(
                (
                    link.get("href", "")
                    for link in links
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf"
                ),
                "",
            )
            papers.append(
                {
                    "title": self._text(entry, "atom:title", ns),
                    "authors": [
                        self._text(author, "atom:name", ns)
                        for author in entry.findall("atom:author", ns)
                    ],
                    "abstract": self._text(entry, "atom:summary", ns),
                    "source": "arXiv",
                    "published_date": self._text(entry, "atom:published", ns)[:10],
                    "pdf_url": pdf_url,
                    "paper_url": paper_url,
                    "citation_count": 0,
                }
            )
        return papers

    @staticmethod
    def _text(node: ET.Element, path: str, ns: Dict[str, str]) -> str:
        element = node.find(path, ns)
        if element is None or not element.text:
            return ""
        return " ".join(element.text.split())


arxiv_service = ArxivService()
