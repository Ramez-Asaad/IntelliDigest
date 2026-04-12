"""
qa_chain.py
-----------
RAG (Retrieval-Augmented Generation) chain for question-answering over the
knowledge base. Retrieves relevant context from ChromaDB and injects it
into the LLM prompt for grounded, source-aware answers.

This is the key module that closes the RAG loop — the #1 most in-demand
LangChain pattern for AI engineering roles.
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chains.llm_factory import make_groq_with_ollama_fallback
from personas.personas import PERSONAS, DEFAULT_PERSONA


RAG_SYSTEM_TEMPLATE = """You are IntelliDigest, an intelligent research assistant.
{persona_instruction}

Answer the user's question using ONLY the context provided below. If the context
does not contain enough information, say so honestly. Always cite which source(s)
your answer is based on.

Context:
{context}
"""

RAG_HUMAN_TEMPLATE = "{question}"


def format_docs(docs) -> str:
    """Format retrieved documents into a single context string with sources."""
    formatted = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        title = doc.metadata.get("title", "")
        header = f"[Source {i}: {source}]"
        if title:
            header += f" — {title}"
        formatted.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(formatted)


class QAChain:
    """RAG-based question-answering chain over the vector store."""

    def __init__(
        self,
        retriever,
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
        self.retriever = retriever
        self.parser = StrOutputParser()

    def ask(
        self,
        question: str,
        persona_id: str = DEFAULT_PERSONA,
        chat_history: str = "",
    ) -> dict:
        """
        Ask a question against the knowledge base.

        Returns:
            dict with keys: answer, sources
        """
        persona = PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])
        persona_instruction = persona["system_prompt"]

        # Retrieve relevant documents
        docs = self.retriever.invoke(question)

        if not docs:
            return {
                "answer": (
                    "I don't have enough information in my knowledge base to "
                    "answer that question. Try uploading some documents or "
                    "searching for news first!"
                ),
                "sources": [],
            }

        # Format context
        context = format_docs(docs)

        # Build the prompt with history context if available
        system_msg = RAG_SYSTEM_TEMPLATE.format(
            persona_instruction=persona_instruction,
            context=context,
        )
        if chat_history:
            system_msg += f"\n\nPrevious conversation:\n{chat_history}"

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", RAG_HUMAN_TEMPLATE),
        ])

        # Build and invoke the chain
        chain = prompt | self.llm | self.parser
        answer = chain.invoke({"question": question})

        # Extract source metadata
        sources = []
        for doc in docs:
            source_info = {
                "source": doc.metadata.get("source", "Unknown"),
                "title": doc.metadata.get("title", ""),
                "url": doc.metadata.get("url", ""),
            }
            if source_info not in sources:
                sources.append(source_info)

        return {
            "answer": answer.strip(),
            "sources": sources,
        }
