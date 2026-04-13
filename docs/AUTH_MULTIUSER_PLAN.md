# Plan: authentication, authorization, and per-user data

This document is a **roadmap** for making IntelliDigest **multi-tenant**: each signed-in user sees only their own uploads, search results, chat history, and support tickets. It matches the **current codebase** (single global vector store + memory, shared tickets table, client-generated `session_id` for support).

---

## Current state (baseline)

| Area | Today | Risk for multi-user |
|------|--------|----------------------|
| **Main Chroma collection** (`intellidigest`) | Shared by everyone | All users read/write the same chunks |
| **Support Chroma** (`intellidigest_support`) | Shared curated KB | Usually **global** (same FAQs for all); only restrict **writes** if you add user-specific support docs later |
| **Research chat memory** (`ConversationMemory` in `server.py`) | One global instance | All users share one rolling summary/history |
| **Support agent memory** (`support/memory.py`) | Keyed by `session_id` from browser | Not authenticated: IDs are guessable; not durable across devices |
| **Tickets** (`support/tickets.py`) | No `user_id` | Any client listing tickets sees all rows |
| **API** | No auth | Anyone who can reach the server can call any endpoint |

---

## Target model (what “personal data” means)

1. **Identity**: Each request that mutates or reads **private** data must carry a verified **user id** (from JWT, session cookie, or API key).
2. **Authorization**: Every query and tool must **scope** data with that id (or a server-side rule such as “admin sees all”).
3. **Support KB**: Decide explicitly:
   - **Option A (typical)**: `intellidigest_support` stays **global** (product docs); only **tickets** and **support chat transcripts** are per-user.
   - **Option B**: Per-user support snippets (advanced): extra collection or metadata filter—only if you need it.

Below assumes **Option A** unless you mark otherwise in implementation.

---

## Recommended auth approach (pragmatic for FastAPI + SPA)

| Piece | Recommendation | Notes |
|-------|----------------|--------|
| **Protocol** | **JWT access token** (short TTL) + **refresh token** (httpOnly cookie or secure storage) | Stateless API; scales horizontally if you add more uvicorn workers later |
| **Alternative** | Server-side sessions (Redis) + session cookie | Simpler revocation; needs Redis in production |
| **Passwords** | **bcrypt** or **argon2** via `passlib`; store only hashes | Add `users` table with `email`, `password_hash`, `id` (UUID) |
| **OAuth** | Optional phase 2: Google/GitHub via OAuth2 redirect | Same `users` table; link `oauth_sub` or separate `accounts` table |

**Frontend**: Login/register views; store access token (memory + `sessionStorage` or secure cookie strategy you choose); send `Authorization: Bearer <token>` on all API calls except `/`, `/health`, and auth routes.

---

## Data isolation strategies

### 1) Main knowledge base (`intellidigest`)

**Preferred**: **Metadata filter** on every read/write.

- Add **`user_id`** (string UUID) to Chroma document metadata for all chunks from uploads, news, and n8n ingest.
- `VectorStoreEngine.search_similar`, `add_texts`, `add_articles`, `clear_collection`, and stats must accept **`user_id`** and use LangChain/Chroma **`where`** filters (or equivalent) so retrieval only returns that user’s chunks.

**Alternative**: One Chroma **collection per user** (e.g. `intellidigest_u_{user_id}`). Simpler mental model; more collections to manage; migration and backup differ.

**Bootstrap**: New users start with **empty** main KB unless you copy a template (optional).

### 2) Research chat memory

- Replace the single global `memory` with a **dict or LRU** keyed by **`user_id`**, or persist summaries in SQLite/Redis keyed by `user_id`.
- Cap memory per user (max turns / TTL) to avoid unbounded RAM.

### 3) Support agent memory + `session_id`

- Tie support memory to **`user_id`** (and optionally a **thread id** for multiple support conversations): e.g. `support_memory:{user_id}:{thread_id}`.
- Stop trusting raw client `session_id` as the only secret; derive identity from JWT first.

### 4) Tickets

- Add **`user_id`** column to `tickets`; migration for existing rows (assign to NULL or a single “legacy” user).
- **All** reads/writes (`get_all_tickets`, `get_ticket_by_id`, `update_ticket_in_db`, agent tools) must filter or check `user_id`.
- LangChain **`get_ticket`** / list tools must only return tickets for the current user.

### 5) Support vector store (`intellidigest_support`)

- **Read**: Unchanged global curated KB for all users (FAQ), **unless** you add per-user docs later.
- **Write**: N/A for most apps; if you ever ingest user-specific support docs, tag with `user_id` like the main KB.

### 6) n8n / Telegram

- Webhook payloads should include or map to **`user_id`** (e.g. Telegram `chat_id` → user mapping table) before ingesting into a user’s main collection.
- Document that unauthenticated webhooks are **unsafe** in multi-tenant mode—use shared secrets or signed payloads.

---

## API surface changes (summary)

1. **New routes**: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout` (optional).
2. **Dependency**: `get_current_user()` FastAPI dependency: decode JWT → `User` or 401.
3. **Protect routes**: All of `/api/chat`, `/api/upload`, `/api/news/search`, `/api/search`, `/api/clear`, `/api/chat/*`, `/api/support/*`, `/api/tickets*`, `/api/n8n/*` (as applicable) require auth **except** a deliberate public demo mode behind `ALLOW_PUBLIC_DEMO=true` (optional).
4. **CORS**: After auth, restrict `ALLOWED_ORIGINS` and avoid `*` with credentials.

---

## Phased implementation checklist

Use this as a **todo list**; order matters within each phase.

### Phase 0 — Product decisions

- [ ] Confirm **support KB** stays global (Option A) vs per-user (Option B).
- [ ] Decide **auth methods** for v1: email/password only vs OAuth from day one.
- [ ] Decide **deployment**: single VM (SQLite OK?) vs managed Postgres for users + tickets.
- [ ] Define **admin** role: view all tickets / impersonation? (Optional.)

### Phase 1 — Users and tokens (backend)

- [ ] Add `users` table (id, email unique, password_hash, created_at).
- [ ] Implement password hashing and verification.
- [ ] Issue JWT (payload: `sub` = user id, `exp`, optional `jti` for revocation).
- [ ] Add `get_current_user` dependency and 401/403 handling.
- [ ] Environment: `JWT_SECRET`, `JWT_ALGORITHM`, access/refresh TTLs.

### Phase 2 — Scope tickets

- [ ] Migration: add `user_id` to `tickets`; backfill strategy for existing data.
- [ ] Update all ticket queries and REST handlers to filter by `user_id`.
- [ ] Update support **tools** in `support/tickets.py` to pass `user_id` from context (inject via agent or closure).

### Phase 3 — Scope main Chroma + research flow

- [ ] Add `user_id` to metadata on `add_texts` / `add_articles` / n8n ingest paths.
- [ ] Implement **filtered** `search_similar` and **user-scoped** `clear_collection` / counts.
- [ ] Refactor global `ConversationMemory` to **per-user** (in-memory dict or DB).
- [ ] Update `create_research_agent` usage so retrieval uses scoped store or filtered search.

### Phase 4 — Support chat

- [ ] Key `support/memory.py` (and agent cache) by `user_id` (+ optional thread id).
- [ ] Remove or harden client-only `session_id` (replace with server-issued thread id after login).

### Phase 5 — Frontend

- [ ] Login / register UI; store token; attach header to `fetch` calls in `frontend/app.js`.
- [ ] Handle 401: redirect to login, clear token.
- [ ] Remove reliance on anonymous `supportSessionId` for security (optional: keep only as UI thread id **after** auth).

### Phase 6 — Production hardening

- [ ] HTTPS only; secure cookie flags if using cookies.
- [ ] Rate limit `/api/auth/login` and sensitive routes.
- [ ] Audit logs for ticket access (optional).
- [ ] Backup/restore: document per-user Chroma backup if using metadata filtering (single DB file still, but logical partitions).

---

## Testing checklist

- [ ] User A uploads a doc; User B’s search/chat must not return A’s chunks.
- [ ] User A creates ticket; User B cannot `GET /api/tickets` or `PATCH` A’s id.
- [ ] Token expiry: refresh flow works; expired token gets 401.
- [ ] Clear KB / clear chat only affects the authenticated user.

---

## Optional follow-ups

- **Postgres** for users and tickets when SQLite becomes a bottleneck.
- **Row-level security** if you move DB to Postgres.
- **Organization/team** accounts (shared KB within a team).

---

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — current components and dataflow.
- [PRODUCTION.md](PRODUCTION.md) — HTTPS, CORS, secrets.
