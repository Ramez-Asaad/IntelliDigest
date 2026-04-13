# IntelliDigest Running Guide & Internal Architecture

Welcome to the detailed guide on how to run **IntelliDigest** and how its internal engine works.

This guide covers how to launch the app (Docker or local), environment variables (including JWT and optional Google sign-in), the API, LangChain agent, and optional n8n integration.

---

## How to Run the App

### Docker Compose (recommended)

Two compose files (repository root):

| File | What it runs |
|------|----------------|
| [`docker-compose.yml`](../docker-compose.yml) (default) | **IntelliDigest only** — lighter, good for production (e.g. Oracle Cloud Free Tier). |
| [`docker-compose.with-n8n.yml`](../docker-compose.with-n8n.yml) | App **+** bundled **n8n** on port 5678 (Telegram / webhook lab stack). |

### Prerequisites

- [Docker & Docker Compose](https://www.docker.com/products/docker-desktop/) installed.
- API keys for **Groq** and (optionally) **NewsAPI**.
- **JWT auth:** set **`JWT_SECRET`** in `.env` (long random string) so users can register, log in, and call protected APIs.
- **Google sign-in (optional):** OAuth client in Google Cloud; see [Google sign-in (optional)](#google-sign-in-optional) below.

### Step 1: Environment Setup

In the root directory of the project, duplicate the `.env.example` file and name it `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
GROQ_API_KEY=gsk_your_groq_key_here
NEWSAPI_KEY=your_newsapi_key_here
JWT_SECRET=your-long-random-secret
# Optional: local Ollama when Groq rate-limits or errors (see README)
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_FALLBACK_MODEL=qwen2.5:0.5b
```

User accounts and passwords live in **`data/auth.db`**; support tickets in **`data/tickets.db`**. Main knowledge-base vectors use **per-user** Chroma collections under `chroma_db/` (see [ARCHITECTURE.md](ARCHITECTURE.md)).

### Google sign-in (optional)

The web UI can show **Continue with Google** when Google OAuth env vars are set. Flow: browser → `GET /api/auth/google` → Google consent → `GET /api/auth/google/callback` → app issues the same **JWT** as email/password login and redirects to the app root with `token` and `email` query parameters (the frontend stores them and clears the URL).

1. **Google Cloud Console** → **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID** → type **Web application**.
2. Under **Authorized redirect URIs**, add exactly (adjust host/port to match how you open the app):
   - `http://127.0.0.1:8000/api/auth/google/callback`  
   Use the **same host** in the browser (e.g. always `127.0.0.1`, not mixed with `localhost`), or add both URIs in Google if you switch.
3. Copy the **Client ID** and **Client secret** into `.env`:

```env
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
OAUTH_REDIRECT_BASE=http://127.0.0.1:8000
OAUTH_FRONTEND_REDIRECT_BASE=http://127.0.0.1:8000
```

`OAUTH_REDIRECT_BASE` must be **only** the origin (e.g. `http://127.0.0.1:8000`), **not** the full callback path. The server builds `redirect_uri` as `{OAUTH_REDIRECT_BASE}/api/auth/google/callback`. If you put the full callback URL in `OAUTH_REDIRECT_BASE`, Google will see a doubled path and return `redirect_uri_mismatch`. `OAUTH_FRONTEND_REDIRECT_BASE` is where users land after login (usually the same origin). If omitted, the server derives both from the request.

4. **Session cookie:** OAuth uses a short-lived session for the state parameter. Set **`SESSION_SECRET`** (or reuse **`JWT_SECRET`**) so `SessionMiddleware` can sign cookies.

5. Restart the API, open the app, and confirm **`GET /api/auth/config`** returns `"google_enabled": true` before testing the button.

**Production:** use HTTPS origins in Google Console and set `OAUTH_*` to your public URL; keep **`ALLOWED_ORIGINS`** aligned with the SPA origin (see [PRODUCTION.md](PRODUCTION.md)).

**Troubleshooting Google login:** If you see `invalid_token` / *“issued in the future”*, your **PC clock is behind** Google’s servers. On Windows: **Settings → Time & language → Date & time → Sync now** (enable automatic time). The app allows **10 minutes** of skew by default (`OAUTH_JWT_LEEWAY=600`); increase only if needed after syncing time.

### Step 2: Launch the stack

**App only (default):**

```bash
docker compose up -d --build
```

**App + n8n:**

```bash
docker compose -f docker-compose.with-n8n.yml up -d --build
```

### Step 3: Access the services

1. **IntelliDigest:** `http://localhost:8000`
2. **n8n** (only if you used `docker-compose.with-n8n.yml`): `http://localhost:5678`

To view logs for debugging:

```bash
docker compose logs -f
```

(Use the same `-f docker-compose.with-n8n.yml` if you started that stack.)

To stop:

```bash
docker compose down
```

If you started the n8n stack, use `docker compose -f docker-compose.with-n8n.yml down`.

---

## How it Works Internally

IntelliDigest separates its logic across well-defined modules. While the frontend handles the UI and animations, the Python backend orchestrates the heavy lifting using **LangChain**.

### The API Layer (`server.py`)

`server.py` is a FastAPI application that serves the frontend files and exposes identical REST API endpoints.

- `/api/chat`, `/api/upload`, `/api/news/search`
- **Startup:** The server initializes a shared `VectorStoreEngine` (per-user main Chroma collections + shared support KB), a **research agent** factory, and **per-user** conversation memory after login. Protected routes require a **Bearer JWT** (`Authorization` header).

### The Agentic Core (`agents/research_agent.py`)

When a user asks a question via the chat interface, the request is routed to `research_agent.py`.

- **Reasoning Approach:** Instead of using a complex loop-based `AgentExecutor`, IntelliDigest employs a highly-optimized prompt-based approach.
- **Tooling:** The agent runs a semantic search on the ChromaDB vector database. If it finds context, it conditionally constructs its system prompt to ground itself in the retrieved sources. This allows Llama 3.3 to respond reliably without hallucinating tool inputs.

### Knowledge Storage (`vectorstore/` & `ingestion/`)

- Documents (PDFs, text files, Excel sheets) and live NewsAPI articles are ingested through the `document_loader.py` and `news_retriever.py` modules.
- **Chunking:** Texts are split using semantic splitters.
- **Embedding:** Chunks are vectorized locally using HuggingFace's `all-MiniLM-L6-v2` transformer model.
- **Retrieval:** Chunks are stored under `chroma_db/` in **per-user** main collections (`intellidigest_u_*`) for Chat, Search, and research-style RAG.
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

**Ready-made workflow:** import [`n8n/intellidigest-telegram.json`](../n8n/intellidigest-telegram.json) and follow [n8n-telegram.md](n8n-telegram.md) (bot token, activate, paste webhook URL into IntelliDigest Tools).

---

For **HTTPS, CORS (`ALLOWED_ORIGINS`), backups, health checks, and Ollama strategy** on a real server, see **[PRODUCTION.md](PRODUCTION.md)**.

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
| `POST` | `/api/auth/register` | Create account; returns JWT (public) |
| `POST` | `/api/auth/login` | Email/password; returns JWT (public) |
| `GET` | `/api/auth/config` | `{ "google_enabled": bool }` for UI (public) |
| `GET` | `/api/auth/google` | Start Google OAuth (browser redirect; public) |
| `GET` | `/api/auth/google/callback` | Google OAuth callback (browser; public) |
| `POST` | `/api/support/chat` | Support agent; body `{ "message", "session_id"? }`; response includes `ticket_actions` when UI tools ran |
| `POST` | `/api/support/sessions/clear` | Clear support memory + agent cache for a `session_id` |
| `GET` | `/api/tickets` | List tickets |
| `GET` | `/api/tickets/{id}` | One ticket |
| `PATCH` | `/api/tickets/{id}` | Partial update (JSON body) |
| `POST` | `/api/tickets/{id}/close` | Close ticket; optional `{ "resolution_note" }` |
| `POST` | `/api/n8n/telegram` | Forward to n8n for Telegram (`verify_telegram`, `save_message`, …) |
| `GET` | `/api/n8n/status` | Webhook URL configured flag |
