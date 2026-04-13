"""
Support AgentExecutor: support-only KB search, classify_issue, create_ticket,
and UI affordance tools (no direct ticket mutations from the LLM).
"""

import json
import os

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from chains.llm_factory import make_groq_with_ollama_fallback
from support.classifier import get_classifier_tool
from support.config import SUPPORT_LLM_MODEL, SUPPORT_LLM_TEMPERATURE
from support.memory import get_memory
from support.prompts import SUPPORT_SYSTEM_PROMPT
from support.retriever import make_search_support_knowledge_tool
from support.sanitize_reply import sanitize_support_reply
from support.tickets import get_ticket_by_id, make_create_ticket_tool
from support.ui_tools import (
    get_show_new_chat_ui_tool,
    make_show_close_ticket_ui_tool,
    make_show_edit_ticket_ui_tool,
)
from vectorstore.engine import VectorStoreEngine

SYSTEM_PROMPT = SUPPORT_SYSTEM_PROMPT

_agent_cache: dict[str, AgentExecutor] = {}


def _normalize_tool_input(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _iter_tool_invocations(intermediate_steps):
    """Yield (tool_name, input_dict) for each tool call in agent steps (LC variants)."""
    for step in intermediate_steps or []:
        if not step:
            continue
        action = step[0]
        if getattr(action, "tool", None):
            yield action.tool, _normalize_tool_input(getattr(action, "tool_input", None))
        for tc in getattr(action, "tool_calls", None) or []:
            if isinstance(tc, dict):
                nm = tc.get("name")
                if nm:
                    yield nm, _normalize_tool_input(tc.get("args") or tc.get("input") or {})


def collect_ui_actions_from_steps(intermediate_steps, user_id: str) -> list[dict]:
    """
    Attach close/edit/new-chat buttons only when the model invoked the matching UI tools.
    Ticket ids are validated against SQLite (must exist; close not shown if already closed).
    """
    actions: list[dict] = []
    seen: set[str] = set()
    for name, inp in _iter_tool_invocations(intermediate_steps):
        if name == "show_close_ticket_confirmation_ui":
            tid = str(inp.get("ticket_id", "")).strip().upper()
            row = get_ticket_by_id(tid, user_id) if tid else None
            if not row:
                continue
            if (row.get("status") or "").strip().lower() == "closed":
                continue
            key = f"close:{tid}"
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                {
                    "kind": "close_ticket",
                    "ticket_id": tid,
                    "label": "Issue resolved — close ticket",
                }
            )
        elif name == "show_edit_ticket_confirmation_ui":
            tid = str(inp.get("ticket_id", "")).strip().upper()
            if not tid or not get_ticket_by_id(tid, user_id):
                continue
            key = f"edit:{tid}"
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                {
                    "kind": "edit_ticket",
                    "ticket_id": tid,
                    "label": "Edit ticket",
                }
            )
        elif name == "show_new_support_chat_confirmation_ui":
            if "new_chat" in seen:
                continue
            seen.add("new_chat")
            actions.append({"kind": "new_ticket", "label": "Start new support chat"})
    return actions


def _create_agent(
    session_id: str, vectorstore_engine: VectorStoreEngine, user_id: str
) -> AgentExecutor:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment.")

    llm = make_groq_with_ollama_fallback(
        model_name=SUPPORT_LLM_MODEL,
        temperature=SUPPORT_LLM_TEMPERATURE,
        groq_api_key=api_key,
        model_kwargs={"parallel_tool_calls": False},
    )

    kb_tool = make_search_support_knowledge_tool(vectorstore_engine)
    tools = [
        kb_tool,
        get_classifier_tool(),
        make_create_ticket_tool(user_id),
        make_show_close_ticket_ui_tool(user_id),
        make_show_edit_ticket_ui_tool(user_id),
        get_show_new_chat_ui_tool(),
    ]

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    memory = get_memory(f"{user_id}:{session_id}")

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=True,
        handle_parsing_errors=(
            "Tool call was invalid. Retry with a valid tool invocation only—"
            "never put tool names, JSON, or <function> tags in the user-visible answer."
        ),
        max_iterations=8,
        return_intermediate_steps=True,
    )


def get_support_agent(
    session_id: str, vectorstore_engine: VectorStoreEngine, user_id: str
) -> AgentExecutor:
    cache_key = f"{user_id}:{session_id}:{id(vectorstore_engine)}"
    if cache_key not in _agent_cache:
        _agent_cache[cache_key] = _create_agent(session_id, vectorstore_engine, user_id)
    return _agent_cache[cache_key]


def clear_support_agent(
    session_id: str, vectorstore_engine: VectorStoreEngine, user_id: str
) -> None:
    cache_key = f"{user_id}:{session_id}:{id(vectorstore_engine)}"
    if cache_key in _agent_cache:
        del _agent_cache[cache_key]


def process_support_message(
    user_message: str,
    session_id: str,
    vectorstore_engine: VectorStoreEngine,
    user_id: str,
) -> tuple[str, list[dict]]:
    try:
        agent = get_support_agent(session_id, vectorstore_engine, user_id)
        result = agent.invoke({"input": user_message})
        out = result.get(
            "output",
            "I apologize, but I couldn't process your request. Please try again.",
        )
        cleaned = sanitize_support_reply(out)
        ui_actions = collect_ui_actions_from_steps(
            result.get("intermediate_steps"), user_id
        )
        return cleaned, ui_actions
    except Exception as e:
        error_msg = str(e)
        print(f"[Support Agent Error] Session {session_id}: {error_msg}")
        if "rate limit" in error_msg.lower():
            return (
                "The Groq API is rate-limited right now. Wait a moment and try again. "
                "If it keeps happening, we can log a support ticket with the details."
            ), []
        if "api key" in error_msg.lower() or "auth" in error_msg.lower():
            return (
                "I'm having trouble connecting to my systems right now. "
                "Please verify GROQ_API_KEY configuration."
            ), []
        if "failed to call" in error_msg.lower() or "failed_generation" in error_msg.lower():
            return (
                "The model had trouble using tools just now (common with fast Groq models). "
                "Try sending your message again. If it keeps failing, set SUPPORT_LLM_MODEL to "
                "`llama-3.3-70b-versatile` in `.env` and restart the server, or ask a simpler question."
            ), []
        return (
            "Something went wrong on my side. Try rephrasing your question, "
            "or ask me to create a support ticket so the issue is recorded."
        ), []
