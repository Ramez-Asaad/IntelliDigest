"""
Primary LLM Factory, supporting multi-provider BYOK (Groq, OpenAI, Gemini)
with an Ollama fallback.
"""

from __future__ import annotations

import os

import httpx
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

# Exceptions that trigger the local Ollama model (see .env OLLAMA_*).
_FALLBACK_EXCEPTIONS: tuple = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    APIStatusError,
    httpx.HTTPError,
    ConnectionError,
    TimeoutError,
    OSError,
    Exception,
)


def make_llm(
    *,
    provider: str = "groq",
    api_key: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.3,
    model_kwargs: dict | None = None,
):
    """
    Returns a Chat Model with fallbacks ([ChatOllama]).
    Works with LCEL and AgentExecutor.
    """
    mk = dict(model_kwargs or {})
    
    # Fallback to server demo key if user hasn't provided one
    if not api_key or not api_key.strip():
        api_key = os.getenv("GROQ_API_KEY")
        provider = "groq"
        
    if not api_key:
        raise ValueError("API Key is required to chat.")

    provider = provider.lower().strip()
    
    if provider == "openai":
        primary = ChatOpenAI(
            api_key=api_key,
            model=model_name or "gpt-4o",
            temperature=temperature,
            **mk,
        )
    elif provider == "gemini":
        primary = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model_name or "gemini-1.5-flash",
            temperature=temperature,
            **mk,
        )
    else:
        # Default to Groq
        primary = ChatGroq(
            groq_api_key=api_key,
            model_name=model_name or "llama-3.3-70b-versatile",
            temperature=temperature,
            **mk,
        )

    ollama_model = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5:0.5b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    fallback = ChatOllama(
        model=ollama_model,
        base_url=base_url,
        temperature=temperature,
    )

    return primary.with_fallbacks(
        [fallback],
        exceptions_to_handle=_FALLBACK_EXCEPTIONS,
    )
