# IntelliDigest Running Guide & Internal Architecture

Welcome to the detailed guide on how to run **IntelliDigest** and how its internal engine works.

This guide covers the quickest way to launch the app (using Docker) and dives deep into the API, LangChain reasoning agent, and n8n integration.

---

## How to Run the App

The easiest and most reliable way to run IntelliDigest and its automated research workflows is via **Docker Compose**. This will automatically spin up both the FastAPI backend and the n8n automation engine.

### Prerequisites

- [Docker & Docker Compose](https://www.docker.com/products/docker-desktop/) installed.
- API keys for **Groq** and (optionally) **NewsAPI**.

### Step 1: Environment Setup

In the root directory of the project, duplicate the `.env.example` file and name it `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
GROQ_API_KEY=gsk_your_groq_key_here
NEWSAPI_KEY=your_newsapi_key_here
# Optional: local Ollama when Groq rate-limits or errors (see README)
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_FALLBACK_MODEL=qwen2.5:0.5b
```

### Step 2: Launch the Stack

Run the following command to build the Docker image and start the services in detached mode:

```bash
docker compose up -d --build
```

### Step 3: Access the App

Once the containers are running:

1. **IntelliDigest Web App (FastAPI + UI):** Open `http://localhost:8000` in your browser.
2. **n8n Automation Dashboard:** Open `http://localhost:5678` to view and configure automated insight workflows.

To view logs for debugging:

```bash
docker compose logs -f
```

To stop the application:

```bash
docker compose down
```

---

## How it Works Internally

IntelliDigest separates its logic across well-defined modules. While the frontend handles the UI and animations, the Python backend orchestrates the heavy lifting using **LangChain**.

### The API Layer (`server.py`)

`server.py` is a FastAPI application that serves the frontend files and exposes identical REST API endpoints.

- `/api/chat`, `/api/upload`, `/api/news/search`
- **Global States:** When the server starts up, it initializes global instances of the `VectorStoreEngine` and the `ConversationMemory`.

### The Agentic Core (`agents/research_agent.py`)

When a user asks a question via the chat interface, the request is routed to `research_agent.py`.

- **Reasoning Approach:** Instead of using a complex loop-based `AgentExecutor`, IntelliDigest employs a highly-optimized prompt-based approach.
- **Tooling:** The agent runs a semantic search on the ChromaDB vector database. If it finds context, it conditionally constructs its system prompt to ground itself in the retrieved sources. This allows Llama 3.3 to respond reliably without hallucinating tool inputs.

### Knowledge Storage (`vectorstore/` & `ingestion/`)

- Documents (PDFs, text files, Excel sheets) and live NewsAPI articles are ingested through the `document_loader.py` and `news_retriever.py` modules.
- **Chunking:** Texts are split using semantic splitters.
- **Embedding:** Chunks are vectorized locally using HuggingFace's `all-MiniLM-L6-v2` transformer model.
- **Retrieval:** They are stored persistently in the `chroma_db/` folder in the **`intellidigest`** Chroma collection (Chat, Search, research-style RAG).
- **Support KB (separate collection):** The **`intellidigest_support`** collection holds curated customer-service text from `support/kb/*.md`. It is populated once at startup if empty (`support/bootstrap_kb.py`). The Support tab agent searches **only** this collection via `search_support_knowledge_base`—not your uploaded documents or news.

### LLM routing (`chains/llm_factory.py`)

- All primary chat paths use **ChatGroq** with **`RunnableWithFallbacks`** to **ChatOllama**.
- If Groq raises rate limits, timeouts, connection errors, or common API 5xx errors, the same request is retried against Ollama using `OLLAMA_FALLBACK_MODEL` (default `qwen2.5:0.5b`) and `OLLAMA_BASE_URL`.
- Install [Ollama](https://ollama.com), run `ollama serve`, and `ollama pull <model>` for the fallback to succeed when triggered.

### Support tab (`support/`)

- **Persistence:** Tickets are rows in **`data/tickets.db`** (SQLite). The UI **Tickets** drawer lists them; IDs look like `TKT-` + 8 hex chars.
- **Agent:** `support/agent.py` uses LangChain **`AgentExecutor`** with tools: `search_support_knowledge_base`, `classify_issue`, `create_ticket`, and **UI affordance** tools (`show_close_ticket_confirmation_ui`, `show_edit_ticket_confirmation_ui`, `show_new_support_chat_confirmation_ui`). Those tools do **not** change the database; they let the API attach **`ticket_actions`** so the frontend can show confirmation dialogs when the user has asked to close, edit, or start a new chat.
- **REST:** Updates and closes go through **`PATCH /api/tickets/{id}`** and **`POST /api/tickets/{id}/close`** after the user confirms in the modal. The composer bar only exposes **New conversation** (global close/edit shortcuts were removed by design).
- **Prompts & safety:** `support/prompts.py` is grounded in the real app; `support/sanitize_reply.py` strips leaked tool markup from user-visible replies.

### Automation via n8n → Telegram

You can **save assistant replies to Telegram** (or run a test ping) by wiring a Webhook workflow in n8n.

1. In **Tools**, set your **n8n Webhook URL** and **Telegram chat ID** (from `@userinfobot` or `@RawDataBot`). Use **Send test message** to confirm the link (`action: verify_telegram` in the JSON body).
2. After each assistant answer in **Chat** or **Support**, click **Send to Telegram** — the app calls `POST /api/n8n/telegram`, which forwards JSON to your webhook (`action: save_message`, plus `assistant_message`, `user_message`, `channel`, `persona`).
3. In n8n, branch on `action` and use a **Telegram** node: send `assistant_message` (and optionally prepend `user_message`) to `telegram_chat_id`.
4. Optional: other workflows can still **push text into the KB** by posting to `POST /api/n8n/webhook` with a `content` field (same as before).

**Ready-made workflow:** import [`n8n/intellidigest-telegram.json`](./n8n/intellidigest-telegram.json) and follow [`n8n/README.md`](./n8n/README.md) (bot token, activate, paste webhook URL into IntelliDigest Tools).

---

## Modifying the App

- **Adding API Routes:** Add routes in `server.py` (existing patterns for chat, support, tickets, n8n).
- **Tweak Styles:** Change variables in `frontend/styles.css`.
- **Research chat:** Prompts live in `personas/personas.py` and `agents/research_agent.py` (prompt-grounded retrieval, not `AgentExecutor`).
- **Support chat:** Tool-calling agent in `support/agent.py` + `support/prompts.py`; curated KB under `support/kb/`.
- **Fallback LLM:** Adjust `chains/llm_factory.py` or exception types / env vars as needed.

---

## API quick reference (beyond `/api/chat`)

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/support/chat` | Support agent; body `{ "message", "session_id"? }`; response includes `ticket_actions` when UI tools ran |
| `POST` | `/api/support/sessions/clear` | Clear support memory + agent cache for a `session_id` |
| `GET` | `/api/tickets` | List tickets |
| `GET` | `/api/tickets/{id}` | One ticket |
| `PATCH` | `/api/tickets/{id}` | Partial update (JSON body) |
| `POST` | `/api/tickets/{id}/close` | Close ticket; optional `{ "resolution_note" }` |
| `POST` | `/api/n8n/telegram` | Forward to n8n for Telegram (`verify_telegram`, `save_message`, …) |
| `GET` | `/api/n8n/status` | Webhook URL configured flag |
