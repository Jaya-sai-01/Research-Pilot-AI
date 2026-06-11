import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import httpx


class PubMedService:
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            search_response = await client.get(
                f"{self.BASE_URL}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": max_results,
                },
            )
            search_response.raise_for_status()
            ids = search_response.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            fetch_response = await client.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
            fetch_response.raise_for_status()

        root = ET.fromstring(fetch_response.content)
        papers = []
        for article in root.findall(".//PubmedArticle"):
            pmid = self._joined_text(article.find(".//PMID"))
            title = self._joined_text(article.find(".//ArticleTitle"))
            abstract = " ".join(
                self._joined_text(part)
                for part in article.findall(".//Abstract/AbstractText")
            ).strip()
            authors = []
            for author in article.findall(".//Author"):
                collective = self._joined_text(author.find("CollectiveName"))
                name = " ".join(
                    value
                    for value in (
                        self._joined_text(author.find("ForeName")),
                        self._joined_text(author.find("LastName")),
                    )
                    if value
                )
                if collective or name:
                    authors.append(collective or name)
            date = self._publication_date(article)
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
            papers.append(
                {
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "source": "PubMed",
                    "published_date": date,
                    "pdf_url": "",
                    "paper_url": url,
                    "citation_count": 0,
                }
            )
        return papers

    @staticmethod
    def _joined_text(element: ET.Element | None) -> str:
        return " ".join(element.itertext()).strip() if element is not None else ""

    def _publication_date(self, article: ET.Element) -> str:
        date = article.find(".//ArticleDate") or article.find(".//PubDate")
        if date is None:
            return ""
        year = self._joined_text(date.find("Year"))
        month = self._joined_text(date.find("Month"))
        day = self._joined_text(date.find("Day"))
        return "-".join(part for part in (year, month, day) if part)


pubmed_service = PubMedService()
