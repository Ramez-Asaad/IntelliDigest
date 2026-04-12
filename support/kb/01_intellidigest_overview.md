# IntelliDigest — support reference (overview)

IntelliDigest is a local-first FastAPI web app with a static HTML/JS frontend. Default dev URL: `http://127.0.0.1:8000`.

## Tabs

- **Chat** — RAG over the knowledge base with Groq (Llama-class) and optional personas. Needs `GROQ_API_KEY`.
- **News** — Fetches articles via NewsAPI and ingests them into the KB. Needs `NEWSAPI_KEY`.
- **Search** — Semantic search over the same embedded collection as Chat.
- **Support** — This assistant; tickets live in SQLite (`data/tickets.db`) and appear in the **Tickets** panel.

There is no user login, billing, or Stripe in this codebase.

## Knowledge bases (important)

- **Main KB** (Chat / Search / uploads / news) — user content.
- **Support KB** — Curated customer-service documents used only by the Support tab search tool. It does not automatically include user uploads.

## Tools drawer

Users can upload PDF, DOCX, XLSX, TXT, clear the KB, fetch news, and configure **Telegram via n8n** (webhook URL + chat ID).
