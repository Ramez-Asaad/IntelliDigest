"""
Primary ChatGroq + Ollama fallback when Groq fails (rate limits, timeouts, 5xx, etc.).
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
from langchain_ollama import ChatOllama

# Exceptions that trigger the local Ollama model (see .env OLLAMA_*).
_GROQ_FALLBACK_EXCEPTIONS: tuple = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    APIStatusError,
    httpx.HTTPError,
    ConnectionError,
    TimeoutError,
    OSError,
)


def make_groq_with_ollama_fallback(
    *,
    model_name: str,
    temperature: float,
    groq_api_key: str | None = None,
    model_kwargs: dict | None = None,
):
    """
    Returns ChatGroq.with_fallbacks([ChatOllama]) — Runnable, works with LCEL and AgentExecutor.

    Set OLLAMA_BASE_URL (default http://127.0.0.1:11434) and OLLAMA_FALLBACK_MODEL
    (default qwen2.5:0.5b). Run `ollama serve` and `ollama pull <model>` locally.
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is required.")

    mk = dict(model_kwargs or {})
    primary = ChatGroq(
        groq_api_key=api_key,
        model_name=model_name,
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
        exceptions_to_handle=_GROQ_FALLBACK_EXCEPTIONS,
    )
