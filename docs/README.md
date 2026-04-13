# IntelliDigest documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, dual Chroma collections, ingestion and chat/support dataflow (with diagrams). |
| [AUTH_MULTIUSER_PLAN.md](AUTH_MULTIUSER_PLAN.md) | Roadmap: authn/z, per-user Chroma/tickets/memory, phased todos. |
| [DOCKERLESS.md](DOCKERLESS.md) | Run the FastAPI app locally without Docker (`uvicorn`, venv). |
| [RUNNING_GUIDE.md](RUNNING_GUIDE.md) | Docker Compose, env (JWT, Google OAuth), internal architecture, API overview, n8n → Telegram. |
| [PRODUCTION.md](PRODUCTION.md) | HTTPS, CORS (`ALLOWED_ORIGINS`), volumes, backups, `/health`, Oracle / VPS. |
| [n8n-telegram.md](n8n-telegram.md) | Import workflow, bot token, webhook URL for Telegram forwarding. |

The main project overview and feature list remain in the repository **[README.md](../README.md)**.
