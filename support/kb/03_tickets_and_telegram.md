# Tickets, Telegram, and n8n (support KB)

## Tickets

- Tickets are stored in SQLite at `data/tickets.db`.
- The **Tickets** button in the top bar opens a panel listing ticket id, status, summary, category, and priority.
- Ticket ids look like `TKT-` followed by 8 hexadecimal characters. **Only ids shown in the Tickets panel or returned by the assistant after a successful create are valid.**

## Closing or editing

- **Closing** or **editing** a ticket from the UI uses confirmation dialogs so changes are intentional.
- Users can also use **Close ticket…** or **Edit ticket…** in the Support composer bar; those flows ask for confirmation before calling the API.

## Telegram (n8n)

- **Tools → Telegram via n8n** stores webhook URL and Telegram chat ID in the browser (localStorage) and can send test or saved messages through a user-configured n8n workflow.
- Endpoint `POST /api/n8n/telegram` forwards payloads to the webhook; see `n8n/README.md` in the repo.

## Environment

- `GROQ_API_KEY` — required for LLM features.
- `NEWSAPI_KEY` — required for live news fetch.
- Optional: `SUPPORT_LLM_MODEL` to override the default Groq model for the Support tab.
