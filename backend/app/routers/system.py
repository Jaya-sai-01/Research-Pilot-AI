from fastapi import APIRouter

from app.services.llm_service import llm_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/provider-health")
def provider_health():
    return llm_service.provider_health()


@router.get("/provider-debug")
def provider_debug():
    return llm_service.provider_debug()


@router.get("/test-groq")
def test_groq():
    return llm_service.test_provider("groq")


@router.get("/test-gemini")
def test_gemini():
    return llm_service.test_provider("gemini")


@router.get("/test-openrouter")
def test_openrouter():
    return llm_service.test_provider("openrouter")


@router.get("/test-ollama")
def test_ollama():
    return llm_service.test_provider("ollama")
