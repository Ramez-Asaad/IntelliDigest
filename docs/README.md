# IntelliDigest documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, dual Chroma collections, ingestion and chat/support dataflow (with diagrams). |
| [DOCKERLESS.md](DOCKERLESS.md) | Run the FastAPI app locally without Docker (`uvicorn`, venv). |
| [RUNNING_GUIDE.md](RUNNING_GUIDE.md) | Docker Compose, env (JWT, Google OAuth, SMTP password reset), internal architecture, API overview, n8n → Telegram. |
| [PRODUCTION.md](PRODUCTION.md) | Fly.io (`fly.toml`), HTTPS, CORS (`ALLOWED_ORIGINS`), volumes (`INTELLIDIGEST_PERSIST_DIR`), backups, `/health`, VPS options. |
| [n8n-telegram.md](n8n-telegram.md) | Import workflow, bot token, webhook URL for Telegram forwarding. |

The main project overview and feature list remain in the repository **[README.md](../README.md)**.
