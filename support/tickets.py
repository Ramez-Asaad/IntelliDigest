"""
Ticket management: SQLite persistence and LangChain create_ticket tool.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from support.config import DATABASE_PATH, ISSUE_CATEGORIES

_TICKET_CATEGORY_HELP = "Exactly one of: " + ", ".join(ISSUE_CATEGORIES)


def _get_connection():
    """Get a SQLite connection, creating the DB if needed."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            customer_name TEXT NOT NULL,
            issue_summary TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'Medium',
            suggested_solution TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def create_ticket_in_db(
    customer_name: str,
    issue_summary: str,
    category: str,
    priority: str = "Medium",
    suggested_solution: str = "",
) -> dict:
    """Insert a ticket and return its fields including id."""
    conn = _get_connection()
    try:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO tickets
               (id, customer_name, issue_summary, category, priority,
                suggested_solution, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'Open', ?, ?)""",
            (
                ticket_id,
                customer_name,
                issue_summary,
                category,
                priority,
                suggested_solution,
                now,
                now,
            ),
        )
        conn.commit()
        return {
            "id": ticket_id,
            "customer_name": customer_name,
            "issue_summary": issue_summary,
            "category": category,
            "priority": priority,
            "suggested_solution": suggested_solution,
            "status": "Open",
            "created_at": now,
        }
    finally:
        conn.close()


class TicketInput(BaseModel):
    customer_name: str = Field(description="Name of the person reporting the issue (required)")
    issue_summary: str = Field(description="Short summary of the IntelliDigest problem or request (required)")
    category: str = Field(description=_TICKET_CATEGORY_HELP)
    priority: str = Field(description="Priority: Critical, High, Medium, or Low", default="Medium")
    suggested_solution: str = Field(
        description="Suggested solution based on knowledge base", default=""
    )


@tool("create_ticket", args_schema=TicketInput)
def create_ticket_tool_func(
    customer_name: str,
    issue_summary: str,
    category: str,
    priority: str = "Medium",
    suggested_solution: str = "",
) -> str:
    """
    **This is the only way to create a real ticket id.** Persist a row in SQLite (Tickets panel).
    After the user confirms they want a ticket filed, you **must** call this tool—do not
    describe a fake `TKT-...` id in prose without calling it. Use after intake (name, scope,
    evidence) unless they gave a full brief and asked to file immediately.
    """
    try:
        ticket = create_ticket_in_db(
            customer_name=customer_name,
            issue_summary=issue_summary,
            category=category,
            priority=priority,
            suggested_solution=suggested_solution,
        )
        return (
            f"✅ Ticket Created Successfully!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Ticket ID: {ticket['id']}\n"
            f"Customer: {ticket['customer_name']}\n"
            f"Category: {ticket['category']}\n"
            f"Priority: {ticket['priority']}\n"
            f"Status: {ticket['status']}\n"
            f"Summary: {ticket['issue_summary']}\n"
            f"Suggested Solution: {ticket['suggested_solution']}\n"
            f"Created: {ticket['created_at']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        return f"Error creating ticket: {str(e)}"


def get_all_tickets() -> list:
    """Return all tickets, newest first."""
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_ticket_by_id(ticket_id: str) -> dict | None:
    """Return one ticket by id or None."""
    conn = _get_connection()
    try:
        cur = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_ticket_in_db(
    ticket_id: str,
    customer_name: str | None = None,
    issue_summary: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    suggested_solution: str | None = None,
    status: str | None = None,
) -> dict | None:
    """Update allowed fields; returns updated row or None if missing."""
    existing = get_ticket_by_id(ticket_id)
    if not existing:
        return None
    now = datetime.now(timezone.utc).isoformat()
    fields: list[str] = []
    values: list = []
    for col, val in (
        ("customer_name", customer_name),
        ("issue_summary", issue_summary),
        ("category", category),
        ("priority", priority),
        ("suggested_solution", suggested_solution),
        ("status", status),
    ):
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return existing
    fields.append("updated_at = ?")
    values.append(now)
    values.append(ticket_id)
    conn = _get_connection()
    try:
        conn.execute(
            f"UPDATE tickets SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()
    return get_ticket_by_id(ticket_id)


def close_ticket_in_db(ticket_id: str) -> dict | None:
    """Set status to Closed."""
    return update_ticket_in_db(ticket_id, status="Closed")


def finalize_close_ticket(ticket_id: str, resolution_note: str = "") -> dict | None:
    """Close ticket; optional note is appended to suggested_solution."""
    tid = ticket_id.strip()
    existing = get_ticket_by_id(tid)
    if not existing:
        return None
    extra = existing.get("suggested_solution") or ""
    if resolution_note.strip():
        note = resolution_note.strip()
        merged = f"{extra}\n\n[Resolved] {note}".strip() if extra else f"[Resolved] {note}"
        return update_ticket_in_db(tid, status="Closed", suggested_solution=merged)
    return close_ticket_in_db(tid)


class UpdateTicketInput(BaseModel):
    ticket_id: str = Field(description="The ticket id, e.g. TKT-XXXXXXXX")
    customer_name: str = Field(default="", description="New display name, or empty to leave unchanged")
    issue_summary: str = Field(default="", description="New summary, or empty to leave unchanged")
    category: str = Field(default="", description=f"New category, or empty. {_TICKET_CATEGORY_HELP}")
    priority: str = Field(default="", description="Critical, High, Medium, Low, or empty to leave unchanged")
    suggested_solution: str = Field(default="", description="New suggested solution text, or empty")


@tool("update_ticket", args_schema=UpdateTicketInput)
def update_ticket_tool_func(
    ticket_id: str,
    customer_name: str = "",
    issue_summary: str = "",
    category: str = "",
    priority: str = "",
    suggested_solution: str = "",
) -> str:
    """
    Update an existing ticket after the user confirmed what to change.
    Only pass fields that should change; use empty string to leave a field unchanged.
    """
    kwargs = {}
    if customer_name.strip():
        kwargs["customer_name"] = customer_name.strip()
    if issue_summary.strip():
        kwargs["issue_summary"] = issue_summary.strip()
    if category.strip():
        kwargs["category"] = category.strip()
    if priority.strip():
        kwargs["priority"] = priority.strip()
    if suggested_solution.strip():
        kwargs["suggested_solution"] = suggested_solution.strip()
    if not kwargs:
        return "No changes provided for update_ticket."
    row = update_ticket_in_db(ticket_id.strip(), **kwargs)
    if not row:
        return f"Ticket {ticket_id} not found."
    return (
        f"✅ Ticket updated\n{row['id']}\n"
        f"Status: {row['status']}\nSummary: {row['issue_summary'][:200]}"
    )


class CloseTicketInput(BaseModel):
    ticket_id: str = Field(description="Ticket id to close, e.g. TKT-XXXXXXXX")
    resolution_note: str = Field(
        default="",
        description="Short note that the issue is resolved (optional, for suggested_solution append)",
    )


@tool("close_ticket", args_schema=CloseTicketInput)
def close_ticket_tool_func(ticket_id: str, resolution_note: str = "") -> str:
    """
    Mark a ticket Closed after the user confirmed the issue is resolved.
    Optional resolution_note can summarize the fix.
    """
    tid = ticket_id.strip()
    row = finalize_close_ticket(tid, resolution_note)
    if not row:
        return f"Ticket {tid} not found."
    return (
        f"✅ Ticket {tid} closed.\n"
        f"Status: {row['status']}\nUpdated: {row['updated_at']}"
    )


def get_ticket_tool():
    """LangChain tool for ticket creation."""
    return create_ticket_tool_func


def get_update_ticket_tool():
    return update_ticket_tool_func


def get_close_ticket_tool():
    return close_ticket_tool_func
