"""LLM adapter — the ONLY module permitted to call LLM provider SDKs.

All agent code must call functions from this module.
Switching providers requires only configuration changes here.

Constitution §2.0.0: All LLM provider calls MUST go through a LangChain
BaseChatModel configured here. Node functions receive the model via state
or dependency injection — they MUST NOT import vendor SDKs directly.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from src.settings_store import load_settings


class StubChatModel(BaseChatModel):
    """Placeholder chat model for development.

    Returns a canned response. Replace with a real provider model
    by changing configuration in the settings UI or env vars.
    """

    model_name: str = "stub"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> Any:
        from langchain_core.outputs import ChatGeneration, ChatResult
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="[stub] Not yet wired to a provider."))]
        )

    @property
    def _llm_type(self) -> str:
        return "stub"


class LLMAdapter:
    """Provider-agnostic wrapper that exposes a LangChain BaseChatModel.

    Configuration is read from the settings store (settings.json + env fallback).
    Supported providers: gemini, openai, anthropic, local (Ollama/vLLM), stub.
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
    ) -> None:
        settings = load_settings()
        self.provider = provider or settings.provider
        self.api_key = api_key or settings.api_key
        self.model = model or settings.model
        self.base_url = base_url or settings.base_url
        self.temperature = temperature if temperature is not None else settings.temperature

    def get_chat_model(self) -> BaseChatModel:
        """Return a LangChain BaseChatModel for the configured provider.

        This is the ONLY place where vendor-specific SDK imports are permitted.
        """
        if self.provider == "stub":
            return StubChatModel(model_name=self.model)

        if self.provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self.api_key,
                temperature=self.temperature,
            )

        if self.provider == "openai":
            from langchain_openai import ChatOpenAI
            kwargs: dict[str, Any] = {
                "model": self.model,
                "api_key": self.api_key,
                "temperature": self.temperature,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            return ChatOpenAI(**kwargs)

        if self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.model,
                api_key=self.api_key,
                temperature=self.temperature,
            )

        if self.provider == "local":
            # Local LLMs via OpenAI-compatible API (Ollama, vLLM, llama.cpp)
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.model,
                base_url=self.base_url or "http://localhost:11434/v1",
                api_key=self.api_key or "not-needed",
                temperature=self.temperature,
            )

        raise ValueError(
            f"Unknown LLM provider '{self.provider}'. "
            "Supported: 'gemini', 'openai', 'anthropic', 'local', 'stub'."
        )

    async def complete(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Legacy interface — send a chat completion and return parsed response.

        Prefer get_chat_model() for LangGraph node usage.
        """
        model = self.get_chat_model()
        from langchain_core.messages import HumanMessage, SystemMessage
        result = model.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return {"content": result.content, "usage": {}}


