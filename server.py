"""
server.py
---------
FastAPI REST API for IntelliDigest — exposes all LangChain backend modules
as HTTP endpoints for the custom JavaScript frontend.

Endpoints:
  POST /api/chat          — RAG chat with the knowledge base
  POST /api/upload        — Upload and ingest documents
  POST /api/news/search   — Search and ingest news articles
  GET  /api/search        — Semantic search across knowledge base
  GET  /api/stats         — Knowledge base statistics
  POST /api/summarize     — Summarize news articles
  DELETE /api/clear       — Clear the knowledge base
  DELETE /api/chat/clear  — Clear chat history
  GET  /api/personas      — List available personas
  POST /api/n8n/webhook   — Receive content from n8n to ingest into the KB
  POST /api/n8n/telegram  — Forward verify/save payloads to your n8n → Telegram workflow
  GET  /api/n8n/status    — n8n webhook URL configured (Telegram pipeline)
  POST /api/support/chat — Support agent (tools + tickets)
  GET  /api/tickets       — List support tickets
  GET  /api/tickets/{id}  — Get one ticket
  PATCH /api/tickets/{id} — Update ticket fields
  POST /api/tickets/{id}/close — Close ticket (optional resolution note)
  POST /api/support/sessions/clear — Clear support session memory
  GET  /health            — Liveness probe (load balancers / orchestrators)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import uuid
import httpx
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Annotated, Any
from urllib.parse import quote, urlencode, urlparse

from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

# Prevent Keras 3 / TensorFlow import conflict with HuggingFace transformers
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"

from fastapi import Depends, FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from ingestion.document_loader import load_document, semantic_chunk, SUPPORTED_EXTENSIONS
from ingestion.news_retriever import NewsRetriever
from personas.personas import PERSONAS, DEFAULT_PERSONA, get_persona_list
from support.memory import clear_memory as clear_support_memory
from support.tickets import (
    finalize_close_ticket,
    get_all_tickets,
    get_ticket_by_id,
    update_ticket_in_db,
)
from auth.deps import CurrentUser, get_current_user
from auth.jwt_tokens import create_access_token
from auth.oauth_google import ensure_google_client, google_oauth_configured, oauth
from auth.password_reset import consume_reset_token, issue_reset_token
from auth.reset_notify import send_reset_email, smtp_configured
from auth.users import (
    authenticate_email_password,
    get_or_create_google_user,
    get_user_for_password_reset,
    register_user,
)

logger = logging.getLogger(__name__)


# ── Global State ─────────────────────────────────────────────────────────────
# Heavy LangChain / Chroma / embeddings imports are deferred so uvicorn binds quickly (Fly.io health checks).

vectorstore: Any = None
_research_memories: dict[str, Any] = {}
agent_fn: Any = None
summarizer: Any = None
user_doc_count: defaultdict[str, int] = defaultdict(int)
user_news_count: defaultdict[str, int] = defaultdict(int)


def get_research_memory(user_id: str) -> Any:
    """Per-user rolling chat memory for the research tab."""
    if user_id not in _research_memories:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise HTTPException(
                status_code=503, detail="GROQ_API_KEY not set."
            )
        from memory.conversation import ConversationMemory

        _research_memories[user_id] = ConversationMemory(groq_api_key=groq_key)
    return _research_memories[user_id]


def _cors_allow_origins() -> list[str]:
    """Comma-separated ALLOWED_ORIGINS env; empty or unset => allow all (dev). Production: set e.g. https://yourdomain.com"""
    raw = (os.getenv("ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _initialize_backend_sync() -> None:
    """Load embeddings + LangChain stack. Can take minutes on cold start (model download)."""
    from agents.research_agent import create_research_agent
    from chains.summarizer import Summarizer
    from support.bootstrap_kb import bootstrap_support_knowledge_base
    from vectorstore.engine import VectorStoreEngine

    global vectorstore, agent_fn, summarizer

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("[WARNING] GROQ_API_KEY not set - some features will be unavailable.")
    else:
        vectorstore = VectorStoreEngine()
        sk = bootstrap_support_knowledge_base(vectorstore)
        if sk:
            print(f"[OK] Support KB: ingested {sk} chunk(s) into intellidigest_support.")
        agent_fn = create_research_agent(vectorstore)
        summarizer = Summarizer(groq_api_key=groq_key)
        print("[OK] All LangChain components initialized.")
    if not (os.getenv("JWT_SECRET") or "").strip():
        print("[WARNING] JWT_SECRET not set — register/login will fail until you set it in .env")
    if ensure_google_client():
        print("[OK] Google OAuth client registered.")


async def _run_backend_startup() -> None:
    """Run heavy init off the event loop so uvicorn binds to 0.0.0.0 immediately (required for Fly.io)."""
    try:
        await asyncio.to_thread(_initialize_backend_sync)
    except Exception:
        logger.exception("Backend initialization failed; API will return 503 for RAG routes until fixed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background init so the HTTP server accepts connections while embeddings load."""
    asyncio.create_task(_run_backend_startup())
    yield


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="IntelliDigest API",
    description="Multi-source AI research assistant powered by LangChain",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = _cors_allow_origins()
_session_secret = (
    os.getenv("SESSION_SECRET") or os.getenv("JWT_SECRET") or "dev-session-secret-replace-me-32chars!!"
)
# Session must run before CORS on the response path: add Session after CORS so it runs first on requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    max_age=900,
    same_site="lax",
)

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# ── Request/Response Models ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    persona: str = DEFAULT_PERSONA


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    tools_used: list[str]


class NewsSearchRequest(BaseModel):
    topic: str
    max_articles: int = 5
    language: str = "en"


class SummarizeRequest(BaseModel):
    mode: str = "brief"
    persona: str = DEFAULT_PERSONA


class StatsResponse(BaseModel):
    total_chunks: int
    doc_count: int
    news_count: int
    chat_messages: int


class N8nWebhookPayload(BaseModel):
    """Payload sent by the n8n workflow after LLM analysis."""
    content: str
    email: str = ""
    subject: str = ""
    prompt: str = ""


class N8nTelegramRequest(BaseModel):
    """Forward to n8n so a workflow can send Telegram messages (verify link or save a reply)."""

    webhook_url: str = ""
    telegram_chat_id: str
    action: str = "save_message"
    assistant_message: str = ""
    user_message: str = ""
    persona: str = ""
    channel: str = "research_chat"


class SupportChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SupportChatResponse(BaseModel):
    response: str
    session_id: str
    ticket_actions: list[dict] = Field(default_factory=list)


class TicketPatchRequest(BaseModel):
    customer_name: str | None = None
    issue_summary: str | None = None
    category: str | None = None
    priority: str | None = None
    suggested_solution: str | None = None
    status: str | None = None


class TicketCloseRequest(BaseModel):
    resolution_note: str = ""


class SupportSessionClearRequest(BaseModel):
    session_id: str = "default"


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ForgotPasswordResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class AuthConfigOut(BaseModel):
    google_enabled: bool
    reset_email_configured: bool


_GOOGLE_CALLBACK_SUFFIX = "/api/auth/google/callback"


def _oauth_id_token_leeway() -> int:
    """
    Seconds of clock skew allowed when validating Google's id_token (iat/nbf).
    If the PC clock is behind real time, validation fails with 'issued in the future'
    unless leeway is large enough. Sync Windows time (Settings → Time) first; use env for edge cases.
    """
    raw = (os.getenv("OAUTH_JWT_LEEWAY") or "").strip()
    if raw:
        try:
            return max(0, min(int(raw), 86400))
        except ValueError:
            pass
    return 600


def _normalize_oauth_origin(raw: str) -> str:
    """
    Env must be scheme + host + port only (e.g. http://127.0.0.1:8000).
    If someone pastes the full Google redirect URI, strip the callback path once
    so we do not produce .../callback/api/auth/google/callback.
    """
    s = raw.strip().rstrip("/")
    if s.endswith(_GOOGLE_CALLBACK_SUFFIX):
        s = s[: -len(_GOOGLE_CALLBACK_SUFFIX)].rstrip("/")
    return s


def _align_oauth_origin_with_request(request: Request, configured: str) -> str:
    """
    Session cookies are host-only. If OAUTH_* uses localhost but the browser uses 127.0.0.1
    (or the reverse), Google redirects to the configured host while OAuth state lives on the
    request host — Authlib raises mismatching_state (CSRF). Prefer the incoming request
    origin when both URLs are loopback with the same port. Add both redirect URIs in Google
    Cloud Console if you switch between localhost and 127.0.0.1.
    """
    normalized = _normalize_oauth_origin(configured)
    req_base = str(request.base_url).rstrip("/")
    try:
        u_req = urlparse(req_base)
        u_cfg = urlparse(normalized)
        loopback = {"localhost", "127.0.0.1"}
        if (
            u_req.hostname in loopback
            and u_cfg.hostname in loopback
            and u_req.hostname != u_cfg.hostname
            and u_req.port == u_cfg.port
        ):
            return req_base
    except Exception:
        pass
    return normalized


def _oauth_public_base(request: Request) -> str:
    """Origin for OAuth redirect_uri (Google Console must list origin + /api/auth/google/callback)."""
    b = (os.getenv("OAUTH_REDIRECT_BASE") or "").strip()
    if b:
        return _align_oauth_origin_with_request(request, b)
    return str(request.base_url).rstrip("/")


def _oauth_frontend_base(request: Request) -> str:
    """Where to send the browser after Google login (usually same origin as the SPA)."""
    b = (os.getenv("OAUTH_FRONTEND_REDIRECT_BASE") or "").strip()
    if b:
        return _align_oauth_origin_with_request(request, b)
    return str(request.base_url).rstrip("/")


# ── Routes ───────────────────────────────────────────────────────────────────


@app.post("/api/auth/register", response_model=TokenResponse)
async def auth_register(body: RegisterRequest):
    try:
        user = register_user(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        token = create_access_token(user_id=user["id"], email=user["email"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(
        access_token=token,
        user={"id": user["id"], "email": user["email"]},
    )


@app.post("/api/auth/login", response_model=TokenResponse)
async def auth_login(body: LoginRequest):
    try:
        user = authenticate_email_password(body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    try:
        token = create_access_token(user_id=user["id"], email=user["email"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(
        access_token=token,
        user={"id": user["id"], "email": user["email"]},
    )


@app.post("/api/auth/forgot-password", response_model=ForgotPasswordResponse)
async def auth_forgot_password(body: ForgotPasswordRequest):
    """
    Sends a reset link by email (SMTP) when the account exists.
    Response is always generic to avoid email enumeration.
    """
    generic = ForgotPasswordResponse(
        message=(
            "If an account exists for that address, you will receive "
            "reset instructions shortly."
        )
    )
    email = body.email.strip().lower()
    if len(email) < 3 or "@" not in email:
        return generic

    user = get_user_for_password_reset(email)
    if not user:
        return generic

    raw = issue_reset_token(user["id"])
    try:
        if smtp_configured():
            await asyncio.to_thread(send_reset_email, email, raw)
    except Exception as e:
        print(f"[forgot-password] delivery failed: {e}")
    return generic


@app.post("/api/auth/reset-password", response_model=TokenResponse)
async def auth_reset_password(body: ResetPasswordRequest):
    try:
        user = consume_reset_token(body.token, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        token = create_access_token(user_id=user["id"], email=user["email"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return TokenResponse(
        access_token=token,
        user={"id": user["id"], "email": user["email"]},
    )


@app.get("/api/auth/config", response_model=AuthConfigOut)
async def auth_public_config():
    """Public: whether Google OAuth is configured (for UI)."""
    return AuthConfigOut(
        google_enabled=google_oauth_configured(),
        reset_email_configured=smtp_configured(),
    )


@app.get("/api/auth/google")
async def auth_google_start(request: Request):
    """Begin Google OAuth (browser redirect)."""
    if not ensure_google_client():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    redirect_uri = f"{_oauth_public_base(request)}{_GOOGLE_CALLBACK_SUFFIX}"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request):
    """OAuth callback: issue app JWT and redirect to the SPA with token query params."""
    front = _oauth_frontend_base(request)
    if not ensure_google_client():
        return RedirectResponse(url=f"{front}/?auth_error=not_configured", status_code=302)
    try:
        token = await oauth.google.authorize_access_token(
            request,
            leeway=_oauth_id_token_leeway(),
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{front}/?auth_error={quote(str(e)[:280])}",
            status_code=302,
        )
    access = token.get("access_token")
    if not access:
        return RedirectResponse(url=f"{front}/?auth_error=no_access_token", status_code=302)
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access}"},
            timeout=15.0,
        )
    if r.status_code != 200:
        return RedirectResponse(url=f"{front}/?auth_error=userinfo_failed", status_code=302)
    info = r.json()
    email = (info.get("email") or "").strip()
    if not email:
        return RedirectResponse(url=f"{front}/?auth_error=no_email", status_code=302)
    if info.get("email_verified") is False:
        return RedirectResponse(url=f"{front}/?auth_error=email_not_verified", status_code=302)
    sub = str(info.get("sub") or info.get("id") or "").strip()
    if not sub:
        return RedirectResponse(url=f"{front}/?auth_error=no_sub", status_code=302)
    try:
        user = get_or_create_google_user(email, sub)
    except ValueError as e:
        return RedirectResponse(url=f"{front}/?auth_error={quote(str(e))}", status_code=302)
    try:
        jwt = create_access_token(user_id=user["id"], email=user["email"])
    except RuntimeError as e:
        return RedirectResponse(url=f"{front}/?auth_error={quote(str(e))}", status_code=302)
    q = urlencode({"token": jwt, "email": user["email"]})
    return RedirectResponse(url=f"{front}/?{q}", status_code=302)


@app.get("/health")
async def health():
    """Lightweight liveness check; does not wait for embedding model load (suitable for Fly.io probes)."""
    return {
        "status": "ok",
        "service": "intellidigest",
        "ready": vectorstore is not None,
    }


@app.get("/")
async def serve_frontend():
    """Serve the main HTML page."""
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "IntelliDigest API is running. Frontend not found."}


@app.get("/api/personas")
async def list_personas():
    """List all available personas."""
    return get_persona_list()


@app.get("/api/stats")
async def get_stats(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Get knowledge base statistics for the authenticated user."""
    total_chunks = 0
    chat_msgs = 0
    if vectorstore:
        total_chunks = vectorstore.get_collection_count(user.id)
    try:
        mem = get_research_memory(user.id)
        chat_msgs = len(mem.get_display_history())
    except Exception:
        chat_msgs = 0

    return StatsResponse(
        total_chunks=total_chunks,
        doc_count=user_doc_count[user.id],
        news_count=user_news_count[user.id],
        chat_messages=chat_msgs,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Send a message to the research agent."""
    if not agent_fn:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API keys.")

    mem = get_research_memory(user.id)
    chat_context = mem.get_context_string()

    result = agent_fn(
        user_query=req.message,
        persona_id=req.persona,
        chat_history=chat_context,
        user_id=user.id,
    )

    mem.add_exchange(req.message, result["answer"])

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        tools_used=result.get("tools_used", []),
    )


@app.post("/api/upload")
async def upload_document(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    """Upload and ingest a document into the knowledge base."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # Write to temp file and process
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = load_document(tmp_path)
        chunks = semantic_chunk(text, max_chunk_size=500)
        count = vectorstore.add_texts(
            user.id,
            chunks,
            source=file.filename,
            metadata_extras={"type": "document", "filename": file.filename},
        )
        user_doc_count[user.id] += 1
        return {
            "filename": file.filename,
            "chunks_ingested": count,
            "total_chunks": vectorstore.get_collection_count(user.id),
        }
    finally:
        os.unlink(tmp_path)


@app.post("/api/news/search")
async def search_news(
    req: NewsSearchRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Search for news articles and ingest them into the knowledge base."""
    newsapi_key = os.getenv("NEWSAPI_KEY")
    if not newsapi_key:
        raise HTTPException(status_code=503, detail="NEWSAPI_KEY not set.")
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    retriever = NewsRetriever(api_key=newsapi_key)
    articles = retriever.search_articles(
        query=req.topic,
        page_size=req.max_articles,
        language=req.language,
    )

    if not articles:
        return {"articles": [], "chunks_ingested": 0}

    count = vectorstore.add_articles(user.id, articles)
    user_news_count[user.id] += len(articles)

    return {
        "articles": articles,
        "chunks_ingested": count,
        "total_chunks": vectorstore.get_collection_count(user.id),
    }


@app.post("/api/summarize")
async def summarize_articles(
    req: SummarizeRequest,
    _user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Summarize the latest news articles."""
    if not summarizer:
        raise HTTPException(status_code=503, detail="Summarizer not initialized.")

    # This would typically use stored articles; for now we search the vectorstore
    raise HTTPException(
        status_code=400,
        detail="Use /api/news/search to fetch articles, then /api/chat to ask about them.",
    )


@app.get("/api/search")
async def semantic_search(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    q: str = Query(..., min_length=1),
    k: int = Query(5, ge=1, le=20),
):
    """Semantic search across the knowledge base."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    total = vectorstore.get_collection_count(user.id)
    if total == 0:
        return {"results": [], "total_chunks": 0}

    docs = vectorstore.search_similar(user.id, q, k=k)
    results = []
    for doc in docs:
        results.append({
            "content": doc.page_content[:500],
            "source": doc.metadata.get("source", "Unknown"),
            "title": doc.metadata.get("title", ""),
            "url": doc.metadata.get("url", ""),
            "type": doc.metadata.get("type", ""),
        })

    return {"results": results, "total_chunks": total}


@app.delete("/api/clear")
async def clear_knowledge_base(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Clear all documents from this user's knowledge base collection."""
    if vectorstore:
        vectorstore.clear_collection(user.id)
    user_doc_count[user.id] = 0
    user_news_count[user.id] = 0
    return {"message": "Knowledge base cleared."}


@app.delete("/api/chat/clear")
async def clear_chat(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Clear chat history for this user."""
    mem = get_research_memory(user.id)
    mem.clear()
    return {"message": "Chat history cleared."}


@app.get("/api/chat/history")
async def get_chat_history(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Get the full chat history."""
    mem = get_research_memory(user.id)
    return {"history": mem.get_display_history()}


# ── Support & ticketing (lab 6 integration) ─────────────────────────────────

@app.post("/api/support/chat", response_model=SupportChatResponse)
async def support_chat(
    req: SupportChatRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Customer-support agent with KB search, classification, and ticket creation."""
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set.")
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    sid = (req.session_id or "").strip() or str(uuid.uuid4())
    from support.agent import process_support_message

    response_text, ticket_actions = await asyncio.to_thread(
        process_support_message,
        msg,
        sid,
        vectorstore,
        user.id,
    )
    return SupportChatResponse(
        response=response_text,
        session_id=sid,
        ticket_actions=ticket_actions,
    )


@app.get("/api/tickets")
async def list_tickets(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """List support tickets for the authenticated user (newest first)."""
    try:
        tickets = await asyncio.to_thread(get_all_tickets, user.id)
        return {"tickets": tickets, "count": len(tickets)}
    except Exception as e:
        print(f"[API Error] List tickets: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tickets.")


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Get a single ticket by id (must belong to the user)."""
    try:
        t = await asyncio.to_thread(get_ticket_by_id, ticket_id, user.id)
        if not t:
            raise HTTPException(
                status_code=404, detail=f"Ticket '{ticket_id}' not found."
            )
        return {"ticket": t}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API Error] Get ticket {ticket_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ticket.")


@app.patch("/api/tickets/{ticket_id}")
async def patch_ticket(
    ticket_id: str,
    body: TicketPatchRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Update ticket fields (only provided keys are applied)."""
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:

        def _apply():
            return update_ticket_in_db(ticket_id, user.id, **patch)

        row = await asyncio.to_thread(_apply)
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Ticket '{ticket_id}' not found."
            )
        return {"ticket": row}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API Error] Patch ticket {ticket_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update ticket.")


@app.post("/api/tickets/{ticket_id}/close")
async def close_ticket_route(
    ticket_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: TicketCloseRequest = TicketCloseRequest(),
):
    """Mark ticket closed; optional resolution note stored on the ticket."""
    note = (body.resolution_note or "").strip()

    def _close():
        return finalize_close_ticket(ticket_id, note, user_id=user.id)

    try:
        row = await asyncio.to_thread(_close)
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Ticket '{ticket_id}' not found."
            )
        return {"ticket": row}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API Error] Close ticket {ticket_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to close ticket.")


@app.post("/api/support/sessions/clear")
async def support_sessions_clear(
    req: SupportSessionClearRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Clear LangChain memory and cached executor for a support session."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")
    try:
        from support.agent import clear_support_agent

        sid = (req.session_id or "").strip() or "default"
        mem_key = f"{user.id}:{sid}"
        cleared_mem = clear_support_memory(mem_key)
        clear_support_agent(sid, vectorstore, user.id)
        return {
            "success": True,
            "message": (
                "Session cleared successfully."
                if cleared_mem
                else "No active conversation memory for this session."
            ),
        }
    except Exception as e:
        print(f"[API Error] Clear support session: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear session.")


# ── n8n Integration ──────────────────────────────────────────────────────────

@app.post("/api/n8n/webhook")
async def n8n_webhook(
    payload: N8nWebhookPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Receive email insight results from n8n and ingest into the authenticated user's KB."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Empty content received.")

    source_label = f"n8n-email: {payload.email}" if payload.email else "n8n-email-insight"
    subject_label = payload.subject or "Email Insight"

    # Chunk the insight content
    chunks = semantic_chunk(payload.content, max_chunk_size=500)
    count = vectorstore.add_texts(
        user.id,
        chunks,
        source=source_label,
        metadata_extras={
            "type": "n8n-email-insight",
            "email": payload.email,
            "subject": subject_label,
            "prompt": payload.prompt,
        },
    )
    user_doc_count[user.id] += 1

    return {
        "status": "ingested",
        "chunks": count,
        "source": source_label,
        "total_chunks": vectorstore.get_collection_count(user.id),
    }


@app.post("/api/n8n/telegram")
async def n8n_telegram_forward(
    req: N8nTelegramRequest,
    _user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """
    POST JSON to your n8n webhook. Typical workflow: Webhook → IF action → Telegram Send Message.

    Actions:
      - verify_telegram — ping the user so they know the chat id is correct
      - save_message — send the chosen assistant reply (and optional user question) to Telegram
    """
    n8n_url = (
        (req.webhook_url or "").strip()
        or os.getenv("N8N_TELEGRAM_WEBHOOK_URL", "").strip()
        or os.getenv("N8N_WEBHOOK_URL", "").strip()
    )
    if not n8n_url:
        raise HTTPException(
            status_code=503,
            detail="n8n webhook URL not set. Add it under Tools → Telegram, or set N8N_TELEGRAM_WEBHOOK_URL / N8N_WEBHOOK_URL.",
        )

    chat_id = req.telegram_chat_id.strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="telegram_chat_id is required.")

    action = req.action if req.action in ("verify_telegram", "save_message") else "save_message"
    payload = {
        "action": action,
        "telegram_chat_id": chat_id,
        "assistant_message": req.assistant_message,
        "user_message": req.user_message,
        "persona": req.persona,
        "channel": req.channel if req.channel in ("research_chat", "support_chat") else "research_chat",
        "title": "IntelliDigest",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(n8n_url, json=payload)
            response.raise_for_status()
            body = None
            ct = response.headers.get("content-type", "")
            if ct.startswith("application/json"):
                try:
                    body = response.json()
                except Exception:
                    body = response.text
            else:
                body = response.text
            return {"status": "forwarded", "n8n_response": body}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="n8n webhook timed out.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"n8n returned {e.response.status_code}: {e.response.text[:200]}",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach n8n: {str(e)}")


@app.get("/api/n8n/status")
async def n8n_status():
    """Whether a Telegram webhook URL is available (env or UI-driven)."""
    tg = os.getenv("N8N_TELEGRAM_WEBHOOK_URL", "").strip()
    legacy = os.getenv("N8N_WEBHOOK_URL", "").strip()
    url = tg or legacy
    return {
        "configured": bool(url),
        "webhook_url": url[:40] + "..." if len(url) > 40 else url,
        "source": "N8N_TELEGRAM_WEBHOOK_URL" if tg else ("N8N_WEBHOOK_URL" if legacy else ""),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
