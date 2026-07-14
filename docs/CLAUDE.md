# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Quick Command Reference

### Environment Setup
```bash
# Copy environment template and configure with API keys
cp .env.example .env
# Edit .env with: GROQ_API_KEY, JWT_SECRET, NEWSAPI_KEY (optional), etc.

# Create and activate virtual environment (Python 3.11+)
python -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Running the Application

**Docker (recommended for production):**
```bash
docker compose up -d --build              # App only
docker compose -f docker-compose.with-n8n.yml up -d --build  # App + n8n
docker compose logs -f                    # View logs
docker compose down                       # Stop and remove containers
```

**Local development (without Docker):**
```bash
# In virtual environment with dependencies installed
python server.py
# App runs at http://localhost:8000
```

**Streamlit UI (legacy, for local experimentation):**
```bash
streamlit run app.py
```

### Testing & Code Quality
```bash
pytest                        # Run all tests
pytest -v                     # Verbose output
pytest -k "test_name"         # Run specific test
pytest tests/test_auth.py     # Run single test file
```

### Database & Persistence
```bash
# Data location depends on INTELLIDIGEST_PERSIST_DIR in .env (default: ./data/)
# Chroma vector store: ./chroma_db/
# SQLite databases: ./data/auth.db, ./data/tickets.db

# To reset data (development only)
rm -rf ./chroma_db ./data/tickets.db  # Remove Chroma and tickets
rm ./data/auth.db                      # Remove user accounts (if starting fresh)
```

---

## Architecture Overview

### System Design
**IntelliDigest** is a RAG (Retrieval-Augmented Generation) research assistant built with:
- **Backend:** FastAPI (`server.py`) — single-process app that initializes all components on startup
- **Frontend:** Vanilla HTML/CSS/JS (`frontend/`) — no build step required
- **Embedding & Storage:** ChromaDB with HuggingFace embeddings (`sentence-transformers/all-MiniLM-L6-v2`)
- **LLM:** Groq (primary, fast inference) + optional Ollama fallback when rate-limited
- **Database:** SQLite for user accounts and support tickets
- **Orchestration:** Optional n8n for Telegram automation

### Two Separate Knowledge Bases
This is a critical architectural decision: **IntelliDigest uses two distinct Chroma collections:**

1. **`intellidigest_*` (per-user main KB):** Contains user uploads, news articles, and n8n-ingested content. Each authenticated user gets their own collection (suffix = user ID). Used by the research chat flow.

2. **`intellidigest_support`:** Shared support-only KB with curated markdown files from `support/kb/*.md`. Bootstrapped on first run. Used exclusively by the support agent—user uploads never leak into support responses.

**Why this split?** Keeps private documents private while allowing support agents to reference curated knowledge bases.

### Data Flow Layers

#### Layer 1: Ingestion → Vector Store
Users upload documents (PDF, DOCX, Excel, TXT) or search news → documents are parsed, semantically chunked, embedded, and stored in the user's Chroma collection.

#### Layer 2: Research Chat
User question → semantic search in main KB → retrieval of context → LLM generation with persona injection and rolling conversation memory → grounded answer with source citations.

#### Layer 3: Support Agent
User support message → tool-calling AgentExecutor → searches support-only KB only (via `support/retriever.py`) → classifies issue → creates ticket in SQLite → signals frontend for UI confirmations → no silent DB mutations.

#### Layer 4: Optional n8n Telegram
External `POST /api/n8n/telegram` webhook → forwards chat/support replies to user-hosted n8n → Telegram delivery. Does not replace core logic.

---

## Module Organization & What Each File Does

### Core Application
- **`server.py`**: Main FastAPI app. Initializes components on startup (lifespan), defines all REST endpoints, serves frontend.
- **`paths.py`**: Centralizes filepath constants (INTELLIDIGEST_PERSIST_DIR, Chroma and SQLite locations).

### Authentication & Users (`auth/`)
- **`auth/users.py`**: SQLite user DB (email, password hash, created_at).
- **`auth/jwt_handler.py`**: JWT token creation/validation, credentials extraction.
- **`auth/oauth.py`**: Google OAuth flow integration (Google Console → callback → JWT issuance).
- **`auth/password_reset.py`**: Time-limited reset tokens, SMTP email delivery.

### Vector Store & Embeddings (`vectorstore/`)
- **`vectorstore/engine.py`**: Core abstraction. Manages two Chroma collections (main + support), semantic search, add_texts/add_articles methods. Handles per-user collection naming and embedding model initialization.

### Ingestion (`ingestion/`)
- **`ingestion/document_loader.py`**: Multi-format document parsing (PDF → PyPDF2, DOCX → python-docx, Excel → openpyxl, TXT → raw). Semantic chunking with sentence-level boundaries.
- **`ingestion/news_retriever.py`**: NewsAPI client to fetch and parse current articles.

### LLM & Chains (`chains/`)
- **`chains/llm_factory.py`**: Creates ChatGroq (primary) wrapped with RunnableWithFallbacks to ChatOllama (fallback on rate-limit/error).
- **`chains/qa_chain.py`**: LCEL RAG pattern (retriever → prompt → LLM → parser). Strict RAG pipeline alternative to the research agent.
- **`chains/summarizer.py`**: Stuff chain (brief) and map-reduce chain (detailed) for document summarization.
- **`chains/prompts.py`**: Shared LangChain prompt templates.

### Research Agent (`agents/`)
- **`agents/research_agent.py`**: Prompt-based orchestration (not AgentExecutor). Retrieves context from main KB, injects persona, manages rolling summary memory, returns grounded answer + sources.

### Support (`support/`)
- **`support/agent.py`**: Tool-calling AgentExecutor with LangChain tools: `search_support_knowledge_base`, `classify_issue`, `create_ticket`, `get_ticket`, plus UI affordance tools.
- **`support/retriever.py`**: Chroma retriever that searches **only** the support KB collection.
- **`support/tickets.py`**: SQLite schema and CRUD for support tickets (create, list, update, close).
- **`support/bootstrap_kb.py`**: Loads all `.md` files from `support/kb/` into the support Chroma collection on app startup (if the collection is empty).
- **`support/prompts.py`**: IntelliDigest-grounded system prompt for the support agent.
- **`support/ui_tools.py`**: Tools that signal the frontend (show_confirm_close, show_edit_ticket, etc.) without writing to the database.
- **`support/kb/`**: Curated markdown files (FAQ, troubleshooting, etc.) ingested into the support-only vector store.

### Conversation Memory (`memory/`)
- **`memory/conversation.py`**: Maintains rolling chat history. Compresses older exchanges into a summary (using LLM) when history grows, keeping only recent turns verbatim. Prevents context window bloat in multi-turn conversations.

### Personas (`personas/`)
- **`personas/personas.py`**: Five tone presets (Tech, Business, Academic, Casual, Political). Injected into research agent prompts to modulate response style.

### Frontend (`frontend/`)
- **`frontend/index.html`**: App shell with auth flow, tabs (Chat, News, Search, Support, Tickets), modals for confirmations. Single-page app; no build step.
- **`frontend/app.js`**: UI state, API calls, real-time updates (chat, tickets, persona switching).
- **`frontend/styles.css`**: Design system tokens (colors, spacing, typography, animations) aligned with DESIGN.md.

### Tests (`tests/`)
- **`tests/test_auth.py`**: JWT, user registration, login, password reset flows.
- Other test files as added.

### Documentation (`docs/`)
- **`ARCHITECTURE.md`**: System design, data flows, module map (read this first for deep dives).
- **`RUNNING_GUIDE.md`**: Deployment, environment variables, Google OAuth setup.
- **`DOCKERLESS.md`**: Running locally without Docker.
- **`n8n-telegram.md`**: n8n workflow setup for Telegram forwarding.
- **`README.md`**: Feature list, quick start, tech stack.

### (Deprecated/Optional)
- **`app.py`**: Streamlit UI. Legacy; the main UX is the custom HTML/CSS/JS frontend.
- **`n8n/`**: Sample n8n workflow JSON for Telegram integration.

---

## Key Development Patterns

### Authentication Guards
Protected endpoints require `Depends(verify_token)` or `Depends(verify_token_optional)`. The token is extracted from the `Authorization: Bearer <token>` header or cookies.

### Per-User Data Isolation
The research agent and vector store are user-aware: each registered user gets their own Chroma collection (`intellidigest_u_<user_id>`). Support KB is shared (`intellidigest_support`).

### Error Handling & Fallbacks
- **Groq rate limits:** Caught by `RunnableWithFallbacks` → chains automatically retry with Ollama.
- **Missing GROQ_API_KEY:** Components remain uninitialized. Endpoints that need them fail gracefully with a message.
- **Missing required env vars:** Startup warnings logged; some features (e.g., Google OAuth) disabled silently if config is incomplete.

### Response Format
Most endpoints return JSON with `{"response": "...", "sources": [...], ...}` or `{"status": "ok", "data": ...}`. Errors return HTTP error codes + JSON body with `{"error": "message"}`.

### Conversation Memory Compression
Long chat histories are compressed into a summary via LLM to save context. Recent exchanges stay verbatim. Configure compression threshold in `memory/conversation.py` (default: after ~10 exchanges).

### Support Agent Tools Are Composable
UI affordance tools (e.g., `show_confirm_close`) do **not** mutate the database—they only signal the frontend to render a confirmation modal. Actual mutations (close ticket, edit ticket) happen via REST endpoints after user confirmation.

---

## Configuration & Environment Variables

See `.env.example` for the complete list. Key ones:

- **`GROQ_API_KEY`** (required): Groq inference API key.
- **`JWT_SECRET`** (required): Long random string for signing JWT tokens.
- **`NEWSAPI_KEY`** (optional): News search feature.
- **`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`**, `OAUTH_REDIRECT_BASE` (optional): Google OAuth.
- **`SESSION_SECRET`** (optional): OAuth session signing (reuse `JWT_SECRET` if omitted).
- **`OLLAMA_BASE_URL`, `OLLAMA_FALLBACK_MODEL`** (optional): Local LLM fallback.
- **`INTELLIDIGEST_PERSIST_DIR`** (optional): Where Chroma and SQLite data live (default: `./data/`).
- **`SMTP_*`** (optional): Email server for password resets.
- **`ALLOWED_ORIGINS`** (optional, important for CORS): Comma-separated list of allowed client origins.
- **`N8N_WEBHOOK_URL`** (optional): n8n webhook for Telegram integration.

---

## Testing Patterns

### Unit / Integration Tests
- Auth tests verify JWT creation, user registration, login, password reset.
- Run with `pytest` or `pytest -v` for verbose output.
- Tests run against real local SQLite (not mocked) to catch actual schema issues early.

### Manual Integration Testing
1. Register a new account via the UI.
2. Upload a PDF.
3. Ask a question in Chat → verify retrieval from your document.
4. Submit a support message → verify ticket creation + support KB search.
5. (Optional) Set up Telegram workflow and test n8n forwarding.

---

## Performance Considerations

- **First cold start:** Sentence-transformers model loads from HuggingFace (~500 MB). Subsequent starts are much faster.
- **Chroma persistence:** Vectors are stored locally; no external DB required. Scales to thousands of documents per user on a single instance.
- **Single worker:** The typical setup is one Python process. Scale-out requires multiple instances with shared volumes or external vector store (not in this repo's scope).
- **Token limits:** Groq requests (+ conversation memory) must fit within 8K context. Conversation memory compression kicks in to manage long chats.

---

## Important Notes

1. **Support KB is curated.** Add `.md` files to `support/kb/` and restart the app to bootstrap them into the shared support collection.
2. **No need to rebuild frontend.** HTML/CSS/JS is served as-is; changes are instant (refresh browser).
3. **Dockerfile uses Python 3.13.** Local dev can use 3.11+ per `requirements.txt`.
4. **design.md tokens:** Inspect `DESIGN.md` and `frontend/styles.css` before styling changes to maintain visual consistency.
5. **Reserved feature:** The "research agent" is the primary chat UX. The RAG chain in `chains/qa_chain.py` exists for comparison but is not exposed in the main UI.

---

## Debugging Tips

- **Enable debug logs:** Add `import logging; logging.basicConfig(level=logging.DEBUG)` to see LangChain internals.
- **Check Chroma persistence:** `./chroma_db/` contains SQLite indices. Inspect with DB browser if needed.
- **Inspect LLM calls:** The research agent logs retrieved chunks and the final prompt sent to Groq.
- **Test Ollama fallback:** Set `GROQ_API_KEY` to a dummy value to force fallback.
- **OAuth clock skew:** If Google login fails with "issued in the future," sync your system clock.
