from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from app.core.config import settings


class OpenAlexService:
    BASE_URL = "https://api.openalex.org/works"

    async def lookup(self, doi: str = "", title: str = "") -> Dict[str, str]:
        try:
            params = {"mailto": settings.ACADEMIC_USER_AGENT.split("mailto:")[-1].strip(")")}
            url = self._doi_url(doi) if doi else self.BASE_URL
            if not doi:
                if not title:
                    return {}
                params["search"] = title
                params["per-page"] = 1

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()

            work = payload if doi else (payload.get("results") or [{}])[0]
            return self._extract_locations(work)
        except Exception as e:
            print(f"OpenAlex lookup failed for DOI={doi!r}, title={title!r}: {e}")
            return {}

    def _doi_url(self, doi: str) -> str:
        return f"{self.BASE_URL}/doi:{quote(doi.strip())}"

    @staticmethod
    def _extract_locations(work: Dict[str, Any]) -> Dict[str, str]:
        best_oa = work.get("best_oa_location") or {}
        primary = work.get("primary_location") or {}
        landing = best_oa.get("landing_page_url") or primary.get("landing_page_url") or work.get("doi") or ""
        pdf = best_oa.get("pdf_url") or ""

        if not pdf:
            for location in work.get("locations") or []:
                if location.get("pdf_url"):
                    pdf = location.get("pdf_url") or ""
                    landing = landing or location.get("landing_page_url") or ""
                    break

        return {
            "openalex_pdf_url": pdf,
            "openalex_landing_url": landing,
        }


openalex_service = OpenAlexService()
