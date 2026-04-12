# Running IntelliDigest without Docker

This guide runs the **FastAPI app + static frontend** directly on your machine. You do **not** need Docker or the bundled **n8n** service. Core features (upload, news, chat, search, support ticketing) work the same; anything that depends on a self-hosted n8n instance is optional and can be ignored.

## Prerequisites

- **Python 3.11+** (3.13 is fine; match what you use elsewhere in the course).
- **Git** (if you are cloning the repo).
- A **Groq API key** ([Groq Console](https://console.groq.com/)). Required for primary LLM usage (chat, support agent, summarization, RAG).
- **NewsAPI key** only if you want the News tab / `/api/news/search` ([NewsAPI](https://newsapi.org/)).
- **Ollama** (optional but recommended): install [Ollama](https://ollama.com), run `ollama serve`, and `ollama pull` the model named in `OLLAMA_FALLBACK_MODEL` (see `.env.example`). When Groq rate-limits or errors, the app retries on the local model via `chains/llm_factory.py`.

Optional: **build tools** on Linux (e.g. `build-essential`) if `pip` fails compiling native wheels—on Windows, prebuilt wheels usually install without this.

## 1. Get the code and enter the project folder

```bash
cd IntelliDigest
```

## 2. Create and activate a virtual environment

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

The first run will download **sentence-transformers** / **PyTorch**-related wheels and can take several minutes.

## 4. Environment variables

Copy the example env file and edit it:

```bash
copy .env.example .env
```

On macOS/Linux use `cp .env.example .env`.

Set at least:

```env
GROQ_API_KEY=your_key_here
```

Add `NEWSAPI_KEY=` if you use news search.

Optional but useful:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_FALLBACK_MODEL=qwen2.5:0.5b
```

Other keys in `.env.example` are optional (`SUPPORT_LLM_MODEL`, Telegram/n8n URLs, etc.).

## 5. Avoid TensorFlow / Keras conflicts (if imports fail)

Some setups pull **transformers** in a way that triggers a Keras 3 error. The app sets these inside `server.py`, but if you run tools that import the stack **before** `server.py`, set them in your shell:

**PowerShell**

```powershell
$env:TRANSFORMERS_NO_TF = "1"
$env:USE_TF = "0"
```

**bash**

```bash
export TRANSFORMERS_NO_TF=1
export USE_TF=0
```

## 6. Start the API server

From the **repository root** (the folder that contains `server.py`):

```bash
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

- **`--reload`** restarts on code changes (omit in production).
- Use `--host 0.0.0.0` if you need access from other devices on your LAN.

Open a browser at: **http://127.0.0.1:8000**

## 7. What gets created on disk

| Path | Purpose |
|------|--------|
| `chroma_db/` | Chroma persist dir. Contains **`intellidigest`** (uploads + news for Chat/Search) and **`intellidigest_support`** (curated support docs from `support/kb/`). Deleting the folder resets both; support KB is re-seeded from markdown on next startup if the support collection is empty. |
| `data/tickets.db` | SQLite DB for Support tickets (OpenAPI `PATCH` / `POST …/close` after UI confirmation). |

Both are gitignored; they appear after first use.

## 8. Stopping the app

Press **Ctrl+C** in the terminal where `uvicorn` is running, then `deactivate` the venv if you want to leave it.

## 9. What you are *not* running (by design)

- **n8n** — Not started. The Tools drawer can still point at an **external** n8n webhook URL if you run n8n elsewhere; otherwise ignore Telegram automation.
- **Docker Compose** — No containerized Chroma volume; `chroma_db/` lives directly in the project folder.

## 10. Troubleshooting

| Issue | What to try |
|--------|-------------|
| `GROQ_API_KEY` errors / 503 on chat | Ensure `.env` is in the project root and the key is valid. |
| Groq rate limit / 429 / timeouts | Ensure **Ollama** is running (`ollama serve`) and the model in `OLLAMA_FALLBACK_MODEL` is pulled (`ollama pull …`). Check `OLLAMA_BASE_URL`. |
| Port 8000 in use | Run `uvicorn ... --port 8001` and open that port instead. |
| Slow first request | The embedding model downloads on first Chroma use; wait once. |
| `ModuleNotFoundError` | Confirm the venv is activated and `pip install -r requirements.txt` finished without errors. |
| Support agent “Failed to call a function” | Prefer `SUPPORT_LLM_MODEL=llama-3.3-70b-versatile` in `.env` (see `.env.example`). |

## Optional: alternate UI (`app.py`)

The repo may include a **Streamlit** `app.py`. It is **not** part of `requirements.txt`. The supported path for this project is **FastAPI + `frontend/`** via `uvicorn` as above. Only explore Streamlit if your course materials require it and you install Streamlit yourself.
