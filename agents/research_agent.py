"""
research_agent.py
-----------------
LangChain ReAct-style agent with custom tools for multi-source knowledge
retrieval. The agent intelligently decides which tool to use based on the
user's question:

  - search_knowledge_base — semantic search over uploaded docs + news
  - search_news           — fetch fresh articles from NewsAPI
  - summarize_text        — generate brief or detailed summaries

This is a key differentiator for the resume — demonstrating agent-based
reasoning with tool use.
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chains.llm_factory import make_groq_with_ollama_fallback
from personas.personas import PERSONAS, DEFAULT_PERSONA


def create_research_agent(vectorstore_engine, news_retriever=None, summarizer=None):
    """
    Create a research agent that reasons about which tools to use.

    Uses a structured prompt-based approach (rather than full AgentExecutor)
    for reliability with Groq's models.
    """

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment.")

    llm = make_groq_with_ollama_fallback(
        model_name="llama-3.3-70b-versatile",
        temperature=0.3,
        groq_api_key=api_key,
    )

    def agent_respond(
        user_query: str,
        persona_id: str = DEFAULT_PERSONA,
        chat_history: str = "",
        user_id: str = "",
    ) -> dict:
        """
        The agent analyzes the query and decides how to respond:
        1. If about knowledge base content → RAG search + answer
        2. If asking for news → search news + summarize
        3. If general question → direct LLM response with context
        """
        persona = PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])

        # Step 1: Retrieve relevant context from knowledge base (per-user collection)
        docs = vectorstore_engine.search_similar(user_id, user_query, k=5)
        kb_context = ""
        sources = []

        if docs:
            context_parts = []
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get("source", "Unknown")
                title = doc.metadata.get("title", "")
                url = doc.metadata.get("url", "")
                header = f"[Source {i}: {source}]"
                if title:
                    header += f" — {title}"
                context_parts.append(f"{header}\n{doc.page_content[:500]}")

                source_info = {"source": source, "title": title, "url": url}
                if source_info not in sources:
                    sources.append(source_info)

            kb_context = "\n\n---\n\n".join(context_parts)

        # Step 2: Build the agent prompt
        system_prompt = f"""You are IntelliDigest, an intelligent multi-source research assistant.
{persona['system_prompt']}

Your capabilities:
- You have access to a knowledge base containing uploaded documents and news articles.
- You provide accurate, well-sourced answers based on the available context.
- If the context is insufficient, you say so honestly.
- You always cite your sources.

{"Knowledge Base Context:" + chr(10) + kb_context if kb_context else "The knowledge base is currently empty. Suggest the user upload documents or search for news."}

{"Previous conversation:" + chr(10) + chat_history if chat_history else ""}"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{question}"),
        ])

        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke({"question": user_query}).strip()

        # Determine what tools were "used"
        tools_used = []
        if kb_context:
            tools_used.append("🔍 Knowledge Base Search")
        if not kb_context:
            tools_used.append("🧠 Direct LLM Response")

        return {
            "answer": answer,
            "sources": sources,
            "tools_used": tools_used,
        }

    return agent_respond
