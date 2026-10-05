from langchain_core.language_models import BaseChatModel

from app.config import Settings


def build_llm(settings: Settings, json_mode: bool = False) -> BaseChatModel:
    """Return a chat model backed by an open-source LLM server."""
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=0 if json_mode else settings.llm_temperature,
            format="json" if json_mode else None,
        )

    from langchain_openai import ChatOpenAI

    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        temperature=0 if json_mode else settings.llm_temperature,
        model_kwargs=kwargs,
    )
