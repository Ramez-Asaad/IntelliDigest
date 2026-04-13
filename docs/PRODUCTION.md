# Production deployment (VPS, Fly.io, etc.)

This document complements [README.md](../README.md), [RUNNING_GUIDE.md](RUNNING_GUIDE.md), and [DOCKERLESS.md](DOCKERLESS.md).

## Fly.io

The repo includes [`fly.toml`](../fly.toml) for [Fly.io](https://fly.io/) (Dockerfile-based deploy). Chroma and SQLite share **one** persistent volume via `INTELLIDIGEST_PERSIST_DIR` (see [`paths.py`](../paths.py)).

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/) and log in: `fly auth login`.
2. Create an app name (must be unique): e.g. `fly apps create my-intellidigest` and set `app = "my-intellidigest"` in `fly.toml` (or run `fly launch` and merge settings).
3. **Create a volume** in the **same region** as `primary_region` in `fly.toml` (default `iad`):
   ```bash
   fly volumes create intellidigest_data --region iad --size 3
   ```
4. **Secrets** (do not commit these; set on Fly, not only in local `.env`):
   ```bash
   fly secrets set GROQ_API_KEY=... JWT_SECRET=... NEWSAPI_KEY=...
   ```
   Add any others you use (`GOOGLE_CLIENT_ID`, `OAUTH_*`, `SMTP_*`, `ALLOWED_ORIGINS`, etc.).
5. Deploy: `fly deploy`
6. **Custom domain / HTTPS:** `fly certs add yourdomain.com` and follow DNS instructions. Then set production `OAUTH_*`, `PASSWORD_RESET_FRONTEND_BASE`, and `ALLOWED_ORIGINS` to `https://yourdomain.com` (via `fly secrets set` or `[env]` in `fly.toml` for non-secret values).

**RAM:** `fly.toml` requests **2 GB**; embeddings are heavy—raise if the Machine OOMs (`[[vm]]` `memory`).

**Single Machine + volume:** scale to one Machine in the volume’s region; Fly volumes do not span Machines.

---

## Host choice (VPS)

**Oracle Cloud “Always Free” AMD VPS**, **Hetzner**, **DigitalOcean**, etc. are a good fit: you run Docker, keep volumes for Chroma and SQLite, and control firewall and TLS.

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

**Docker Compose** maps:

| Volume | Purpose |
|--------|---------|
| `chroma_data` | Chroma embeddings (`chroma_db/` in container) |
| `ticket_data` | SQLite (`data/` — tickets, auth DB, etc.) |

**Fly.io:** one volume at `/data` holds `chroma_db/` and `data/` when `INTELLIDIGEST_PERSIST_DIR=/data`.

**Back up** persistent data if the knowledge base or tickets matter: copy volume data or use your provider’s volume snapshots on a schedule.

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
