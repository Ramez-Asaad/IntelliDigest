# Troubleshooting (support KB)

## 503 / "Agent not initialized"

- Ensure `GROQ_API_KEY` is set in `.env` in the project root (or environment).
- Restart the server after changing `.env` (`uvicorn server:app` or your process manager).
- If using Docker, pass env vars into the container.

## News fetch fails / NEWSAPI_KEY

- The News tab requires `NEWSAPI_KEY` from https://newsapi.org/
- Without it, the API returns 503 for news search/ingest.

## Vector store / Chroma

- Embeddings use `sentence-transformers/all-MiniLM-L6-v2` by default.
- Main collection name: `intellidigest`. Support-only collection: `intellidigest_support` (curated support docs).
- Persist directory: `chroma_db/` under the repo.

## Upload issues

- Supported upload types: PDF, DOCX, XLSX, TXT (see app `SUPPORTED_EXTENSIONS`).
- Very large files may take time to chunk and embed.

## Docker vs local

- See **DOCKERLESS.md** for running without Docker.
- `docker-compose.yml` can run n8n alongside the app for Telegram workflows.
