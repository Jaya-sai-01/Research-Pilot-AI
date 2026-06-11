import asyncio
import logging
import math
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List

from app.services.acm_scraper import acm_scraper
from app.services.arxiv_service import arxiv_service
from app.services.conference_scraper import conference_scraper
from app.services.core_service import core_service
from app.services.crossref_service import crossref_service
from app.services.doaj_service import doaj_service
from app.services.ieee_scraper import ieee_scraper
from app.services.openalex_service import openalex_service
from app.services.pubmed_service import pubmed_service
from app.services.semantic_scholar_service import semantic_scholar_service


logger = logging.getLogger(__name__)


class HybridSearchService:
    API_SOURCES = {"arXiv", "PubMed", "Semantic Scholar", "Crossref", "CORE", "DOAJ"}
    SCRAPED_SOURCES = {"IEEE", "ACM", "NeurIPS", "ICML", "ICLR"}
    SOURCE_AUTHORITY = {
        "IEEE": 10,
        "ACM": 9,
        "Springer": 9,
        "Elsevier": 9,
        "Wiley": 8,
        "Taylor & Francis": 8,
        "SAGE": 8,
        "OUP": 8,
        "CUP": 8,
        "AAAI": 8,
        "NeurIPS": 8,
        "ICML": 8,
        "ICLR": 8,
        "PubMed": 8,
        "Semantic Scholar": 8,
        "Crossref": 7,
        "CORE": 7,
        "DOAJ": 7,
        "arXiv": 6,
    }
    SOURCE_PRIORITY = SOURCE_AUTHORITY
    APPROVED_SOURCES = tuple(SOURCE_AUTHORITY.keys())
    DIVERSIFIED_SOURCES = (
        "IEEE",
        "ACM",
        "Springer",
        "Elsevier",
        "PubMed",
        "Semantic Scholar",
        "arXiv",
        "Wiley",
        "Taylor & Francis",
        "SAGE",
        "OUP",
        "CUP",
        "AAAI",
        "NeurIPS",
        "ICML",
        "ICLR",
        "Crossref",
        "CORE",
        "DOAJ",
    )
    LOG_SOURCES = (
        "arXiv",
        "PubMed",
        "Semantic Scholar",
        "Crossref",
        "CORE",
        "DOAJ",
        "IEEE",
        "ACM",
        "Springer",
        "Elsevier",
    )

    async def search(self, query: str, max_results: int = 40) -> List[Dict[str, Any]]:
        per_source = max(3, min(10, math.ceil(max_results / 4)))
        providers = (
            arxiv_service,
            pubmed_service,
            semantic_scholar_service,
            crossref_service,
            core_service,
            doaj_service,
            ieee_scraper,
            acm_scraper,
            conference_scraper,
        )
        groups = await asyncio.gather(
            *(provider.search(query, per_source) for provider in providers),
            return_exceptions=True,
        )
        for provider, group in zip(providers, groups):
            if isinstance(group, Exception):
                logger.warning(
                    "Research discovery provider %s failed for query %r: %s",
                    provider.__class__.__name__,
                    query,
                    group,
                )
        results = [
            self._normalize(paper)
            for group in groups
            if isinstance(group, list)
            for paper in group
            if paper.get("title")
        ]
        results = [paper for paper in results if paper["source"] in self.APPROVED_SOURCES]
        self._log_counts("before deduplication", results)
        deduplicated = self._deduplicate(results)
        deduplicated = await self._enrich_access_urls(deduplicated)
        self._log_counts("after deduplication", deduplicated)
        ranked = sorted(
            deduplicated,
            key=lambda paper: self._rank(paper, query),
            reverse=True,
        )
        diversified = self._diversify(ranked, query, max_results)
        self._log_counts("after ranking", diversified)
        return diversified

    def _normalize(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        authors = paper.get("authors") or []
        if isinstance(authors, str):
            authors = [
                author.strip()
                for author in re.split(r",|;|\band\b", authors)
                if author.strip()
            ]
        normalized = {
            "doi": self._normalize_doi(paper.get("doi") or paper.get("DOI")),
            "publisher": self._clean(paper.get("publisher")),
            "journal": self._clean(paper.get("journal")),
            "venue": self._clean(paper.get("venue")),
        }
        source = self._normalize_source(paper.get("source"), normalized)
        paper_url = paper.get("paper_url") or paper.get("url") or ""
        source_url = paper.get("source_url") or paper_url
        ieee_url = paper.get("ieee_url") or (source_url if self._is_ieee_document_url(source_url) else "")
        publisher_url = paper.get("publisher_url") or ("" if self._is_ieee_document_url(source_url) else paper_url)
        doi_url = paper.get("doi_url") or self._doi_url(normalized["doi"])
        return {
            "title": self._clean(paper.get("title")),
            "authors": [self._clean(author) for author in authors if author],
            "abstract": self._clean(paper.get("abstract")),
            "source": source,
            "published_date": self._clean(paper.get("published_date")),
            "publication_year": self._publication_year(paper.get("published_date")),
            "pdf_url": paper.get("pdf_url") or "",
            "paper_url": paper_url,
            "url": paper.get("url") or paper_url,
            "source_url": source_url,
            "doi_url": doi_url,
            "publisher_url": publisher_url,
            "ieee_url": ieee_url,
            "preferred_access_url": paper.get("preferred_access_url") or "",
            "preferred_access_type": paper.get("preferred_access_type") or "",
            "open_url": paper.get("open_url") or "",
            "retrieved_via": paper.get("retrieved_via") or source,
            "access_type": paper.get("access_type") or "",
            "citation_count": max(0, int(paper.get("citation_count") or 0)),
            **normalized,
        }

    async def _enrich_access_urls(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lookups = await asyncio.gather(
            *(
                openalex_service.lookup(doi=paper.get("doi") or "", title=paper.get("title") or "")
                for paper in papers
            ),
            return_exceptions=True,
        )
        enriched = []
        for paper, lookup in zip(papers, lookups):
            openalex = lookup if isinstance(lookup, dict) else {}
            enriched.append(self._select_access_url(paper, openalex))
        return enriched

    def _select_access_url(self, paper: Dict[str, Any], openalex: Dict[str, str]) -> Dict[str, Any]:
        result = paper.copy()
        source_url = result.get("source_url") or result.get("paper_url") or ""
        ieee_url = result.get("ieee_url") or (source_url if self._is_ieee_document_url(source_url) else "")
        publisher_url = result.get("publisher_url") or ("" if self._is_ieee_document_url(source_url) else source_url)
        doi_url = result.get("doi_url") or self._doi_url(result.get("doi") or "")
        existing_pdf = result.get("pdf_url") or ""
        openalex_pdf = openalex.get("openalex_pdf_url") or ""
        openalex_landing = openalex.get("openalex_landing_url") or ""

        if existing_pdf:
            result["open_url"] = existing_pdf
            result["access_type"] = "Open PDF"
            result["retrieved_via"] = result.get("source") or "Provider"
        elif openalex_pdf:
            result["pdf_url"] = openalex_pdf
            result["open_url"] = openalex_pdf
            result["access_type"] = "Open PDF"
            result["retrieved_via"] = "OpenAlex"
        elif doi_url:
            result["open_url"] = doi_url
            result["access_type"] = "DOI"
            result["retrieved_via"] = "DOI"
        elif openalex_landing:
            publisher_url = publisher_url or openalex_landing
            result["open_url"] = openalex_landing
            result["access_type"] = "Publisher Page"
            result["retrieved_via"] = "OpenAlex"
        elif publisher_url:
            result["open_url"] = publisher_url
            result["access_type"] = "Publisher Page"
            result["retrieved_via"] = result.get("source") or "Publisher"
        elif ieee_url:
            result["open_url"] = ieee_url
            result["access_type"] = "IEEE Page"
            result["retrieved_via"] = "IEEE"
        else:
            result["open_url"] = ""
            result["access_type"] = ""
            result["retrieved_via"] = result.get("source") or "Publisher"

        result["doi_url"] = doi_url
        result["source_url"] = source_url
        result["ieee_url"] = ieee_url
        result["publisher_url"] = publisher_url
        result["preferred_access_url"] = result.get("open_url") or ""
        result["preferred_access_type"] = result.get("access_type") or ""
        return result

    def _deduplicate(self, papers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[str, Dict[str, Any]] = {}
        doi_index: Dict[str, str] = {}
        title_index: Dict[str, str] = {}
        for paper in papers:
            doi_key = paper.get("doi") or ""
            title_key = re.sub(r"[^a-z0-9]", "", paper["title"].lower())
            key = doi_index.get(doi_key) if doi_key else None
            key = key or title_index.get(title_key) if title_key else key
            key = key or (f"doi:{doi_key}" if doi_key else f"title:{title_key}")
            if not doi_key and not title_key:
                continue
            if key not in unique:
                unique[key] = paper
                if doi_key:
                    doi_index[doi_key] = key
                if title_key:
                    title_index[title_key] = key
                continue
            unique[key] = self._merge(unique[key], paper)
            if doi_key:
                doi_index[doi_key] = key
            if title_key:
                title_index[title_key] = key
        return list(unique.values())

    def _merge(self, first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
        preferred = self._best_metadata_record(first, second)
        other = second if preferred is first else first
        source_preferred = self._higher_priority(first["source"], second["source"])
        merged = preferred.copy()
        for field in (
            "doi", "doi_url", "published_date", "publication_year", "pdf_url",
            "paper_url", "url", "source_url", "publisher_url", "ieee_url",
            "preferred_access_url", "preferred_access_type",
            "publisher", "journal", "venue"
        ):
            merged[field] = preferred[field] or other[field]
        merged["authors"] = preferred["authors"] or other["authors"]
        merged["source"] = source_preferred
        merged["citation_count"] = max(first["citation_count"], second["citation_count"])
        return merged

    def _best_metadata_record(self, first: Dict[str, Any], second: Dict[str, Any]) -> Dict[str, Any]:
        first_score = self._metadata_completeness(first) + len(first["abstract"]) / 1000
        second_score = self._metadata_completeness(second) + len(second["abstract"]) / 1000
        return first if first_score >= second_score else second

    def _normalize_source(self, source: Any, metadata: Dict[str, str]) -> str:
        source_name = self._canonical_source(source)
        doi = metadata.get("doi", "")
        metadata_text = " ".join(
            metadata.get(field, "")
            for field in ("publisher", "journal", "venue")
        ).lower()

        detected = self._detect_publisher(doi, metadata_text)
        if detected:
            return detected
        return source_name

    def _canonical_source(self, source: Any) -> str:
        source_text = self._clean(source)
        aliases = {
            "ieee": "IEEE",
            "ieee xplore": "IEEE",
            "acm": "ACM",
            "acm digital library": "ACM",
            "springer": "Springer",
            "springer nature": "Springer",
            "elsevier": "Elsevier",
            "sciencedirect": "Elsevier",
            "science direct": "Elsevier",
            "wiley": "Wiley",
            "taylor & francis": "Taylor & Francis",
            "taylor and francis": "Taylor & Francis",
            "sage": "SAGE",
            "sage publishing": "SAGE",
            "oup": "OUP",
            "oxford university press": "OUP",
            "cup": "CUP",
            "cambridge university press": "CUP",
            "aaai": "AAAI",
            "neurips": "NeurIPS",
            "icml": "ICML",
            "iclr": "ICLR",
            "pubmed": "PubMed",
            "semantic scholar": "Semantic Scholar",
            "crossref": "Crossref",
            "core": "CORE",
            "doaj": "DOAJ",
            "arxiv": "arXiv",
        }
        return aliases.get(source_text.lower(), source_text or "Unknown")

    def _higher_priority(self, first: str, second: str) -> str:
        first_score = self.SOURCE_PRIORITY.get(first, 0)
        second_score = self.SOURCE_PRIORITY.get(second, 0)
        return first if first_score >= second_score else second

    def _detect_publisher(self, doi: str, metadata_text: str) -> str:
        doi_rules = (
            ("IEEE", ("10.1109/",)),
            ("ACM", ("10.1145/",)),
            ("Springer", ("10.1007/", "10.1186/")),
            ("Elsevier", ("10.1016/",)),
            ("Wiley", ("10.1002/", "10.1111/")),
            ("Taylor & Francis", ("10.1080/",)),
            ("SAGE", ("10.1177/",)),
            ("OUP", ("10.1093/",)),
            ("CUP", ("10.1017/",)),
            ("AAAI", ("10.1609/",)),
        )
        for source, prefixes in doi_rules:
            if doi.startswith(prefixes):
                return source

        text_rules = (
            ("IEEE", ("ieee", "institute of electrical and electronics engineers")),
            ("ACM", ("association for computing machinery", "acm digital library")),
            ("Springer", ("springer", "nature portfolio", "springer nature")),
            ("Elsevier", ("elsevier", "sciencedirect", "science direct")),
            ("Wiley", ("wiley",)),
            ("Taylor & Francis", ("taylor & francis", "taylor and francis")),
            ("SAGE", ("sage publishing", "sage journals")),
            ("OUP", ("oxford university press",)),
            ("CUP", ("cambridge university press",)),
            ("AAAI", ("aaai", "association for the advancement of artificial intelligence")),
            ("NeurIPS", ("neurips", "neural information processing systems")),
            ("ICML", ("icml", "international conference on machine learning")),
            ("ICLR", ("iclr", "international conference on learning representations")),
        )
        for source, needles in text_rules:
            if any(self._contains_source_name(metadata_text, needle) for needle in needles):
                return source
        return ""

    @staticmethod
    def _contains_source_name(value: str, needle: str) -> bool:
        if len(needle) <= 5 and needle.isalpha():
            return re.search(rf"\b{re.escape(needle)}\b", value) is not None
        return needle in value

    @staticmethod
    def _normalize_doi(value: Any) -> str:
        doi = " ".join(str(value or "").strip().split()).lower()
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi)
        return doi.rstrip(".")

    @staticmethod
    def _doi_url(value: str) -> str:
        doi = HybridSearchService._normalize_doi(value)
        return f"https://doi.org/{doi}" if doi else ""

    @staticmethod
    def _is_ieee_document_url(value: str) -> bool:
        from urllib.parse import urlparse

        parsed = urlparse(value or "")
        return "ieeexplore.ieee.org" in parsed.netloc.lower() and "/document/" in parsed.path.lower()

    def _rank(self, paper: Dict[str, Any], query: str) -> float:
        terms = {term for term in self._tokens(query) if len(term) > 1}
        title_tokens = set(self._tokens(paper["title"]))
        abstract_tokens = set(self._tokens(paper["abstract"]))
        matched_title_terms = terms & title_tokens
        matched_abstract_terms = terms & abstract_tokens
        normalized_query = self._normalized_text(query)
        normalized_title = self._normalized_text(paper["title"])
        semantic_score = self._semantic_similarity(query, paper)
        title_coverage = len(matched_title_terms) / max(1, len(terms))
        title_jaccard = len(matched_title_terms) / max(1, len(terms | title_tokens))
        title_score = title_coverage * 26 + title_jaccard * 14
        abstract_score = min(len(matched_abstract_terms), 5) * 1.5
        phrase_score = 18 if normalized_query and normalized_query in normalized_title else 0
        exact_title_score = 45 if normalized_query == normalized_title else 0
        citation_score = min(24, math.log1p(paper["citation_count"]) * 3)
        recency_score = self._recency_score(paper["published_date"])
        source_score = self.SOURCE_AUTHORITY.get(paper["source"], 0)
        metadata_score = self._metadata_completeness(paper)
        return (
            exact_title_score
            + title_score
            + semantic_score
            + abstract_score
            + phrase_score
            + citation_score
            + recency_score
            + source_score
            + metadata_score
        )

    def _diversify(
        self,
        ranked: List[Dict[str, Any]],
        query: str,
        max_results: int,
    ) -> List[Dict[str, Any]]:
        if max_results <= 0:
            return []

        top_window_size = min(10, max_results)
        selected: List[Dict[str, Any]] = []
        selected_ids = set()

        def add(paper: Dict[str, Any]) -> bool:
            paper_id = self._paper_identity(paper)
            if paper_id in selected_ids:
                return False
            selected.append(paper)
            selected_ids.add(paper_id)
            return True

        exact_title_matches = [
            paper for paper in ranked if self._is_exact_title_match(paper, query)
        ]
        for paper in exact_title_matches:
            if len(selected) >= top_window_size:
                break
            add(paper)

        source_buckets = {
            source: [
                paper
                for paper in ranked
                if paper["source"] == source
                and self._paper_identity(paper) not in selected_ids
                and self._is_relevant_for_diversity(paper, query)
            ]
            for source in self.DIVERSIFIED_SOURCES
        }

        # Put the strongest relevant candidate from each source into the top window
        # before allowing high-volume sources, especially arXiv, to fill the page.
        for source in self.DIVERSIFIED_SOURCES:
            if len(selected) >= top_window_size:
                break
            if source_buckets[source]:
                add(source_buckets[source][0])

        generic_query = self._is_generic_query(query)
        source_counts = self._source_counts(selected)
        source_cap = 2 if generic_query else 3

        for paper in ranked:
            if len(selected) >= top_window_size:
                break
            source = paper["source"]
            if generic_query and source_counts.get(source, 0) >= source_cap:
                continue
            if add(paper):
                source_counts[source] = source_counts.get(source, 0) + 1

        for paper in ranked:
            if len(selected) >= max_results:
                break
            add(paper)

        return selected[:max_results]

    def _is_relevant_for_diversity(self, paper: Dict[str, Any], query: str) -> bool:
        terms = {term for term in self._tokens(query) if len(term) > 1}
        if not terms:
            return False
        title_tokens = set(self._tokens(paper["title"]))
        abstract_tokens = set(self._tokens(paper["abstract"]))
        return bool(terms & title_tokens) or len(terms & abstract_tokens) >= min(2, len(terms))

    def _is_generic_query(self, query: str) -> bool:
        terms = [term for term in self._tokens(query) if len(term) > 1]
        return len(terms) <= 3

    def _is_exact_title_match(self, paper: Dict[str, Any], query: str) -> bool:
        return self._normalized_text(paper["title"]) == self._normalized_text(query)

    def _paper_identity(self, paper: Dict[str, Any]) -> str:
        doi = paper.get("doi") or ""
        if doi:
            return f"doi:{doi}"
        return f"title:{self._normalized_text(paper['title'])}"

    @staticmethod
    def _source_counts(papers: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for paper in papers:
            source = paper["source"]
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _semantic_similarity(self, query: str, paper: Dict[str, Any]) -> float:
        query_tokens = self._tokens(query)
        haystack_tokens = self._tokens(f"{paper['title']} {paper['abstract']} {paper['venue']} {paper['journal']}")
        if not query_tokens or not haystack_tokens:
            return 0
        query_bigrams = set(zip(query_tokens, query_tokens[1:]))
        haystack_bigrams = set(zip(haystack_tokens, haystack_tokens[1:]))
        unigram_overlap = len(set(query_tokens) & set(haystack_tokens)) / max(1, len(set(query_tokens)))
        bigram_overlap = len(query_bigrams & haystack_bigrams) / max(1, len(query_bigrams))
        return unigram_overlap * 8 + bigram_overlap * 8

    @staticmethod
    def _metadata_completeness(paper: Dict[str, Any]) -> float:
        fields = ("title", "authors", "abstract", "published_date", "doi", "pdf_url", "preferred_access_url", "citation_count")
        return sum(1 for field in fields if paper.get(field)) * 0.75

    @staticmethod
    def _recency_score(value: str) -> float:
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if not match:
            return 0
        age = max(0, datetime.utcnow().year - int(match.group()))
        return max(0, 3 - age * 0.25)

    @staticmethod
    def _publication_year(value: Any) -> str:
        match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
        return match.group() if match else ""

    @staticmethod
    def _tokens(value: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", value.lower())

    @staticmethod
    def _normalized_text(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    def _log_counts(self, stage: str, papers: Iterable[Dict[str, Any]]) -> None:
        counts = self._source_counts(papers)
        formatted = ", ".join(f"{source} count={counts.get(source, 0)}" for source in self.LOG_SOURCES)
        logger.info("Research discovery %s: %s", stage, formatted)

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").split())


hybrid_search_service = HybridSearchService()
