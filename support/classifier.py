"""Issue classification tool (Groq + Ollama fallback)."""

import os
import sys

from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chains.llm_factory import make_groq_with_ollama_fallback

from support.config import ISSUE_CATEGORIES, SUPPORT_LLM_MODEL

_classifier_llm = None


def _get_classifier_llm():
    global _classifier_llm
    if _classifier_llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        _classifier_llm = make_groq_with_ollama_fallback(
            model_name=SUPPORT_LLM_MODEL,
            temperature=0.1,
            groq_api_key=api_key,
        )
    return _classifier_llm


class ClassifierInput(BaseModel):
    issue_description: str = Field(
        description="Clear description of the customer's issue or problem to be classified."
    )


@tool("classify_issue", args_schema=ClassifierInput)
def classify_issue(issue_description: str) -> str:
    """
    Classify an IntelliDigest user issue into one category (KB/chat, API keys,
    Docker, news/search/upload, tickets/Telegram/n8n, or General).
    """
    llm = _get_classifier_llm()
    if not llm:
        return (
            "Category: General\n"
            "Confidence: Low\n"
            "Priority: Medium\n"
            "Reasoning: GROQ_API_KEY not configured."
        )
    try:
        categories_str = ", ".join(ISSUE_CATEGORIES)
        classification_prompt = PromptTemplate(
            input_variables=["issue", "categories"],
            template="""You classify support issues for IntelliDigest — a FastAPI + Groq RAG app with Chroma, document/news ingestion, optional Docker/n8n/Telegram. There is no billing or user-login product tier.

Pick exactly ONE category from this list (copy the label verbatim):
{categories}

Issue: {issue}

Respond in EXACTLY this format (no extra text):
Category: <category name>
Confidence: <High/Medium/Low>
Priority: <Critical/High/Medium/Low>
Reasoning: <one short sentence>
""",
        )
        prompt_text = classification_prompt.format(
            issue=issue_description,
            categories=categories_str,
        )
        response = llm.invoke(prompt_text)
        return response.content.strip()
    except Exception as e:
        return (
            f"Category: General\n"
            f"Confidence: Low\n"
            f"Priority: Medium\n"
            f"Reasoning: Classification failed due to error: {str(e)}. "
            f"Defaulting to General category."
        )


def get_classifier_tool():
    return classify_issue
