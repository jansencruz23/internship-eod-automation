from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings

_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    """Lazy singleton for the Gemini LLM. Shared by Teams and Internity agents."""
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            max_output_tokens=1024,
        )
    return _llm
