"""LLM adapter — the ONLY module permitted to call LLM provider SDKs.

All agent code must call functions from this module.
Switching providers requires only configuration changes here.

Constitution §2.0.0: All LLM provider calls MUST go through a LangChain
BaseChatModel configured here. Node functions receive the model via state
or dependency injection — they MUST NOT import vendor SDKs directly.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage


class StubChatModel(BaseChatModel):
    """Placeholder chat model for development.

    Returns a canned response. Replace with a real provider model
    (e.g., ChatOpenAI, ChatAnthropic) by changing configuration only.
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

    The model is constructed based on environment variables:
        LLM_PROVIDER — "openai" | "anthropic" | "stub" (default)
        LLM_API_KEY  — provider API key
        LLM_MODEL    — model identifier (e.g., "gpt-4o", "claude-sonnet-4-20250514")
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider or os.getenv("LLM_PROVIDER", "stub")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")

    def get_chat_model(self) -> BaseChatModel:
        """Return a LangChain BaseChatModel for the configured provider.

        Add provider branches here as needed. This is the ONLY place
        where vendor-specific SDK imports are permitted.
        """
        if self.provider == "stub":
            return StubChatModel(model_name=self.model)

        # Future providers:
        # if self.provider == "openai":
        #     from langchain_openai import ChatOpenAI
        #     return ChatOpenAI(model=self.model, api_key=self.api_key)
        # if self.provider == "anthropic":
        #     from langchain_anthropic import ChatAnthropic
        #     return ChatAnthropic(model=self.model, api_key=self.api_key)

        raise ValueError(
            f"Unknown LLM provider '{self.provider}'. "
            "Supported: 'stub'. Add provider here — nowhere else."
        )

    async def complete(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Legacy interface — send a chat completion and return parsed response.

        Prefer get_chat_model() for LangGraph node usage.
        """
        model = self.get_chat_model()
        from langchain_core.messages import HumanMessage, SystemMessage
        result = model.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return {"content": result.content, "usage": {}}

