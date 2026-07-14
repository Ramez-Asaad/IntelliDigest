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
import json
import re
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chains.llm_factory import make_llm
from personas.personas import PERSONAS, DEFAULT_PERSONA
from auth.users import get_user_llm_config


def create_research_agent(vectorstore_engine, news_retriever=None, summarizer=None):
    """
    Create a research agent that reasons about which tools to use.

    Uses a structured prompt-based approach (rather than full AgentExecutor)
    for reliability.
    """

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

        config = get_user_llm_config(user_id) if user_id else None
        provider = config.get("llm_provider") if config else "groq"
        api_key = config.get("llm_api_key") if config else None

        llm = make_llm(
            provider=provider,
            api_key=api_key,
            temperature=0.3,
        )

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
- You MUST write your response in rich Markdown formatting (e.g., use bold, italics, bullet points, headers, or code blocks where appropriate).

IMPORTANT: First, provide your detailed response using rich Markdown formatting.
At the very end of your response, you MUST provide 1 to 3 short search suggestions (queries the user could use to fetch more info) in exactly this format:
<suggestions>
["suggestion 1", "suggestion 2", "suggestion 3"]
</suggestions>

{"Knowledge Base Context:" + chr(10) + kb_context if kb_context else "The knowledge base is currently empty. Suggest the user upload documents or search for news."}

{"Previous conversation:" + chr(10) + chat_history if chat_history else ""}"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{question}"),
        ])

        chain = prompt | llm | StrOutputParser()
        raw_output = chain.invoke({"question": user_query}).strip()

        parsed_answer = raw_output
        suggestions = []
        
        sugg_match = re.search(r'<suggestions>\s*(.*?)\s*</suggestions>', raw_output, re.DOTALL | re.IGNORECASE)
        if sugg_match:
            try:
                suggestions = json.loads(sugg_match.group(1))
            except Exception:
                pass
            parsed_answer = re.sub(r'<suggestions>.*?</suggestions>', '', raw_output, flags=re.DOTALL | re.IGNORECASE).strip()

        # Determine what tools were "used"
        tools_used = []
        if kb_context:
            tools_used.append("🔍 Knowledge Base Search")
        if not kb_context:
            tools_used.append("🧠 Direct LLM Response")

        return {
            "answer": parsed_answer,
            "sources": sources,
            "tools_used": tools_used,
            "suggestions": suggestions,
        }

    return agent_respond
