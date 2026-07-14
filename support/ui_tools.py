"""
UI affordance tools for the Support agent — they do not mutate tickets.

They only signal the API to attach confirmation buttons after validating ticket_id.
"""

import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from support.tickets import get_all_tickets, get_ticket_by_id


class TicketIdInput(BaseModel):
    ticket_id: str = Field(
        description="Existing ticket id from the Tickets panel (e.g. TKT-XXXXXXXX)."
    )


class NewChatUIArgs(BaseModel):
    unused: str = Field(default="", description="Leave empty.")


_PLACEHOLDER_TICKET_RE = re.compile(r"^TKT-[Xx]{8}$")


def _resolve_ticket_id(ticket_id: str, user_id: str) -> tuple[str, dict | None]:
    """
    Resolve ticket_id for UI actions.
    If the model passes placeholder ids like TKT-XXXXXXXX, use the newest open ticket.
    """
    tid = ticket_id.strip().upper()
    row = get_ticket_by_id(tid, user_id)
    if row:
        return tid, row

    if _PLACEHOLDER_TICKET_RE.fullmatch(tid):
        tickets = get_all_tickets(user_id)
        for t in tickets:
            if (t.get("status") or "").strip().lower() != "closed":
                real_id = str(t.get("id", "")).strip().upper()
                if real_id:
                    return real_id, t
        if tickets:
            real_id = str(tickets[0].get("id", "")).strip().upper()
            if real_id:
                return real_id, tickets[0]

    return tid, None


def make_show_close_ticket_ui_tool(user_id: str):
    @tool("show_close_ticket_confirmation_ui", args_schema=TicketIdInput)
    def show_close_ticket_confirmation_ui(ticket_id: str) -> str:
        """
        Call only when the user clearly asked to close or resolve a specific ticket.
        The app will show a confirmation dialog; the ticket is not closed until they confirm there.
        """
        tid, row = _resolve_ticket_id(ticket_id, user_id)
        if not row:
            return (
                f"No ticket `{tid}` was found. Ask the user to open the Tickets panel and copy "
                "the exact id, or say they can use **Close ticket…** in the composer bar."
            )
        if (row.get("status") or "").strip().lower() == "closed":
            return (
                f"Ticket `{tid}` is already closed. Acknowledge that—do not imply it is still open."
            )
        return (
            "A **close ticket** confirmation can appear in the UI for this id. "
            "Tell the user to review the dialog and click **Confirm** if they want to close it."
        )

    return show_close_ticket_confirmation_ui


def make_show_edit_ticket_ui_tool(user_id: str):
    @tool("show_edit_ticket_confirmation_ui", args_schema=TicketIdInput)
    def show_edit_ticket_confirmation_ui(ticket_id: str) -> str:
        """
        Call only when the user clearly asked to change or update a specific ticket.
        The app will show an edit confirmation form; nothing is saved until they confirm.
        """
        tid, row = _resolve_ticket_id(ticket_id, user_id)
        if not row:
            return (
                f"No ticket `{tid}` was found. Ask the user to copy the id from the Tickets panel, "
                "or use **Edit ticket…** in the composer bar."
            )
        return (
            "An **edit ticket** form can appear in the UI for this id. "
            "Tell the user to update the fields and click **Confirm** to save."
        )

    return show_edit_ticket_confirmation_ui


@tool("show_new_support_chat_confirmation_ui", args_schema=NewChatUIArgs)
def show_new_support_chat_confirmation_ui(unused: str = "") -> str:
    """
    Call only when the user clearly asked to start a fresh support conversation / new ticket thread.
    The app will ask for confirmation before clearing the chat session.
    """
    return (
        "A **new support chat** confirmation can appear. "
        "Tell the user to confirm in the dialog if they want to clear this conversation."
    )


def get_show_new_chat_ui_tool():
    return show_new_support_chat_confirmation_ui
