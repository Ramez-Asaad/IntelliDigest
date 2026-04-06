"""
conversation.py
---------------
Chat history management with summary-based memory compression.
Maintains a rolling conversation summary for context-aware multi-turn chat.

Derived from Lab 3 — enhanced with structured storage and LLM-based
summary compression.
"""

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()


class ConversationMemory:
    """Manages chat history with rolling summary compression."""

    def __init__(
        self,
        groq_api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        max_history_length: int = 10,
    ):
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY in your .env file."
            )

        self.llm = ChatGroq(
            groq_api_key=api_key,
            model_name=model,
            temperature=0.2,
        )
        self.max_history_length = max_history_length
        self.chat_history: list[dict] = []
        self.summary: str = ""

    def add_exchange(self, user_message: str, ai_response: str) -> None:
        """Record a user-AI exchange and compress if needed."""
        self.chat_history.append({
            "role": "user",
            "content": user_message,
        })
        self.chat_history.append({
            "role": "assistant",
            "content": ai_response,
        })

        # Compress older history into summary when history gets long
        if len(self.chat_history) > self.max_history_length * 2:
            self._compress_history()

    def _compress_history(self) -> None:
        """Summarize older messages to keep context window manageable."""
        # Take the older half to summarize
        split = len(self.chat_history) // 2
        older = self.chat_history[:split]
        self.chat_history = self.chat_history[split:]

        # Build summary of older messages
        older_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in older
        )

        prompt = (
            f"Update this conversation summary with the new exchanges.\n"
            f"Current summary: {self.summary or '(empty)'}\n\n"
            f"New exchanges:\n{older_text}\n\n"
            f"Write a brief updated summary (3-4 sentences max):"
        )

        result = self.llm.invoke([HumanMessage(content=prompt)])
        self.summary = result.content.strip()

    def get_context_string(self) -> str:
        """Get the full conversation context as a formatted string."""
        parts = []
        if self.summary:
            parts.append(f"[Previous conversation summary]: {self.summary}")

        for msg in self.chat_history[-6:]:  # Last 3 exchanges
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}")

        return "\n".join(parts)

    def get_display_history(self) -> list[dict]:
        """Get the full chat history for UI display."""
        return self.chat_history.copy()

    def clear(self) -> None:
        """Reset all memory."""
        self.chat_history = []
        self.summary = ""
