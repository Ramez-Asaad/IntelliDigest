"""
summarizer.py
-------------
LangChain summarization chains using Groq's llama-3.3-70b-versatile model.
Provides two chain types:

  1. Brief   — 1-2 sentence summary (Stuff-style: single LLM call)
  2. Detailed — Paragraph-length summary (Map-Reduce: map + combine)

Supports persona-based summarization where the tone adapts to the active persona.

Derived from Lab 4 — adapted with LCEL chain composition.
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chains.llm_factory import make_groq_with_ollama_fallback
from personas.personas import PERSONAS, DEFAULT_PERSONA


class Summarizer:
    """Generates brief or detailed summaries using LangChain LCEL chains."""

    def __init__(
        self,
        groq_api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
    ):
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY in your .env file."
            )
        self.llm = make_groq_with_ollama_fallback(
            model_name=model,
            temperature=0.3,
            groq_api_key=api_key,
        )
        self.parser = StrOutputParser()

    # ── Stuff-style brief summary (single LLM call) ─────────────────────

    def _build_brief_chain(self, persona_id: str):
        persona = PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])
        prompt = ChatPromptTemplate.from_messages([
            ("system", persona["brief_instruction"]),
            ("human", "Article:\n{text}\n\nBrief Summary:"),
        ])
        return prompt | self.llm | self.parser

    # ── Map-Reduce-style detailed summary ────────────────────────────────

    def _build_map_chain(self, persona_id: str):
        persona = PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])
        prompt = ChatPromptTemplate.from_messages([
            ("system", persona["detailed_instruction"]),
            ("human",
             "Extract the key points from the following text.\n\n"
             "Text:\n{text}\n\nKey points:"),
        ])
        return prompt | self.llm | self.parser

    def _build_reduce_chain(self, persona_id: str):
        persona = PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])
        prompt = ChatPromptTemplate.from_messages([
            ("system", persona["detailed_instruction"]),
            ("human",
             "Using the key points below, write a detailed summary paragraph.\n\n"
             "Key points:\n{text}\n\nDetailed Summary:"),
        ])
        return prompt | self.llm | self.parser

    # ── Public API ───────────────────────────────────────────────────────

    def summarize_brief(
        self, text: str, persona_id: str = DEFAULT_PERSONA
    ) -> str:
        """Generate a 1-2 sentence summary (Stuff chain)."""
        chain = self._build_brief_chain(persona_id)
        return chain.invoke({"text": text}).strip()

    def summarize_detailed(
        self, text: str, persona_id: str = DEFAULT_PERSONA
    ) -> str:
        """Generate a paragraph-length summary (Map-Reduce chain)."""
        map_chain = self._build_map_chain(persona_id)
        key_points = map_chain.invoke({"text": text})

        reduce_chain = self._build_reduce_chain(persona_id)
        return reduce_chain.invoke({"text": key_points}).strip()

    def summarize_articles(
        self,
        articles: list[dict],
        mode: str = "brief",
        persona_id: str = DEFAULT_PERSONA,
    ) -> list[dict]:
        """Summarize a list of article dicts."""
        summarize_fn = (
            self.summarize_brief if mode == "brief" else self.summarize_detailed
        )
        results = []
        for article in articles:
            text = "\n\n".join(
                filter(None, [
                    article.get("title", ""),
                    article.get("description", ""),
                    article.get("content", ""),
                ])
            )
            if not text.strip():
                continue

            summary = summarize_fn(text, persona_id=persona_id)
            results.append({
                "title": article.get("title", "Untitled"),
                "summary": summary,
                "url": article.get("url", ""),
                "source": article.get("source", "Unknown"),
            })
        return results
