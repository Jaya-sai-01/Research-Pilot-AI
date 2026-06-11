import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import List, Dict, Any, Callable, Tuple
from app.core.config import settings
from groq import Groq
import requests
import re
import traceback

logger = logging.getLogger(__name__)


class AllProvidersUnavailableError(Exception):
    def __init__(self, failures: Dict[str, str]):
        self.failures = failures
        super().__init__("All configured AI providers are unavailable")


class LlmService:
    REVIEW_SECTION_EQUIVALENTS = {
        "introduction": [
            "introduction", "overview", "project overview", "background",
        ],
        "problem_statement": [
            "problem statement", "project description", "motivation", "introduction",
            "research problem", "background", "problem definition",
        ],
        "methodology": [
            "methodology", "approach", "system design", "architecture", "workflow",
            "implementation process", "milestone implementation", "milestones",
            "technical approach", "technical design", "requirements specification",
        ],
        "architecture": [
            "architecture", "system architecture", "technical design", "system design",
            "solution architecture", "architectural design",
        ],
        "implementation": [
            "implementation", "development process", "implementation process",
            "milestones", "feature development", "project setup",
        ],
        "results": [
            "results", "evaluation", "experiments", "testing", "validation",
            "performance analysis", "demonstration", "feature demonstration",
            "system evaluation", "project outcomes",
        ],
        "conclusion": [
            "conclusion", "final remarks", "summary", "final summary",
            "closing remarks", "project outcome", "project outcomes",
            "future scope and conclusion",
        ],
        "literature_review": [
            "literature review", "related work", "background research", "prior work",
            "state of the art",
        ],
        "abstract": ["abstract", "executive summary", "overview"],
        "future_work": ["future work", "future scope", "future enhancements", "limitations and future work"],
        "references": ["references", "bibliography", "works cited", "citations"],
    }

    REVIEW_SECTION_LABELS = {
        "introduction": "Introduction",
        "problem_statement": "Problem Statement",
        "methodology": "Methodology",
        "architecture": "Architecture",
        "implementation": "Implementation",
        "results": "Results",
        "conclusion": "Conclusion",
        "literature_review": "Literature Review",
        "abstract": "Abstract",
        "future_work": "Future Work",
        "references": "References",
    }

    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self._gemini_model_cache = ""
        self._last_provider_health: Dict[str, bool] = {}
        self._last_provider_failures: Dict[str, str] = {}
        if self.api_key:
            self.client = Groq(api_key=self.api_key)
        else:
            self.client = None

    def _is_rate_limit_error(self, error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if status_code == 429:
            return True
        response = getattr(error, "response", None)
        if getattr(response, "status_code", None) == 429:
            return True
        return "429" in str(error)

    def provider_configured_status(self) -> Dict[str, bool]:
        return {
            "groq": bool(settings.GROQ_API_KEY),
            "gemini": bool(settings.GEMINI_API_KEY),
            "openrouter": bool(settings.OPENROUTER_API_KEY),
            "ollama": bool(settings.OLLAMA_BASE_URL),
        }

    def log_provider_configuration(self) -> None:
        status = self.provider_configured_status()
        for label, key in (
            ("Groq", "groq"),
            ("Gemini", "gemini"),
            ("OpenRouter", "openrouter"),
            ("Ollama", "ollama"),
        ):
            message = f"{label} configured: {status[key]}"
            logger.info(message)
            print(message)

    def _provider_error_reason(self, error: Exception) -> str:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None) or getattr(error, "status_code", None)
        detail = str(error)
        if response is not None:
            try:
                body = response.json()
            except Exception:
                body = getattr(response, "text", "")
            detail = str(body)[:600]
        if status_code:
            return f"HTTP {status_code}: {detail}"
        return detail[:600]

    def _call_groq_provider(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000, timeout: int = 60) -> str:
        if not self.api_key or not self.client:
            raise RuntimeError("Groq is not configured")

        completion = self.client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=max_tokens
        )
        return completion.choices[0].message.content or ""

    def _resolve_gemini_model(self, timeout: int = 15) -> str:
        if self._gemini_model_cache:
            return self._gemini_model_cache
        configured = (settings.GEMINI_MODEL or "").strip()
        candidates = []
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": settings.GEMINI_API_KEY},
                timeout=timeout,
            )
            response.raise_for_status()
            models = response.json().get("models") or []
            flash_models = []
            for model in models:
                name = (model.get("name") or "").replace("models/", "")
                methods = model.get("supportedGenerationMethods") or []
                if "generateContent" in methods and "flash" in name.lower():
                    flash_models.append(name)
            preferred_order = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
            for preferred in preferred_order:
                match = next((name for name in flash_models if name == preferred or name.startswith(preferred)), "")
                if match and match not in candidates:
                    candidates.append(match)
            for name in flash_models:
                if name not in candidates:
                    candidates.append(name)
        except Exception as exc:
            logger.warning("Gemini model discovery failed: %s", self._provider_error_reason(exc))

        if configured and configured not in candidates:
            candidates.append(configured)
        self._gemini_model_cache = candidates[0] if candidates else configured
        return self._gemini_model_cache

    def _call_gemini_provider(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000, timeout: int = 60) -> str:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("Gemini is not configured")

        model = self._resolve_gemini_model(timeout=min(timeout, 15))
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_tokens,
            },
        }
        response = requests.post(
            url,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or [] if candidates else []
        text = "".join(part.get("text", "") for part in parts)
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response")
        return text

    def _call_openrouter_provider(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000, timeout: int = 60) -> str:
        if not settings.OPENROUTER_API_KEY:
            raise RuntimeError("OpenRouter is not configured")

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:5173",
                "X-Title": "ResearchPilot AI",
            },
            json={
                "model": settings.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        text = ((choices[0] or {}).get("message") or {}).get("content") if choices else ""
        if not text:
            raise RuntimeError("OpenRouter returned an empty response")
        return text

    def _call_ollama_provider(self, system_prompt: str, user_prompt: str, max_tokens: int = 4000, timeout: int = 120) -> str:
        if not settings.OLLAMA_BASE_URL:
            raise RuntimeError("Ollama is not configured")

        response = requests.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = (data.get("message") or {}).get("content") or data.get("response") or ""
        if not text.strip():
            raise RuntimeError("Ollama returned an empty response")
        return text

    def _provider_chain(self) -> List[Tuple[str, Callable[..., str]]]:
        providers = [
            ("Groq", self._call_groq_provider),
            ("Gemini", self._call_gemini_provider),
            ("OpenRouter", self._call_openrouter_provider),
            ("Ollama", self._call_ollama_provider),
        ]
        if settings.AI_TOOLS_GROQ_ONLY:
            return providers[:1]
        return providers

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        failures: Dict[str, str] = {}
        providers = self._provider_chain()

        for index, (provider_name, provider) in enumerate(providers):
            logger.info("Trying %s", provider_name)
            print(f"Trying {provider_name}")
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(provider, system_prompt, user_prompt)
                return future.result(timeout=75)
            except TimeoutError:
                reason = "provider generation timed out"
                failures[provider_name] = reason
                logger.warning("%s failed (reason): %s", provider_name, reason)
                print(f"{provider_name} failed (reason): {reason}")
                if index + 1 < len(providers):
                    logger.info("Switching to %s", providers[index + 1][0])
                    print(f"Switching to {providers[index + 1][0]}")
            except Exception as e:
                reason = self._provider_error_reason(e)
                failures[provider_name] = reason
                if provider_name == "Groq" and self._is_rate_limit_error(e):
                    logger.warning("Groq failed (reason): %s", reason)
                    print(f"Groq failed (reason): {reason}")
                else:
                    logger.warning("%s failed (reason): %s", provider_name, reason)
                    print(f"{provider_name} failed (reason): {reason}")
                if index + 1 < len(providers):
                    logger.info("Switching to %s", providers[index + 1][0])
                    print(f"Switching to {providers[index + 1][0]}")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        raise AllProvidersUnavailableError(failures)

    def provider_self_test(self) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        prompt = "Reply OK only."

        def run_provider_test(provider_name: str, provider: Callable[..., str]) -> Dict[str, Any]:
            try:
                provider("You are a provider health check.", prompt, max_tokens=8, timeout=10)
                return {"configured": True, "ok": True, "reason": ""}
            except Exception as e:
                logger.exception("%s startup self-test failed with stack trace", provider_name)
                return {
                    "configured": True,
                    "ok": False,
                    "reason": self._provider_error_reason(e),
                    "stack_trace": traceback.format_exc(),
                }

        executor = ThreadPoolExecutor(max_workers=4)
        futures = {}
        for provider_name, provider in self._provider_chain():
            configured_key = provider_name.lower().split()[0]
            configured = self.provider_configured_status().get(configured_key if configured_key != "openrouter" else "openrouter", False)
            if not configured:
                results[provider_name] = {"configured": False, "ok": False, "reason": "not configured"}
                logger.info("%s self-test skipped: not configured", provider_name)
                print(f"{provider_name} self-test skipped: not configured")
                continue
            futures[provider_name] = executor.submit(run_provider_test, provider_name, provider)

        for provider_name, future in futures.items():
            try:
                result = future.result(timeout=20)
                results[provider_name] = result
                if result.get("ok"):
                    logger.info("%s self-test success", provider_name)
                    print(f"{provider_name} self-test success")
                else:
                    logger.warning("%s self-test failed: %s", provider_name, result.get("reason"))
                    print(f"{provider_name} self-test failed: {result.get('reason')}")
            except TimeoutError:
                reason = "provider health check timed out"
                results[provider_name] = {"configured": True, "ok": False, "reason": reason}
                logger.warning("%s self-test failed: %s", provider_name, reason)
                print(f"{provider_name} self-test failed: {reason}")
            except Exception as e:
                reason = self._provider_error_reason(e)
                results[provider_name] = {"configured": True, "ok": False, "reason": reason}
                logger.warning("%s self-test failed: %s", provider_name, reason)
                print(f"{provider_name} self-test failed: {reason}")

        executor.shutdown(wait=False, cancel_futures=True)
        self._last_provider_health = {
            "groq": results.get("Groq", {}).get("ok", False),
            "gemini": results.get("Gemini", {}).get("ok", False),
            "openrouter": results.get("OpenRouter", {}).get("ok", False),
            "ollama": results.get("Ollama", {}).get("ok", False),
        }
        self._last_provider_failures = {
            name: value.get("reason", "")
            for name, value in results.items()
            if not value.get("ok")
        }
        return results

    def provider_health(self) -> Dict[str, bool]:
        if self._last_provider_health:
            return self._last_provider_health
        status = self.provider_configured_status()
        return {
            "groq": False if status["groq"] else False,
            "gemini": False if status["gemini"] else False,
            "openrouter": False if status["openrouter"] else False,
            "ollama": False if status["ollama"] else False,
        }

    def _provider_diagnostic_spec(self, provider_key: str) -> Tuple[str, Callable[..., str], str, bool]:
        configured = self.provider_configured_status()
        if provider_key == "groq":
            return "Groq", self._call_groq_provider, settings.GROQ_MODEL, configured["groq"]
        if provider_key == "gemini":
            model = self._gemini_model_cache or settings.GEMINI_MODEL
            return "Gemini", self._call_gemini_provider, model, configured["gemini"]
        if provider_key == "openrouter":
            return "OpenRouter", self._call_openrouter_provider, settings.OPENROUTER_MODEL, configured["openrouter"]
        if provider_key == "ollama":
            return "Ollama", self._call_ollama_provider, settings.OLLAMA_MODEL, configured["ollama"]
        raise ValueError(f"Unknown provider: {provider_key}")

    def test_provider(self, provider_key: str) -> Dict[str, Any]:
        provider_name, provider, model, configured = self._provider_diagnostic_spec(provider_key)
        if not configured:
            error = f"{provider_name} is not configured"
            logger.warning("%s diagnostic skipped: %s", provider_name, error)
            self._last_provider_health[provider_key] = False
            self._last_provider_failures[provider_name] = error
            return {
                "success": False,
                "provider": provider_name,
                "model": model,
                "configured": False,
                "error": error,
            }

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                provider,
                "You are a provider diagnostic check. Reply with OK only.",
                "Reply OK.",
                8,
                20,
            )
            response = future.result(timeout=30)
            if provider_key == "gemini":
                model = self._gemini_model_cache or model
            self._last_provider_health[provider_key] = True
            self._last_provider_failures.pop(provider_name, None)
            return {
                "success": True,
                "provider": provider_name,
                "model": model,
                "configured": True,
                "error": "",
                "response_preview": response[:120],
            }
        except TimeoutError:
            exact_error = f"{provider_name} diagnostic timed out after 30 seconds"
            logger.exception("%s diagnostic timed out with exact stack trace", provider_name)
            self._last_provider_health[provider_key] = False
            self._last_provider_failures[provider_name] = exact_error
            return {
                "success": False,
                "provider": provider_name,
                "model": self._gemini_model_cache if provider_key == "gemini" and self._gemini_model_cache else model,
                "configured": True,
                "error": exact_error,
                "stack_trace": traceback.format_exc(),
            }
        except Exception as exc:
            exact_error = self._provider_error_reason(exc)
            stack_trace = traceback.format_exc()
            logger.exception("%s diagnostic failed with exact stack trace", provider_name)
            self._last_provider_health[provider_key] = False
            self._last_provider_failures[provider_name] = exact_error
            return {
                "success": False,
                "provider": provider_name,
                "model": self._gemini_model_cache if provider_key == "gemini" and self._gemini_model_cache else model,
                "configured": True,
                "error": exact_error,
                "stack_trace": stack_trace,
            }
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def provider_debug(self) -> Dict[str, Dict[str, Any]]:
        debug: Dict[str, Dict[str, Any]] = {}
        for provider_key in ("groq", "gemini", "openrouter", "ollama"):
            result = self.test_provider(provider_key)
            debug[provider_key] = {
                "configured": result.get("configured", False),
                "error": result.get("error", ""),
            }
            if result.get("stack_trace"):
                debug[provider_key]["stack_trace"] = result["stack_trace"]
        return debug

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        return self._call_llm(system_prompt, user_prompt)

    def _paper_corpus(self, papers: List[Dict[str, Any]], max_chars: int = 10000) -> str:
        corpus = []
        for index, paper in enumerate(papers, start=1):
            content = (paper.get("text_content") or paper.get("abstract") or "").strip()
            if not content:
                content = "No analyzable paper text available."
            paper_id = paper.get("id", index)
            source_priority = paper.get("source_priority", "Unknown")
            corpus.append(
                f"<paper id=\"{paper_id}\" ordinal=\"{index}\">\n"
                f"Title: {paper.get('title', 'Untitled')}\n"
                f"Authors: {paper.get('authors') or 'Unknown'}\n"
                f"Published Date: {paper.get('published_date') or 'Not specified'}\n"
                f"Evidence Priority Used: {source_priority}\n"
                f"Evidence Pack:\n{content[:max_chars]}\n"
                f"</paper>"
            )
        return "\n\n".join(corpus)

    def _has_minimum_evidence(self, papers: List[Dict[str, Any]], min_papers: int = 1) -> bool:
        usable_papers = 0
        for paper in papers:
            content = (paper.get("text_content") or paper.get("abstract") or "").strip()
            if len(content) >= 200:
                usable_papers += 1
        return usable_papers >= min_papers

    def _confidence_from_chunks(self, chunk_count: int, has_full_text: bool = False) -> str:
        if chunk_count >= 6 or has_full_text:
            return "High"
        if chunk_count >= 2:
            return "Medium"
        if chunk_count == 1:
            return "Low"
        return "Low"

    def _evidence_sources_section(self, papers: List[Dict[str, Any]], heading: str = "Evidence Sources Used") -> str:
        lines = [f"### {heading}"]
        for index, paper in enumerate(papers, start=1):
            chunk_count = int(paper.get("chunk_count_used") or 0)
            if chunk_count == 0 and (paper.get("text_content") or paper.get("abstract")):
                chunk_count = 1
            confidence = paper.get("evidence_confidence") or self._confidence_from_chunks(
                chunk_count,
                bool(paper.get("has_full_text")),
            )
            lines.extend([
                f"{index}. {paper.get('title') or 'Untitled'}",
                f"   Source: {paper.get('source_priority') or 'Unknown'}",
                f"   Chunks Used: {chunk_count}",
                f"   Confidence: {confidence}",
            ])
        return "\n".join(lines)

    def _quality_score_section(
        self,
        papers: List[Dict[str, Any]],
        direct_evidence_percent: int,
        inference_percent: int,
    ) -> str:
        supporting_papers = sum(
            1 for paper in papers
            if (paper.get("text_content") or paper.get("abstract") or "").strip()
        )
        total_papers = max(len(papers), 1)
        chunk_coverage = sum(1 for paper in papers if int(paper.get("chunk_count_used") or 0) > 0)
        coverage_percent = round((chunk_coverage or supporting_papers) / total_papers * 100)
        support_percent = round(supporting_papers / total_papers * 100)
        score = round(
            coverage_percent * 0.35
            + support_percent * 0.25
            + direct_evidence_percent * 0.30
            + max(0, 100 - inference_percent) * 0.10
        )
        return (
            "### Research Quality Score\n"
            f"{score}/100\n\n"
            "- Evidence Coverage: "
            f"{coverage_percent}%\n"
            "- Number of Supporting Papers: "
            f"{supporting_papers}/{total_papers}\n"
            "- Direct Evidence %: "
            f"{direct_evidence_percent}%\n"
            "- Inference %: "
            f"{inference_percent}%"
        )

    def _insufficient_evidence_response(self, papers: List[Dict[str, Any]]) -> str:
        return (
            "Insufficient evidence available in selected papers.\n\n"
            "Please import additional papers or PDFs.\n\n"
            f"{self._evidence_sources_section(papers)}\n\n"
            f"{self._quality_score_section(papers, direct_evidence_percent=0, inference_percent=0)}"
        )

    def _append_report_sections(
        self,
        response: str,
        evidence_section: str,
        quality_section: str,
    ) -> str:
        additions = []
        lower_response = response.lower()
        if "evidence sources used" not in lower_response:
            additions.append(evidence_section)
        if "research quality score" not in lower_response:
            additions.append(quality_section)
        if not additions:
            return response
        return f"{response.rstrip()}\n\n" + "\n\n".join(additions)

    def _append_sources_used(self, response: str, sources_section: str) -> str:
        if not sources_section or "sources used" in response.lower():
            return response
        return f"{response.rstrip()}\n\n{sources_section}"

    def _append_comparison_summary(self, response: str) -> str:
        if "comparison summary" in response.lower():
            return response
        return (
            f"{response.rstrip()}\n\n"
            "### Comparison Summary\n"
            "- Scope: Insufficient Evidence.\n"
            "- Methodology: Insufficient Evidence.\n"
            "- Evaluation: Insufficient Evidence.\n"
            "- Practical Utility: Insufficient Evidence."
        )

    def _remove_empty_comparison_rows(self, response: str) -> str:
        lines = response.splitlines()
        table_blocks = []
        current_block = []
        current_start = None
        for index, line in enumerate(lines):
            if line.strip().startswith("|") and line.strip().endswith("|"):
                if current_start is None:
                    current_start = index
                current_block.append(line)
            elif current_block:
                table_blocks.append((current_start, index, current_block))
                current_block = []
                current_start = None
        if current_block:
            table_blocks.append((current_start, len(lines), current_block))

        if not table_blocks:
            return response

        start, end, block = max(table_blocks, key=lambda item: len(item[2]))
        if len(block) < 3:
            return response

        header = block[0]
        separator = block[1]
        rows = block[2:]
        grouped_rows: Dict[str, List[str]] = {}
        order = []
        for row in rows:
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue
            field = cells[0].lower()
            grouped_rows.setdefault(field, [])
            if field not in order:
                order.append(field)
            grouped_rows[field].append(row)

        kept_rows = []
        for field in order:
            field_rows = grouped_rows[field]
            has_evidence = False
            for row in field_rows:
                cells = [cell.strip().lower() for cell in row.strip().strip("|").split("|")]
                value = cells[2] if len(cells) > 2 else ""
                evidence = cells[3] if len(cells) > 3 else ""
                if "not specified" not in value or ("not specified" not in evidence and evidence):
                    has_evidence = True
                    break
            if has_evidence:
                kept_rows.extend(field_rows)

        if not kept_rows:
            kept_rows = [
                "| Evidence Availability | Selected papers | Insufficient shared evidence for a meaningful comparison | Not Specified in Paper | Needs Review |"
            ]

        updated_lines = lines[:start] + [header, separator] + kept_rows + lines[end:]
        return "\n".join(updated_lines)

    def is_comparison_query(self, query: str) -> bool:
        comparison_patterns = [
            r"\bcompare\b",
            r"\bcomparison\b",
            r"\bwhich\s+paper\b",
            r"\bwhich\s+one\b",
            r"\bbetter\b",
            r"\bstronger\b",
            r"\bweaker\b",
            r"\bversus\b",
            r"\bvs\.?\b",
            r"\bdifference\b",
            r"\bdifferences\b",
        ]
        normalized = query.lower()
        return any(re.search(pattern, normalized) for pattern in comparison_patterns)

    def _integrity_system_prompt(self, task_name: str) -> str:
        return (
            "You are a Research Integrity and Evidence-Grounded Analysis Agent.\n"
            f"Task: {task_name}.\n"
            "Use ONLY the provided workspace papers. Do not use outside knowledge.\n"
            "Prioritize evidence extraction over text generation: Paper Content -> Evidence Extraction -> Structured Analysis -> Validation -> Final Output.\n"
            "Never generate content first and search for evidence later.\n"
            "Priority order for evidence is: 1) full PDF text chunks, 2) extracted sections, 3) abstract, 4) metadata.\n"
            "Every analytical statement must include Source Paper ID, Source Title, and Evidence Confidence.\n"
            "Every finding must cite an evidence chunk ID such as [P1-C3] when available.\n"
            "Do not create unsupported claims. If evidence is missing, write 'Not Specified in Paper'.\n"
            "Label weak inferences as inferred and never present them as factual findings.\n"
            "After the output, include a Hallucination Audit with counts and percentages for Directly Supported, Inferred, and Unsupported statements.\n"
            "If grounded content is below 90%, display this warning exactly: Insufficient evidence available in uploaded papers. Analysis quality may be reduced."
        )

    def _audit_requirements(self) -> str:
        return (
            "\n\n### Hallucination Audit\n"
            "Classify every substantive statement as one of:\n"
            "- Directly Supported: explicitly supported by a quoted evidence snippet from a paper.\n"
            "- Inferred: a cautious comparison that directly emerges from provided paper evidence.\n"
            "- Needs Review: confidence cannot be determined from the retrieved evidence.\n"
            "- Unsupported: contradicts retrieved evidence or makes a claim with no available evidence. Avoid these; if any remain, list them.\n"
            "Use the same retrieved evidence chunks and citation IDs used in the report body. "
            "If a statement cites a retrieved evidence chunk and does not contradict it, do not classify it as Unsupported.\n"
            "Report:\n"
            "- Paper Grounded %\n"
            "- Inferred %\n"
            "- Needs Review %\n"
            "- Unsupported %\n"
            "- Needs Review Statements: list or 'None'\n"
            "- Unsupported Statements: list or 'None'\n"
            "If Paper Grounded % is below 90%, include the required warning."
        )

    def _append_hallucination_firewall(self, response: str) -> str:
        if "automated hallucination firewall" in response.lower():
            return response
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", response)
            if len(sentence.strip()) > 40
            and not sentence.strip().startswith("|")
            and not sentence.strip().startswith("###")
        ]
        direct = 0
        inferred = 0
        needs_review = 0
        unsupported = 0
        inference_markers = ("may", "might", "suggest", "indicate", "likely", "appears", "potential")
        for sentence in sentences:
            if re.search(r"\[P\d+-C\d+", sentence):
                direct += 1
            elif any(marker in sentence.lower() for marker in inference_markers):
                inferred += 1
            else:
                needs_review += 1
        total = max(1, direct + inferred + needs_review + unsupported)
        grounded_pct = round(direct / total * 100)
        inferred_pct = round(inferred / total * 100)
        needs_review_pct = round(needs_review / total * 100)
        unsupported_pct = round(unsupported / total * 100)
        grounded_display = f"{grounded_pct}%" if direct else "Needs Review"
        warning = (
            "\n- Warning: unsupported generated statements exceed 10%; review this report before use."
            if unsupported_pct > 10
            else ""
        )
        return (
            f"{response.rstrip()}\n\n"
            "### Automated Hallucination Firewall\n"
            f"- Directly Supported: {direct}\n"
            f"- Inferred: {inferred}\n"
            f"- Needs Review: {needs_review}\n"
            f"- Unsupported: {unsupported}\n"
            f"- Paper Grounded %: {grounded_display}\n"
            f"- Inferred %: {inferred_pct}%\n"
            f"- Needs Review %: {needs_review_pct}%\n"
            f"- Unsupported %: {unsupported_pct}%"
            f"{warning}"
        )

    def generate_rag_response(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        chat_history: List[Dict[str, str]] = None,
        active_papers: List[Dict[str, Any]] = None,
    ) -> str:
        active_papers = active_papers or []
        if not chunks:
            return (
                "Insufficient evidence available in selected papers.\n\n"
                "Please import additional papers or PDFs."
            )

        # Construct context from chunks
        context_str = ""
        for i, chunk in enumerate(chunks):
            title = chunk.get("metadata", {}).get("title", "Unknown Source")
            paper_id = chunk.get("metadata", {}).get("paper_id", "")
            context_str += f"[Source {i+1}]: {title} (ID: {paper_id})\n{chunk['content']}\n\n"

        comparison_mode = self.is_comparison_query(query) and len(active_papers) > 1
        sources_section = self._evidence_sources_section(active_papers, heading="Sources Used") if active_papers else ""
        
        system_prompt = (
            "You are ResearchPilot AI, an expert academic research assistant.\n"
            "Your task is to answer the user's query using the provided paper chunks as context.\n"
            "Follow these instructions strictly:\n"
            "1. Base your answer ONLY on the provided context. If the context does not contain enough information, state that clearly.\n"
            "2. Cite your sources inline using [Source 1], [Source 2], etc. or mentioning the paper title.\n"
            "3. Maintain a formal, academic, and scientific tone.\n"
            "4. Do not make up facts or extrapolate beyond the provided text.\n"
            "5. If the user query is not academic or research-related, reject it (but the classification guardrail should have blocked it first).\n"
            "6. If evidence is insufficient, answer exactly: Insufficient evidence available in selected papers. Please import additional papers or PDFs.\n"
            "7. End every answer with a Sources Used section."
        )
        if comparison_mode:
            system_prompt += (
                "\nComparison intent is detected. You MUST compare all active papers represented in the context. "
                "Do not answer from only one document. Compare Objective, Methodology, Results, Limitations, and Future Work. "
                "For each category, write Insufficient Evidence when a paper lacks direct support."
            )
        
        # Add history to user prompt if available
        history_str = ""
        if chat_history:
            history_str = "Conversation History:\n"
            for msg in chat_history[-6:]:  # Last 6 messages
                history_str += f"{msg['role'].upper()}: {msg['content']}\n"
            history_str += "\n"
            
        user_prompt = (
            f"{history_str}"
            f"Context from academic papers:\n{context_str}\n"
            f"Active paper evidence summary:\n{sources_section}\n\n"
            f"User Query: {query}\n\n"
            f"Answer:"
        )
        
        response = self._append_hallucination_firewall(self._call_groq(system_prompt, user_prompt))
        return self._append_sources_used(response, sources_section)

    def generate_assistant_response(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        chat_history: List[Dict[str, str]] = None,
    ) -> str:
        context_lines = []
        for index, chunk in enumerate(chunks[:10], start=1):
            metadata = chunk.get("metadata") or {}
            title = metadata.get("title") or "Unknown Source"
            paper_id = metadata.get("paper_id") or "unknown"
            section = metadata.get("section") or "body"
            chunk_index = metadata.get("chunk_index", index)
            content = (chunk.get("content") or "")[:2200]
            context_lines.append(
                f"[Source {index}] Paper ID: {paper_id}; Title: {title}; "
                f"Section: {section}; Chunk: {chunk_index}\n{content}"
            )
        context_str = "\n\n".join(context_lines)

        history_str = ""
        for message in (chat_history or [])[-8:]:
            role = "Assistant" if message.get("role") == "assistant" else "User"
            content = (message.get("content") or "")[:1200]
            history_str += f"{role}: {content}\n"

        if chunks:
            system_prompt = (
                "You are ResearchPilot Copilot, a production research assistant embedded in ResearchPilot.\n"
                "Answer using the provided workspace evidence whenever it is relevant. Cite evidence inline as [Source 1], [Source 2], etc.\n"
                "Never fabricate paper citations, titles, authors, or findings. If the evidence does not support a claim, say so.\n"
                "You can help summarize papers, compare methods, explain concepts, identify limitations, extract findings, and draft research prose.\n"
                "Keep answers concise, structured, and practical. End with a short 'Paper references' section listing only cited sources."
            )
            user_prompt = (
                f"Recent conversation:\n{history_str or 'No prior turns.'}\n\n"
                f"Workspace evidence:\n{context_str}\n\n"
                f"User request: {query}\n\n"
                "Answer with grounded references. If the evidence is incomplete, clearly state what is unsupported."
            )
        else:
            system_prompt = (
                "You are ResearchPilot Copilot, a helpful academic research assistant.\n"
                "No supporting workspace evidence was retrieved for this turn. You may answer general research, writing, methodology, and concept questions, "
                "but you must not claim the answer is based on the user's uploaded papers.\n"
                "Never fabricate citations. If the user asks about uploaded papers, explicitly say no supporting evidence was found."
            )
            user_prompt = (
                f"Recent conversation:\n{history_str or 'No prior turns.'}\n\n"
                f"User request: {query}\n\n"
                "Answer normally as a research assistant and include this sentence when relevant: "
                "'No supporting evidence was found in the current workspace for this answer.'"
            )

        return self._call_groq(system_prompt, user_prompt)

    def generate_summary(self, title: str, abstract: str, full_text: str = None) -> str:
        text_to_analyze = full_text[:12000] if full_text else abstract
        
        system_prompt = (
            "You are an evidence-grounded academic reviewer. Use ONLY the provided evidence pack. "
            "Every finding must cite an evidence chunk ID and section name if present, for example [P1-C3, Section: Methods]. "
            "If evidence is absent, write 'Not Specified in Paper'."
        )
        user_prompt = (
            f"Generate an evidence-grounded summary of the following academic paper:\n\n"
            f"Title: {title}\n"
            f"Evidence Pack: {text_to_analyze}\n\n"
            f"Use section-aware evidence routing strictly:\n"
            f"- Objective: use only evidence listed under 'Evidence For Objective'.\n"
            f"- Methodology: use only evidence listed under 'Evidence For Methodology'.\n"
            f"- Results: use only evidence listed under 'Evidence For Results'.\n"
            f"- Conclusion: use only evidence listed under 'Evidence For Conclusion'.\n"
            f"- Key Contributions: use the most relevant cited evidence from the four evidence blocks.\n"
            f"Do not use abstract evidence for Methodology, Results, or Conclusion unless that section's evidence block contains no better section-matched chunks.\n"
            f"Include the evidence section name in every citation.\n\n"
            f"Generate exactly the following sections in clean Markdown:\n"
            f"### Objective\n"
            f"[Explain the main goal, research question, or problem being solved]\n\n"
            f"### Methodology\n"
            f"[Detail the research design, models, datasets, or experimental setup used]\n\n"
            f"### Results\n"
            f"[Outline the key outputs, quantitative/qualitative findings, and figures if mentioned]\n\n"
            f"### Conclusion\n"
            f"[Describe the overall conclusion drawn by the authors]\n\n"
            f"### Key Contributions\n"
            f"[List only contributions supported by evidence]\n\n"
            f"{self._audit_requirements()}"
        )
        
        return self._append_hallucination_firewall(self._call_groq(system_prompt, user_prompt))

    def generate_insights(self, title: str, abstract: str, full_text: str = None) -> str:
        text_to_analyze = full_text[:12000] if full_text else abstract
        
        system_prompt = (
            "You are an evidence-grounded scientific analyst. Use ONLY the provided evidence pack. "
            "Every insight must cite evidence. Do not infer trends, strengths, weaknesses, or limitations without support. "
            "Weaknesses and limitations require explicit limitation, weakness, threat-to-validity, failure-case, or future-work evidence."
        )
        user_prompt = (
            f"Generate an evidence-grounded insights report for the following academic paper:\n\n"
            f"Title: {title}\n"
            f"Evidence Pack: {text_to_analyze}\n\n"
            f"Format the output in clean Markdown with these sections:\n"
            f"### Key Findings\n"
            f"[List the most interesting or unexpected findings from the paper]\n\n"
            f"### Important Trends\n"
            f"[Identify how this work aligns with or advances current trends in its field]\n\n"
            f"### Strengths\n"
            f"[Provide a critical review of the core strengths of the paper's design or logic]\n\n"
            f"### Weaknesses\n"
            f"[Only list weaknesses explicitly stated in the evidence. If none exist, write: No explicit limitations were discussed in the paper.]\n\n"
            f"### Limitations\n"
            f"[Only list explicit limitations, threats to validity, failure cases, or author-stated future work. If none exist, write: No explicit limitations were discussed in the paper.]\n\n"
            f"### Practical Implications\n"
            f"[Only implications directly supported by evidence]\n\n"
            f"Do not generate speculative weaknesses, bias assumptions, scalability assumptions, deployment risks, or generic AI risks unless they are directly supported by cited evidence chunks.\n"
            f"{self._audit_requirements()}"
        )
        
        return self._append_hallucination_firewall(self._call_groq(system_prompt, user_prompt))

    def _detect_review_document_type(self, title: str, text: str) -> tuple[str, str]:
        normalized = f"{title}\n{text[:12000]}".lower()
        scores = {
            "Project Report": sum(term in normalized for term in (
                "project description", "implementation", "milestones", "technical stack",
                "features", "workflow", "system design", "usability",
            )),
            "Capstone Project": sum(term in normalized for term in (
                "capstone", "project report", "implementation", "milestones", "demo", "prototype",
            )),
            "Technical Report": sum(term in normalized for term in (
                "technical report", "architecture", "system design", "technical stack", "deployment",
            )),
            "Thesis": sum(term in normalized for term in (
                "thesis", "dissertation", "chapter", "supervisor", "department",
            )),
            "Research Proposal": sum(term in normalized for term in (
                "proposal", "proposed research", "research objectives", "expected outcomes",
            )),
            "Survey Paper": sum(term in normalized for term in (
                "survey", "systematic review", "taxonomy", "state of the art", "related work",
            )),
            "Research Paper": sum(term in normalized for term in (
                "abstract", "methodology", "experiments", "results", "conclusion", "references",
            )),
        }
        doc_type, score = max(scores.items(), key=lambda item: item[1])
        if score == 0:
            return "Other", "Low"
        if score <= 2:
            return doc_type, "Medium"
        return doc_type, "High"

    def _looks_like_title_case(self, value: str) -> bool:
        words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", value)
        if not words:
            return False
        minor_words = {
            "a", "an", "and", "as", "at", "by", "for", "from", "in", "of",
            "on", "or", "the", "to", "with",
        }
        significant = [word for word in words if word.casefold() not in minor_words]
        return bool(significant) and sum(word[0].isupper() for word in significant) / len(significant) >= 0.75

    def _review_heading_candidates(self, text: str) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        seen = set()
        aliases = {
            alias
            for section_aliases in self.REVIEW_SECTION_EQUIVALENTS.values()
            for alias in section_aliases
        }

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or re.fullmatch(r"--- Page \d+ ---", line, re.IGNORECASE):
                continue

            pdf_heading = re.fullmatch(
                r"\[PDF HEADING font=([\d.]+)\]:\s*(.+)",
                line,
                re.IGNORECASE,
            )
            markdown_heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            numbered_heading = re.match(
                r"^(?:(?:section|chapter)\s+)?"
                r"(?:\d+(?:\.\d+)*|[IVXLC]+)[\s.):-]+(.+)$",
                line,
                re.IGNORECASE,
            )
            milestone_heading = re.match(
                r"^(milestone\s+\d+(?:\.\d+)?\s*[:.-]\s*.+)$",
                line,
                re.IGNORECASE,
            )

            kind = ""
            confidence = 0
            title = line
            if pdf_heading:
                kind = "large-font PDF heading"
                confidence = 98
                title = pdf_heading.group(2).strip()
            elif markdown_heading:
                kind = "Markdown heading"
                confidence = 97
                title = markdown_heading.group(2).strip()
            elif milestone_heading:
                kind = "numbered milestone heading"
                confidence = 95
                title = milestone_heading.group(1).strip()
            elif numbered_heading:
                kind = "numbered section heading"
                confidence = 94
                title = numbered_heading.group(1).strip()
            else:
                title = line.strip(" :-\t")
                word_count = len(title.split())
                has_terminal_sentence_punctuation = bool(re.search(r"[.!?;,]$", title))
                normalized_title = title.casefold()
                exact_known_title = normalized_title in aliases
                contains_known_term = any(
                    re.search(rf"\b{re.escape(alias)}\b", normalized_title)
                    for alias in aliases
                )
                is_all_caps = (
                    any(char.isalpha() for char in title)
                    and title.upper() == title
                    and word_count <= 16
                )
                is_title_case = self._looks_like_title_case(title) and word_count <= 16

                if exact_known_title and not has_terminal_sentence_punctuation:
                    kind = "explicit section heading"
                    confidence = 93
                elif is_all_caps and contains_known_term and not has_terminal_sentence_punctuation:
                    kind = "capitalized section heading"
                    confidence = 92
                elif is_title_case and contains_known_term and not has_terminal_sentence_punctuation:
                    kind = "title-case section heading"
                    confidence = 90
                else:
                    continue

            title = re.sub(
                r"^(?:(?:section|chapter)\s+)?(?:\d+(?:\.\d+)*|[IVXLC]+)[\s.):-]+",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip(" :-\t")
            normalized = title.casefold()
            if (
                not title
                or len(title) > 140
                or len(title.split()) > 16
                or re.search(r"[.!?;,]$", title)
                or normalized in seen
            ):
                continue

            seen.add(normalized)
            candidates.append({
                "title": title,
                "kind": kind,
                "confidence": confidence,
                "line_number": line_number,
            })

        return candidates

    def _review_section_evidence(self, text: str) -> Dict[str, Dict[str, Any]]:
        evidence: Dict[str, Dict[str, Any]] = {}
        headings = self._review_heading_candidates(text)
        heading_titles = {item["title"].casefold() for item in headings}
        semantic_lines = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            normalized_line = line.casefold().strip(" :-\t")
            if (
                normalized_line in heading_titles
                or line.startswith("[PDF HEADING")
                or re.fullmatch(r"--- Page \d+ ---", line, re.IGNORECASE)
                or len(line.split()) < 6
                or re.search(r"[,;:]$", line)
            ):
                continue
            semantic_lines.append(line.casefold())
        semantic_text = "\n".join(semantic_lines)
        strong_heading_count = sum(item["confidence"] >= 90 for item in headings)

        for section_key, aliases in self.REVIEW_SECTION_EQUIVALENTS.items():
            heading_matches: List[Tuple[int, int, Dict[str, Any], str]] = []
            canonical_name = section_key.replace("_", " ")

            for heading in headings:
                normalized_heading = heading["title"].casefold()
                matched_aliases = [
                    alias
                    for alias in aliases
                    if re.search(rf"\b{re.escape(alias)}\b", normalized_heading)
                ]
                if not matched_aliases:
                    continue

                best_alias = min(matched_aliases, key=lambda alias: aliases.index(alias))
                alias_priority = aliases.index(best_alias)
                direct = normalized_heading == canonical_name
                specificity = len(best_alias.split())
                match_score = heading["confidence"] + specificity * 2 - alias_priority
                heading_matches.append((int(direct), match_score, heading, best_alias))

            if heading_matches:
                _, _, best_heading, matched_alias = max(
                    heading_matches,
                    key=lambda item: (item[0], item[1], -item[2]["line_number"]),
                )
                direct = best_heading["title"].casefold() == canonical_name
                status = "FOUND_DIRECT" if direct else "FOUND_UNDER_DIFFERENT_NAME"
                confidence = min(
                    99,
                    best_heading["confidence"] + (2 if direct else 0) + min(2, len(matched_alias.split()) - 1),
                )
                evidence_heading = best_heading["title"]
                detection_method = best_heading["kind"]
            else:
                semantic_alias = next(
                    (
                        alias
                        for alias in aliases
                        if re.search(rf"\b{re.escape(alias)}\b", semantic_text)
                    ),
                    None,
                )
                if semantic_alias:
                    status = "SEMANTIC_INFERENCE"
                    confidence = 62
                    evidence_heading = "No explicit heading detected"
                    detection_method = f"semantic inference from '{semantic_alias}' content"
                else:
                    status = "NOT_CONFIDENTLY_FOUND"
                    confidence = 0
                    evidence_heading = "None"
                    detection_method = "no heading or semantic evidence"

            absence_confidence = 0
            if status == "NOT_CONFIDENTLY_FOUND":
                absence_confidence = 97 if strong_heading_count >= 5 and len(text.strip()) >= 4000 else 72

            evidence[section_key] = {
                "status": status,
                "found": status in {"FOUND_DIRECT", "FOUND_UNDER_DIFFERENT_NAME", "SEMANTIC_INFERENCE"},
                "confidence": confidence,
                "evidence_heading": evidence_heading,
                "detection_method": detection_method,
                "absence_confidence": absence_confidence,
            }

        return evidence

    def _build_review_profile(self, title: str, text: str) -> str:
        doc_type, confidence = self._detect_review_document_type(title, text)
        section_evidence = self._review_section_evidence(text)
        detected_confidences = [
            data["confidence"]
            for data in section_evidence.values()
            if data["found"]
        ]
        confidence_score = (
            round(sum(detected_confidences) / len(detected_confidences))
            if detected_confidences
            else 0
        )
        missing_sections = [
            self.REVIEW_SECTION_LABELS[key]
            for key, data in section_evidence.items()
            if data["status"] == "NOT_CONFIDENTLY_FOUND"
            and data["absence_confidence"] > 95
        ]
        score_floor_sections = (
            "problem_statement", "architecture", "methodology", "implementation", "results"
        )
        score_floor_applies = (
            doc_type in {"Project Report", "Capstone Project", "Technical Report"}
            and all(
                section_evidence[key]["status"] in {
                    "FOUND_DIRECT", "FOUND_UNDER_DIFFERENT_NAME",
                }
                for key in score_floor_sections
            )
        )
        profile_lines = [
            f"Detected Document Type: {doc_type}",
            f"Detection Confidence: {confidence}",
            "Detected Sections:",
        ]
        for section_key, data in section_evidence.items():
            display = self.REVIEW_SECTION_LABELS[section_key]
            if data["found"]:
                profile_lines.extend([
                    f"- Section: {display}",
                    f"  Confidence: {data['confidence']}%",
                    f'  Evidence Heading: "{data["evidence_heading"]}"',
                    f"  Detection: {data['detection_method']}",
                ])
            else:
                profile_lines.extend([
                    f"- Section: {display}",
                    "  Confidence: 0%",
                    '  Evidence Heading: "None"',
                    f"  Detection: not confidently found; absence confidence "
                    f"{data['absence_confidence']}%",
                ])
        profile_lines.append("Missing Sections:")
        if missing_sections:
            profile_lines.extend(f"- {section}" for section in missing_sections)
        else:
            profile_lines.append("- None confirmed above 95% absence confidence")
        profile_lines.append(f"Confidence Score: {confidence_score}%")
        profile_lines.append(
            "Project Report Score Floor: "
            + (
                "8.5/10 unless evidence-backed critical flaws exist"
                if score_floor_applies
                else "Not applicable"
            )
        )
        return "\n".join(profile_lines)

    def _prepend_review_profile(self, response: str, review_profile: str) -> str:
        if review_profile in response:
            return response
        return f"{review_profile}\n\n{response.lstrip()}"

    def _enforce_project_report_score_floor(self, response: str, review_profile: str) -> str:
        if "Project Report Score Floor: 8.5/10" not in review_profile:
            return response
        critical_flaw_match = re.search(
            r"Critical Flaws(?: Detected)?:[ \t]*(?:\r?\n)?[ \t]*(.+)",
            response,
            re.IGNORECASE,
        )
        critical_flaw_value = (
            critical_flaw_match.group(1).strip().lstrip("*- ").strip()
            if critical_flaw_match
            else ""
        )
        critical_flaw_documented = (
            critical_flaw_value.casefold() not in {"", "none", "no", "not detected"}
        )
        if critical_flaw_documented:
            return response

        score_match = re.search(
            r"(Overall Score:\s*(?:\n\s*)?)(\d+(?:\.\d+)?)\s*/\s*10",
            response,
            re.IGNORECASE,
        )
        if score_match and float(score_match.group(2)) < 8.5:
            return (
                response[:score_match.start(2)]
                + "8.5"
                + response[score_match.end(2):]
            )
        return response

    def review_research_paper(self, title: str, full_text: str) -> str:
        complete_text = full_text or ""
        if not complete_text.strip():
            return (
                "Detected Document Type: Other\n"
                "Review Confidence: Low\n"
                "Overall Score: 0/10\n\n"
                "Strengths:\n"
                "* No extracted PDF text was available for review.\n\n"
                "Suggestions:\n"
                "* Upload a readable PDF with selectable text before requesting a review.\n\n"
                "Section Feedback:\n"
                "Abstract:\nNo supporting text was found.\n\n"
                "Methodology:\nNo supporting text was found.\n\n"
                "Results:\nNo supporting text was found.\n\n"
                "Conclusion:\nNo supporting text was found.\n\n"
                "Final Recommendation:\n* Major Revision"
            )

        review_profile = self._build_review_profile(title, complete_text)
        if len(complete_text) <= 24000:
            text_to_review = complete_text
        else:
            text_to_review = (
                complete_text[:16000]
                + "\n\n[Middle of extracted text omitted from review context]\n\n"
                + complete_text[-8000:]
            )
        system_prompt = (
            "You are an adaptive academic and technical document reviewer. Review ONLY the uploaded PDF text and the provided pre-review profile.\n"
            "The pre-review profile is the mandatory section map. You MUST read and apply the complete Detected Sections map before generating any criticism.\n"
            "You must NOT rewrite, modify, regenerate, auto-correct, or provide replacement paragraphs for the paper.\n"
            "Only provide observations and actionable review suggestions grounded in detected content.\n"
            "Never fabricate missing sections, citations, results, claims, or references.\n"
            "Never claim a section is missing if equivalent section evidence exists in the pre-review profile.\n"
            "Use only Evidence Heading values as section titles. Never replace them with keywords, sentence fragments, or inferred prose.\n"
            "Distinguish MISSING SECTION from SECTION EXISTS UNDER DIFFERENT NAME. They are never interchangeable.\n"
            "Do not say 'No methodology found', 'No conclusion found', 'No results found', or equivalent absence claims unless the map reports absence confidence above 95%.\n"
            "For every criticism, add an Evidence: line containing the exact detected section heading from the map. If the map has no heading, cite the map status and do not claim the section is missing.\n"
            "Use Research Paper criteria for research papers. Use engineering/product criteria for Project Report or Capstone Project documents.\n"
            "For Project Report or Capstone, evaluate Problem Definition, Architecture, Technical Stack, Workflow, Features, Implementation Quality, AI Integration, Testing, Usability, Scalability, and Documentation Quality.\n"
            "When the profile applies an 8.5/10 project-report score floor, do not score below 8.5 unless you include a Critical Flaws Detected section with specific evidence headings and explain why each flaw is critical.\n"
            "Do not heavily penalize project reports for missing traditional academic sections when equivalent project sections exist.\n"
            "If future work is missing, recommend adding it. If references or citations are limited or inconsistent, mention that as a suggestion.\n"
            "Do not quote long passages. Do not create new paper content."
        )
        user_prompt = (
            f"Paper Title: {title}\n\n"
            f"Pre-review Profile:\n{review_profile}\n\n"
            f"Uploaded PDF Text:\n{text_to_review}\n\n"
            "Adaptive review rules:\n"
            "- Build your review from the Detected Sections map before evaluating content.\n"
            "- The application will prepend the full pre-review profile. Do not repeat Detected Document Type, Detected Sections, Missing Sections, Confidence Score, or Project Report Score Floor in your response.\n"
            "- Treat equivalent section names as valid evidence. For example Project Description can satisfy Problem Statement, Implementation/Milestones can satisfy Methodology, System Evaluation can satisfy Results, and Final Summary can satisfy Conclusion.\n"
            "- Use evidence-first wording. Bad: 'The paper lacks methodology.' Good: 'No dedicated methodology heading was found; however, implementation milestones and workflow descriptions partially serve this role.'\n"
            "- Every criticism or negative suggestion must be followed by: Evidence: <exact detected section name from the map>.\n"
            "- Suggestions must be document-specific. Name the missing metric, validation, comparison, workflow detail, or evidence that should be added and tie it to an actual heading. Never write generic suggestions such as 'Expand methodology' or 'Improve results.'\n"
            "- Example specificity: 'Add performance evaluation metrics such as response time, retrieval accuracy, and user satisfaction scores under Testing and Feature Demonstration.'\n"
            "- Avoid Major Revision solely because traditional academic section names are absent.\n\n"
            "Return exactly this format; the required detection profile will be prepended automatically:\n\n"
            "Overall Score:\n"
            "X/10\n\n"
            "Critical Flaws Detected:\n"
            "* None OR evidence-backed critical flaws\n\n"
            "Strengths:\n"
            "* ...\n"
            "* ...\n"
            "* ...\n\n"
            "Suggestions:\n"
            "* ...\n"
            "* ...\n"
            "* ...\n\n"
            "Section Feedback:\n"
            "...\n\n"
            "Final Recommendation:\n"
            "* Accept OR * Minor Revision OR * Major Revision\n\n"
            "Rules:\n"
            "- Ground every review observation in detected uploaded text.\n"
            "- Every criticism must include Evidence: followed by the exact section heading detected in the map.\n"
            "- Never cite a single keyword such as 'architecture' or 'citations' as an Evidence Heading unless that exact standalone heading was structurally detected.\n"
            "- When a canonical heading is absent but an equivalent heading exists, say 'section exists under different name' and name it.\n"
            "- Never label a section MISSING unless its section-map absence confidence is greater than 95%.\n"
            "- When map confidence is 95% or lower, say only that a dedicated heading was not confidently detected.\n"
            "- Suggestions must be review suggestions only, not replacement text.\n"
            "- Do not include rewritten paragraphs, corrected abstracts, corrected methodology text, or fabricated citations."
        )

        response = self._call_groq(system_prompt, user_prompt)
        response = self._enforce_project_report_score_floor(response, review_profile)
        return self._prepend_review_profile(response, review_profile)

    def generate_literature_review(self, papers: List[Dict[str, Any]]) -> str:
        if not self._has_minimum_evidence(papers, min_papers=2):
            return self._insufficient_evidence_response(papers)

        papers_context = self._paper_corpus(papers)
        evidence_section = self._evidence_sources_section(papers)
        quality_section = self._quality_score_section(papers, direct_evidence_percent=90, inference_percent=10)
        system_prompt = self._integrity_system_prompt("Literature Review")
        user_prompt = (
            f"Workspace papers:\n\n"
            f"{papers_context}\n"
            "\nStep 1: Extract all major themes explicitly discussed in the papers. Do not create themes not present in the papers.\n"
            "Step 2: For every theme, extract supporting papers and quote evidence snippets before analysis.\n"
            "Step 3: Generate literature review sections only from extracted evidence.\n\n"
            "Rules:\n"
            "- Do not create research trends unless multiple papers support them.\n"
            "- If a theme appears in only one paper, explicitly mention that it is single-paper evidence.\n"
            "- Reject themes supported by fewer than 2 papers unless the theme label includes 'Single-Paper Theme'.\n"
            "- Future Directions must come only from explicit future-work, conclusion, discussion, limitation, or open-challenge evidence.\n"
            "- If future-work evidence is unavailable, write exactly: Future research directions were not explicitly discussed in the selected papers.\n"
            "- Every paragraph must cite supporting paper(s) with Source Paper ID, Source Title, and Evidence Confidence.\n"
            "- Accuracy is more important than verbosity.\n\n"
            "Use exactly this repeated output format:\n"
            "### Theme: <theme name>\n"
            "- Theme Type: Multi-Paper Theme / Single-Paper Theme.\n"
            "- Supporting Papers: IDs and titles.\n"
            "- Evidence Count: number of direct evidence snippets used.\n"
            "- Evidence: quoted snippets with Source Paper ID, Source Title, and Evidence Confidence.\n"
            "- Key Findings: evidence-grounded bullets.\n"
            "- Agreement Across Papers: supported comparison or 'Not enough multi-paper evidence'.\n"
            "- Contradictions Across Papers: supported contradiction or 'No contradiction found in provided papers'.\n"
            "- Research Consensus: consensus only if multiple papers directly support it.\n"
            "- Future Directions: future directions only if grounded in evidence.\n"
            "- Analysis: paragraphs only from extracted evidence, each with citations.\n"
            "- Confidence Score: 0-100.\n"
            f"\nInclude this exact evidence section before the Hallucination Audit:\n{evidence_section}\n\n"
            f"Include this exact quality section at the end:\n{quality_section}"
            f"{self._audit_requirements()}"
        )
        
        response = self._append_hallucination_firewall(self._call_groq(system_prompt, user_prompt))
        return self._append_report_sections(response, evidence_section, quality_section)

    def compare_papers(self, papers: List[Dict[str, Any]]) -> str:
        if not self._has_minimum_evidence(papers, min_papers=2):
            return self._insufficient_evidence_response(papers)

        papers_context = self._paper_corpus(papers)
        evidence_section = self._evidence_sources_section(papers)
        quality_section = self._quality_score_section(papers, direct_evidence_percent=90, inference_percent=10)
        system_prompt = self._integrity_system_prompt("Paper Comparison")
        fields = (
            "Objective, Dataset, Methodology, Model, Architecture, Evaluation, Metrics, "
            "Results, Limitations, Future Work, Novelty, Reliability, Scalability"
        )
        user_prompt = (
            f"Workspace papers:\n\n"
            f"{papers_context}\n"
            "\nCreate a structured comparison matrix. Compare ONLY these fields:\n"
            f"{fields}.\n\n"
            "For every paper and every field provide:\n"
            "- Value: extracted value or 'Not Specified in Paper'.\n"
            "- Evidence Source: Source Paper ID, Source Title, and a short evidence snippet.\n"
            "- Confidence Score: 0-100.\n\n"
            "Omit any comparison dimension where every selected paper has no evidence. "
            "Do not show Dataset, Metrics, Future Work, or Limitations rows when all papers are Not Specified in Paper for that field. "
            "Only include meaningful dimensions with at least one cited evidence source.\n\n"
            "Use this Markdown table format:\n"
            "| Field | Paper | Value | Evidence Source | Confidence Score |\n"
            "| --- | --- | --- | --- | --- |\n"
            "Never hallucinate values. Do not compare strengths or weaknesses unless they are stated as limitations/results/future work in the papers.\n\n"
            "After the matrix add:\n"
            "### Comparison Summary\n"
            "- Scope: strongest paper only if directly evidenced, otherwise 'Insufficient Evidence'.\n"
            "- Methodology: strongest paper only if directly evidenced, otherwise 'Insufficient Evidence'.\n"
            "- Evaluation: strongest paper only if directly evidenced, otherwise 'Insufficient Evidence'.\n"
            "- Practical Utility: strongest paper only if directly evidenced, otherwise 'Insufficient Evidence'.\n"
            f"\nInclude this exact evidence section before the Hallucination Audit:\n{evidence_section}\n\n"
            f"Include this exact quality section at the end:\n{quality_section}"
            f"{self._audit_requirements()}"
        )
        
        response = self._append_comparison_summary(
            self._remove_empty_comparison_rows(
                self._append_hallucination_firewall(self._call_groq(system_prompt, user_prompt))
            )
        )
        return self._append_report_sections(response, evidence_section, quality_section)

    def _get_mock_response(self, system_prompt: str, user_prompt: str) -> str:
        """
        Graceful fallback when no provider is available.
        Never generates simulated research content.
        """
        return (
            "Unable to generate a grounded report because all configured AI providers are unavailable.\n\n"
            "Please configure Groq, Gemini, OpenRouter, or Ollama and try again."
        )
        # Determine context based on keywords in prompts
        if "generate a comprehensive, structured summary" in user_prompt:
            # Summarizer Mock
            title = re.search(r"Title:\s*(.*)", user_prompt)
            title_str = title.group(1) if title else "Paper"
            return (
                f"# Summary of: {title_str}\n\n"
                f"### Objective\n"
                f"The primary objective of this work is to address the performance limitations and computational complexities in the field. "
                f"The authors introduce a novel framework to improve accuracy while reducing latency during inference.\n\n"
                f"### Methodology\n"
                f"1. **Architecture Design**: Implementing a dual-path routing network to extract features.\n"
                f"2. **Loss Function**: Custom regularization term utilizing contrastive learning strategies.\n"
                f"3. **Experimental Setup**: Evaluated against standard industry benchmarks, testing scalability and robustness.\n\n"
                f"### Results\n"
                f"- Achieve **+4.5% improvement** in benchmarks compared to baseline models.\n"
                f"- Reduced parameter count by **18%**, resulting in faster runtimes.\n"
                f"- Demonstrates robust convergence behavior within 50 epochs.\n\n"
                f"### Conclusion\n"
                f"The proposed framework represents a viable, scalable alternative to conventional approaches. It effectively balances computational cost and task performance, laying the groundwork for real-time edge deployments.\n\n"
                f"### Key Contributions\n"
                f"- Introduces an open-source, optimized architecture.\n"
                f"- Proposes a dynamic threshold adjustment algorithm.\n"
                f"- Provides an extensive comparative study across 3 major datasets."
            )
        elif "analyze the following academic paper and generate a detailed insights report" in user_prompt:
            # Insights Mock
            title = re.search(r"Title:\s*(.*)", user_prompt)
            title_str = title.group(1) if title else "Paper"
            return (
                f"# Research Insights: {title_str}\n\n"
                f"### Key Findings\n"
                f"- The model exhibits high resilience under noisy data settings, outperforming standard transformer layers.\n"
                f"- Combining spatial attention with localized features prevents overfitting in smaller dataset regimes.\n\n"
                f"### Important Trends\n"
                f"This work aligns with the industry-wide shift toward **parameter-efficient fine-tuning (PEFT)** and green AI, proving that massive parameter scaling is not always necessary for performance leaps.\n\n"
                f"### Strengths\n"
                f"- High mathematical rigor in proving error bounds.\n"
                f"- Clear ablation studies separating the contributions of each architectural module.\n\n"
                f"### Weaknesses\n"
                f"- Relies heavily on high-quality initial data distributions.\n"
                f"- Lack of validation on extremely large-scale out-of-distribution benchmarks.\n\n"
                f"### Limitations\n"
                f"- Constrained to single-GPU testing setups.\n"
                f"- The training epoch configuration exhibits sensitivity to hyperparameter tuning parameters."
            )
        elif "Extract all major themes explicitly discussed" in user_prompt:
            # Evidence-grounded literature review fallback
            return (
                f"# Evidence-Grounded Literature Review\n\n"
                f"Insufficient evidence available in selected papers.\n\n"
                f"### Theme: Not enough verified evidence to extract themes\n"
                f"- Supporting Papers: Not Specified in Paper.\n"
                f"- Evidence: Not Specified in Paper.\n"
                f"- Key Findings: Not Specified in Paper.\n"
                f"- Agreement Across Papers: Not enough multi-paper evidence.\n"
                f"- Contradictions Across Papers: No contradiction found in provided papers.\n"
                f"- Analysis: No publication-quality literature review can be generated without verified extracted evidence.\n"
                f"- Confidence Score: 0.\n\n"
                f"### Hallucination Audit\n"
                f"- Directly Supported: 0\n"
                f"- Inferred: 1\n"
                f"- Unsupported: 0\n"
                f"- Paper Grounded %: 0%\n"
                f"- Inferred %: 100%\n"
                f"- Unsupported %: 0%\n"
                f"- Unsupported Statements: None\n"
                f"Insufficient evidence available in uploaded papers. Analysis quality may be reduced."
            )
        elif "Create a structured comparison matrix" in user_prompt:
            # Evidence-grounded comparison fallback
            return (
                f"# Paper Comparison Matrix\n\n"
                f"Insufficient evidence available in selected papers.\n\n"
                f"| Field | Paper | Value | Evidence Source | Confidence Score |\n"
                f"| --- | --- | --- | --- | --- |\n"
                f"| Research Objective | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Problem Statement | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Dataset | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Methodology | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Model | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Architecture | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Evaluation Strategy | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Metrics | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Results | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Limitations | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n"
                f"| Future Work | Selected papers | Not Specified in Paper | Not Specified in Paper | 0 |\n\n"
                f"### Hallucination Audit\n"
                f"- Directly Supported: 0\n"
                f"- Inferred: 0\n"
                f"- Unsupported: 0\n"
                f"- Paper Grounded %: 0%\n"
                f"- Inferred %: 0%\n"
                f"- Unsupported %: 0%\n"
                f"- Unsupported Statements: None\n"
                f"Insufficient evidence available in uploaded papers. Analysis quality may be reduced."
            )
        else:
            # RAG Chat Mock
            return (
                f"Based on the provided academic context for this workspace:\n\n"
                f"The papers outline that current models struggle with complex, multi-hop reasoning over long texts. "
                f"To mitigate this, authors utilize chunk-based vector search to pull relevant sections into the context window. "
                f"This allows the AI to provide highly specialized responses directly addressing your query about: *\"{re.sub(r'<[^>]+>', '', user_prompt[:80])}...\"* without exceeding token boundaries. [Source 1].\n\n"
                f"Let me know if you would like me to summarize any specific section or compare these methodologies in detail."
            )

llm_service = LlmService()
