# Production deployment (e.g. Oracle Cloud Free Tier)

This document complements [README.md](../README.md), [RUNNING_GUIDE.md](RUNNING_GUIDE.md), and [DOCKERLESS.md](DOCKERLESS.md).

## Host choice

**Oracle Cloud “Always Free” AMD VPS** (or any VPS with persistent disk) is a good fit: you run Docker, keep volumes for Chroma and SQLite, and control firewall and TLS.

## Docker

- **Default** [`docker-compose.yml`](../docker-compose.yml): IntelliDigest only (no bundled n8n). Suitable for production.
- **Optional n8n in the same stack**: [`docker-compose.with-n8n.yml`](../docker-compose.with-n8n.yml).

```bash
docker compose up -d --build
```

Do **not** run `uvicorn` with `--reload` in production. The [Dockerfile](../Dockerfile) uses a plain `uvicorn` command without reload.

## Secrets

- Set **`GROQ_API_KEY`** (and any other keys) via environment or your platform’s secret store. Never commit `.env`.
- Rotate keys if exposed.

## HTTPS and reverse proxy

- Terminate TLS in front of the app (**Caddy**, **nginx**, or **Traefik**) on ports 443 / 80.
- Prefer proxying to `127.0.0.1:8000` and **not** exposing port 8000 on the public internet.
- Firewall: allow SSH (restricted), 80/443; block direct access to app port from the world if the proxy is on the same host.

## CORS

- For production, set **`ALLOWED_ORIGINS`** in `.env` to a comma-separated list of exact origins (scheme + host + port), e.g.  
  `https://yourdomain.com,https://www.yourdomain.com`
- If **`ALLOWED_ORIGINS`** is unset or empty, the API allows `*` (fine for local dev; **not** ideal for public production).

## Persistence and backups

Docker Compose maps:

| Volume | Purpose |
|--------|---------|
| `chroma_data` | Chroma embeddings (`chroma_db/` in container) |
| `ticket_data` | SQLite tickets (`data/tickets.db`) |

**Back up** both if the knowledge base or tickets matter: copy volume data or use your cloud provider’s volume snapshots on a schedule.

## Health checks

- **`GET /health`** returns `{"status":"ok","service":"intellidigest"}`. Use it for load balancer or orchestrator probes (it does not validate Groq or Chroma).

## Runtime and RAM

- The app loads **sentence-transformers** / embeddings on startup; plan **at least ~2 GB RAM** for a small deployment (more if the OS and Docker overhead are tight). First request after cold start can be slow while models load.

## Ollama fallback (optional)

- **`OLLAMA_BASE_URL`** / **`OLLAMA_FALLBACK_MODEL`**: used when Groq returns rate limits or certain API errors ([`chains/llm_factory.py`](../chains/llm_factory.py)).
- **Groq-only production:** omit Ollama or leave fallback unused; ensure Groq quota is sufficient.
- **Same-VPS Ollama:** install Ollama on the VM, `ollama serve`, pull your model, point `OLLAMA_BASE_URL` at `http://127.0.0.1:11434` (default).
- **Separate host:** run Ollama elsewhere and set `OLLAMA_BASE_URL` to that URL (firewall + TLS as appropriate).

## n8n / Telegram

- The default compose file does **not** run n8n. You can run n8n on another machine or use `docker-compose.with-n8n.yml` for a combined stack; see [n8n-telegram.md](n8n-telegram.md).
