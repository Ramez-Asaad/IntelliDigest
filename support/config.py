"""Support feature configuration (paths and LLM constants)."""

import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(_REPO_ROOT, "data", "tickets.db")
SUPPORT_KB_DIR = os.path.join(os.path.dirname(__file__), "kb")

# IntelliDigest-specific (not generic SaaS). Used by classify_issue + ticket tool.
ISSUE_CATEGORIES = [
    "Knowledge base & chat",
    "API keys & environment",
    "Docker & deployment",
    "News, search & upload",
    "Support tickets, Telegram & n8n",
    "General",
]

TOP_K_RESULTS = 4

# Default matches research agent: smaller Groq models often break tool-calling JSON with AgentExecutor.
SUPPORT_LLM_MODEL = os.getenv("SUPPORT_LLM_MODEL", "llama-3.3-70b-versatile")
SUPPORT_LLM_TEMPERATURE = float(os.getenv("SUPPORT_LLM_TEMPERATURE", "0.25"))
