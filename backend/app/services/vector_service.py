import os
import re
import hashlib
import numpy as np
from collections import Counter
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings

# Robust Embedding Function Fallback
class SentenceTransformerEmbeddingModel:
    def __init__(self):
        self.model = None
        self.is_mock = False
        self.dimension = 384
        try:
            print("Loading sentence-transformers/all-MiniLM-L6-v2...")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            print("Successfully loaded sentence-transformers model.")
        except Exception as e:
            print(f"Warning: Failed to load sentence-transformers: {e}")
            print("Falling back to deterministic mock embeddings (384-dimensional).")
            self.is_mock = True

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not self.is_mock and self.model:
            try:
                embeddings = self.model.encode(texts)
                return embeddings.tolist()
            except Exception as e:
                print(f"Error encoding with sentence-transformers: {e}. Using fallback.")
        
        # Fallback Mock Embedding (deterministic based on hash of text)
        result = []
        for text in texts:
            # Seed based on text hash
            hash_val = int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16)
            np.random.seed(hash_val % (2**32))
            
            # Generate deterministic unit vector
            vec = np.random.normal(0, 1, self.dimension)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            result.append(vec.tolist())
        return result

    def get_embedding(self, text: str) -> List[float]:
        return self.get_embeddings([text])[0]

# Initialize embedding helper
embedding_model = SentenceTransformerEmbeddingModel()

class VectorService:
    def __init__(self):
        # Initialize ChromaDB Client
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        # Create or get the collection for papers
        self.collection = self.client.get_or_create_collection(
            name="research_papers",
            metadata={"hnsw:space": "cosine"}
        )

    SECTION_PATTERNS = (
        ("abstract", r"\babstract\b"),
        ("introduction", r"\b(introduction|background)\b"),
        ("methodology", r"\b(methodology|method|methods|approach|architecture|model)\b"),
        ("results", r"\b(results|evaluation|experiment|experiments|metrics|findings)\b"),
        ("limitations", r"\b(limitations?|threats to validity|discussion)\b"),
        ("future_work", r"\b(future work|open challenges?|conclusion|conclusions)\b"),
        ("references", r"\b(references|bibliography)\b"),
    )

    EVIDENCE_TERMS = {
        "objective", "dataset", "method", "methodology", "architecture", "model",
        "evaluation", "metrics", "results", "limitations", "future", "benchmark",
        "comparison", "accuracy", "performance", "experiment", "finding",
    }

    SECTION_DISPLAY_NAMES = {
        "abstract": "Abstract",
        "introduction": "Introduction/Background",
        "methodology": "Methodology/Methods/Approach",
        "results": "Results/Evaluation/Experiments",
        "limitations": "Discussion/Limitations",
        "future_work": "Conclusion/Discussion/Future Work",
        "body": "Body",
    }

    def _display_section_name(self, section: str) -> str:
        return self.SECTION_DISPLAY_NAMES.get((section or "body").lower(), section or "Body")

    def _detect_section(self, heading: str, content: str = "") -> str:
        text = f"{heading} {content[:300]}".lower()
        for section, pattern in self.SECTION_PATTERNS:
            if re.search(pattern, text):
                return section
        return "body"

    def _split_section_blocks(self, text: str) -> List[Dict[str, str]]:
        normalized = re.sub(r"\r\n?", "\n", text or "").strip()
        if not normalized:
            return []

        heading_re = re.compile(
            r"(?im)^(?:\s*(?:\d+(?:\.\d+)*\.?\s+)?)"
            r"(abstract|introduction|background|related work|methodology|methods?|approach|"
            r"architecture|model|experiments?|evaluation|results|discussion|limitations?|"
            r"threats to validity|future work|open challenges?|conclusions?|references)\s*$"
        )
        matches = list(heading_re.finditer(normalized))
        if not matches:
            return [{"heading": "body", "section": self._detect_section("", normalized), "content": normalized}]

        blocks = []
        if matches[0].start() > 0:
            prefix = normalized[:matches[0].start()].strip()
            if prefix:
                blocks.append({"heading": "front_matter", "section": "abstract", "content": prefix})

        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            heading = match.group(1).strip()
            content = normalized[start:end].strip()
            if content:
                blocks.append({
                    "heading": heading,
                    "section": self._detect_section(heading, content),
                    "content": content,
                })
        return blocks

    def _paragraph_chunks(self, content: str, chunk_size: int, overlap: int) -> List[str]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        if not paragraphs:
            paragraphs = [content.strip()]

        chunks = []
        current = ""
        for paragraph in paragraphs:
            paragraph = re.sub(r"[ \t]+", " ", paragraph).strip()
            if not paragraph:
                continue
            if len(paragraph) > chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                sentences = re.split(r"(?<=[.!?])\s+", paragraph)
                sentence_buffer = ""
                for sentence in sentences:
                    if len(sentence_buffer) + len(sentence) + 1 <= chunk_size:
                        sentence_buffer = f"{sentence_buffer} {sentence}".strip()
                    else:
                        if sentence_buffer:
                            chunks.append(sentence_buffer)
                        sentence_buffer = sentence
                if sentence_buffer:
                    chunks.append(sentence_buffer)
                continue

            if len(current) + len(paragraph) + 2 <= chunk_size:
                current = f"{current}\n\n{paragraph}".strip()
            else:
                if current:
                    chunks.append(current.strip())
                overlap_text = current[-overlap:].strip() if overlap and current else ""
                current = f"{overlap_text}\n\n{paragraph}".strip() if overlap_text else paragraph
        if current:
            chunks.append(current.strip())
        return chunks

    def chunk_text_with_metadata(self, text: str, chunk_size: int = 850, overlap: int = 160) -> List[Dict[str, Any]]:
        if not text:
            return []

        chunk_records = []
        for block in self._split_section_blocks(text):
            if block["section"] == "references":
                continue
            for chunk in self._paragraph_chunks(block["content"], chunk_size, overlap):
                if len(chunk.strip()) > 80:
                    chunk_records.append({
                        "content": chunk.strip(),
                        "section": block["section"],
                        "heading": block["heading"],
                    })
        return chunk_records

    def chunk_text(self, text: str, chunk_size: int = 850, overlap: int = 160) -> List[str]:
        return [record["content"] for record in self.chunk_text_with_metadata(text, chunk_size, overlap)]

    def index_paper(self, paper_id: int, workspace_id: int, title: str, text: str) -> bool:
        if not text:
            return False
        
        try:
            chunk_records = self.chunk_text_with_metadata(text)
            if not chunk_records:
                return False
            chunks = [record["content"] for record in chunk_records]
            
            # Prepare IDs, embeddings, metadatas, and documents
            ids = [f"paper_{paper_id}_chunk_{i}" for i in range(len(chunks))]
            embeddings = embedding_model.get_embeddings(chunks)
            metadatas = [{
                "paper_id": paper_id,
                "workspace_id": workspace_id,
                "title": title,
                "chunk_index": i,
                "section": chunk_records[i].get("section", "body"),
                "heading": chunk_records[i].get("heading", ""),
            } for i in range(len(chunks))]
            
            # Add to ChromaDB in batches
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=chunks
            )
            return True
        except Exception as e:
            print(f"Error indexing paper {paper_id} in vector DB: {e}")
            return False

    def delete_paper_embeddings(self, paper_id: int):
        try:
            # Delete entries matching paper_id
            self.collection.delete(
                where={"paper_id": paper_id}
            )
            return True
        except Exception as e:
            print(f"Error deleting embeddings for paper {paper_id}: {e}")
            return False

    def delete_workspace_embeddings(self, workspace_id: int):
        try:
            self.collection.delete(where={"workspace_id": workspace_id})
            return True
        except Exception as e:
            print(f"Error deleting embeddings for workspace {workspace_id}: {e}")
            return False

    def count_workspace_chunks(self, workspace_id: int) -> int:
        try:
            results = self.collection.get(where={"workspace_id": workspace_id})
            return len(results.get("ids") or [])
        except Exception as e:
            print(f"Error counting chunks for workspace {workspace_id}: {e}")
            return 0

    def _tokens(self, value: str) -> List[str]:
        return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 1]

    def _keyword_score(self, query: str, document: str, metadata: Dict[str, Any] = None) -> float:
        metadata = metadata or {}
        query_terms = self._tokens(query)
        if not query_terms:
            return 0.0
        doc_terms = self._tokens(document)
        if not doc_terms:
            return 0.0
        doc_counts = Counter(doc_terms)
        doc_len = len(doc_terms)
        score = 0.0
        for term in query_terms:
            tf = doc_counts.get(term, 0)
            if tf:
                score += (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * doc_len / 180))
        phrase = " ".join(query_terms)
        if phrase and phrase in " ".join(doc_terms):
            score += 2.0
        section = (metadata.get("section") or "").lower()
        if section in {"methodology", "results", "limitations", "future_work", "abstract"}:
            score += 0.75
        if any(term in self.EVIDENCE_TERMS for term in set(doc_terms)):
            score += 0.5
        return score

    def _evidence_density(self, document: str, metadata: Dict[str, Any] = None) -> float:
        metadata = metadata or {}
        text = (document or "").lower()
        score = 0.0
        for term in self.EVIDENCE_TERMS:
            if term in text:
                score += 0.12
        if re.search(r"\b\d+(?:\.\d+)?\s*(%|percent|accuracy|f1|auc|ms|s|x)\b", text):
            score += 0.8
        if re.search(r"\b(we|this paper|our|the authors?)\b", text):
            score += 0.3
        section = (metadata.get("section") or "").lower()
        section_boost = {
            "abstract": 0.4,
            "methodology": 0.8,
            "results": 0.9,
            "limitations": 1.0,
            "future_work": 0.9,
        }.get(section, 0.0)
        return score + section_boost

    def rerank_chunks(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        reranked = []
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            dense_score = float(chunk.get("score") or 0.0)
            keyword_score = self._keyword_score(query, chunk.get("content") or "", metadata)
            evidence_score = self._evidence_density(chunk.get("content") or "", metadata)
            final_score = dense_score * 0.45 + keyword_score * 0.35 + evidence_score * 0.20
            enriched = dict(chunk)
            enriched["dense_score"] = dense_score
            enriched["keyword_score"] = keyword_score
            enriched["evidence_score"] = evidence_score
            enriched["score"] = final_score
            reranked.append(enriched)
        reranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        seen = set()
        unique = []
        for item in reranked:
            key = (item.get("metadata", {}).get("paper_id"), item.get("metadata", {}).get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
            if len(unique) >= top_k:
                break
        return unique

    def rerank_chunks_for_sections(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        preferred_sections: List[str],
        section_terms: List[str],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        preferred = {section.lower() for section in preferred_sections}
        term_pattern = re.compile(
            r"\b(" + "|".join(re.escape(term.lower()) for term in section_terms) + r")\b"
        ) if section_terms else None

        section_matched = []
        scored = []
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            section = (metadata.get("section") or "body").lower()
            heading = (metadata.get("heading") or "").lower()
            content = (chunk.get("content") or "").lower()
            matches_section = section in preferred
            matches_terms = bool(term_pattern and (term_pattern.search(heading) or term_pattern.search(content[:500])))
            if matches_section or matches_terms:
                section_matched.append(chunk)

        pool = section_matched or chunks
        for chunk in pool:
            metadata = chunk.get("metadata") or {}
            section = (metadata.get("section") or "body").lower()
            heading = (metadata.get("heading") or "").lower()
            content = (chunk.get("content") or "").lower()
            section_boost = 0.0
            if section in preferred:
                section_boost += 2.5
            if term_pattern and term_pattern.search(heading):
                section_boost += 1.5
            if term_pattern and term_pattern.search(content[:500]):
                section_boost += 0.75
            if section == "abstract" and "abstract" not in preferred:
                section_boost -= 1.75

            enriched = dict(chunk)
            enriched["section_match_score"] = section_boost
            enriched["score"] = float(chunk.get("score") or 0.0) + section_boost
            scored.append(enriched)

        return self.rerank_chunks(query, scored, top_k=top_k)

    def search_workspace(self, workspace_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            query_embedding = embedding_model.get_embedding(query)
            candidate_count = max(top_k * 4, 20)
            
            # Filter query by workspace_id
            dense_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=candidate_count,
                where={"workspace_id": workspace_id}
            )
            
            # Parse results
            parsed_results = []
            if dense_results and 'documents' in dense_results and dense_results['documents']:
                documents = dense_results['documents'][0]
                metadatas = dense_results['metadatas'][0]
                distances = dense_results['distances'][0] if 'distances' in dense_results else [0.0] * len(documents)
                
                for i in range(len(documents)):
                    parsed_results.append({
                        "content": documents[i],
                        "metadata": metadatas[i],
                        "score": 1.0 - distances[i]  # Cosine similarity score
                    })

            all_results = self.collection.get(where={"workspace_id": workspace_id})
            documents = all_results.get("documents") or []
            metadatas = all_results.get("metadatas") or []
            keyword_candidates = []
            for document, metadata in zip(documents, metadatas):
                score = self._keyword_score(query, document, metadata or {})
                if score > 0:
                    keyword_candidates.append({
                        "content": document,
                        "metadata": metadata or {},
                        "score": min(score / 8.0, 1.0),
                    })
            keyword_candidates.sort(key=lambda item: item["score"], reverse=True)
            parsed_results.extend(keyword_candidates[:candidate_count])
            
            return self.rerank_chunks(query, parsed_results, top_k=top_k)
        except Exception as e:
            print(f"Error searching vector DB: {e}")
            return []

    def search_paper(self, paper_id: int, workspace_id: int, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        try:
            all_results = self.collection.get(where={"paper_id": paper_id})
            documents = all_results.get("documents") or []
            metadatas = all_results.get("metadatas") or []
            candidates = []
            query_embedding = embedding_model.get_embedding(query)
            dense_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=max(top_k * 3, 12),
                where={"paper_id": paper_id},
            )
            if dense_results and dense_results.get("documents"):
                for document, metadata, distance in zip(
                    dense_results["documents"][0],
                    dense_results["metadatas"][0],
                    dense_results.get("distances", [[0.0] * len(dense_results["documents"][0])])[0],
                ):
                    if metadata and metadata.get("workspace_id") == workspace_id:
                        candidates.append({"content": document, "metadata": metadata, "score": 1.0 - distance})

            for document, metadata in zip(documents, metadatas):
                if not metadata or metadata.get("workspace_id") != workspace_id:
                    continue
                score = self._keyword_score(query, document, metadata)
                if score > 0:
                    candidates.append({"content": document, "metadata": metadata, "score": min(score / 8.0, 1.0)})
            return self.rerank_chunks(query, candidates, top_k=top_k)
        except Exception as e:
            print(f"Error searching paper {paper_id}: {e}")
            return []

    def build_evidence_pack(
        self,
        paper_id: int,
        workspace_id: int,
        title: str,
        query: str,
        limit: int = 8,
    ) -> Dict[str, Any]:
        chunks = self.search_paper(paper_id=paper_id, workspace_id=workspace_id, query=query, top_k=limit)
        evidence_lines = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = chunk.get("metadata") or {}
            evidence_lines.append(
                f"[P{paper_id}-C{metadata.get('chunk_index', index)} | {title} | "
                f"Section: {self._display_section_name(metadata.get('section', 'body'))} | Score: {chunk.get('score', 0):.2f}]\n"
                f"{chunk.get('content', '')}"
            )
        return {
            "chunks": chunks,
            "text": "\n\n".join(evidence_lines),
            "chunk_count": len(chunks),
            "avg_score": sum(float(chunk.get("score") or 0) for chunk in chunks) / max(1, len(chunks)),
        }

    def build_summary_evidence_pack(
        self,
        paper_id: int,
        workspace_id: int,
        title: str,
        limit_per_section: int = 3,
    ) -> Dict[str, Any]:
        specs = [
            {
                "label": "Objective",
                "query": "research objective problem statement research question goal motivation introduction",
                "sections": ["abstract", "introduction"],
                "terms": ["abstract", "introduction", "background", "objective", "goal", "motivation", "problem statement"],
            },
            {
                "label": "Methodology",
                "query": "methodology methods approach architecture model dataset experimental setup",
                "sections": ["methodology"],
                "terms": ["methodology", "method", "methods", "approach", "architecture", "model", "dataset", "experimental setup"],
            },
            {
                "label": "Results",
                "query": "results evaluation experiments findings metrics performance quantitative qualitative outputs",
                "sections": ["results"],
                "terms": ["results", "evaluation", "experiment", "experiments", "findings", "metrics", "performance"],
            },
            {
                "label": "Conclusion",
                "query": "conclusion discussion future work implications limitations final findings",
                "sections": ["future_work", "limitations"],
                "terms": ["conclusion", "conclusions", "discussion", "future work", "limitations", "implications"],
            },
        ]

        all_results = self.collection.get(where={"paper_id": paper_id})
        documents = all_results.get("documents") or []
        metadatas = all_results.get("metadatas") or []
        all_chunks = [
            {
                "content": document,
                "metadata": metadata or {},
                "score": 0.0,
            }
            for document, metadata in zip(documents, metadatas)
            if document and metadata and metadata.get("workspace_id") == workspace_id
        ]
        if not all_chunks:
            return {
                "chunks": [],
                "text": "",
                "chunk_count": 0,
                "avg_score": 0,
            }

        evidence_lines = []
        selected_chunks = []
        for spec in specs:
            candidates = self.search_paper(
                paper_id=paper_id,
                workspace_id=workspace_id,
                query=spec["query"],
                top_k=max(limit_per_section * 5, 12),
            )
            candidate_keys = {
                (
                    chunk.get("metadata", {}).get("paper_id"),
                    chunk.get("metadata", {}).get("chunk_index"),
                )
                for chunk in candidates
            }
            for chunk in all_chunks:
                key = (
                    chunk.get("metadata", {}).get("paper_id"),
                    chunk.get("metadata", {}).get("chunk_index"),
                )
                if key not in candidate_keys:
                    candidates.append(chunk)

            section_chunks = self.rerank_chunks_for_sections(
                query=spec["query"],
                chunks=candidates,
                preferred_sections=spec["sections"],
                section_terms=spec["terms"],
                top_k=limit_per_section,
            )
            evidence_lines.append(f"### Evidence For {spec['label']}")
            if not section_chunks:
                evidence_lines.append("Not Specified in Paper")
                continue
            for chunk in section_chunks:
                metadata = chunk.get("metadata") or {}
                selected_chunks.append(chunk)
                evidence_lines.append(
                    f"[P{paper_id}-C{metadata.get('chunk_index', len(selected_chunks))} | {title} | "
                    f"Section: {self._display_section_name(metadata.get('section', 'body'))} | "
                    f"Heading: {metadata.get('heading', 'unknown')} | "
                    f"Score: {chunk.get('score', 0):.2f}]\n"
                    f"{chunk.get('content', '')}"
                )

        unique_chunks = []
        unique_seen = set()
        for chunk in selected_chunks:
            metadata = chunk.get("metadata") or {}
            key = (metadata.get("paper_id"), metadata.get("chunk_index"))
            if key in unique_seen:
                continue
            unique_seen.add(key)
            unique_chunks.append(chunk)

        return {
            "chunks": unique_chunks,
            "text": "\n\n".join(evidence_lines),
            "chunk_count": len(unique_chunks),
            "avg_score": sum(float(chunk.get("score") or 0) for chunk in unique_chunks) / max(1, len(unique_chunks)),
        }

    def get_paper_chunks(self, paper_id: int, workspace_id: int, limit: int = 8) -> List[str]:
        try:
            results = self.collection.get(where={"paper_id": paper_id})
            documents = results.get("documents") or []
            metadatas = results.get("metadatas") or []
            chunks = []
            for document, metadata in zip(documents, metadatas):
                if metadata and metadata.get("workspace_id") == workspace_id and document:
                    chunks.append(document)
            return chunks[:limit]
        except Exception as e:
            print(f"Error loading indexed chunks for paper {paper_id}: {e}")
            return []

vector_service = VectorService()
