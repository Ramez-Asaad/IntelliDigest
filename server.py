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
"""

import asyncio
import os
import sys
import tempfile
import uuid
import httpx
from contextlib import asynccontextmanager

# Prevent Keras 3 / TensorFlow import conflict with HuggingFace transformers
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from ingestion.document_loader import load_document, semantic_chunk, SUPPORTED_EXTENSIONS
from ingestion.news_retriever import NewsRetriever
from vectorstore.engine import VectorStoreEngine
from chains.summarizer import Summarizer
from chains.qa_chain import QAChain
from memory.conversation import ConversationMemory
from personas.personas import PERSONAS, DEFAULT_PERSONA, get_persona_list
from agents.research_agent import create_research_agent
from support.agent import clear_support_agent, process_support_message
from support.bootstrap_kb import bootstrap_support_knowledge_base
from support.memory import clear_memory as clear_support_memory
from support.tickets import (
    finalize_close_ticket,
    get_all_tickets,
    get_ticket_by_id,
    update_ticket_in_db,
)


# ── Global State ─────────────────────────────────────────────────────────────

vectorstore: VectorStoreEngine | None = None
memory: ConversationMemory | None = None
agent_fn = None
summarizer: Summarizer | None = None
doc_count = 0
news_count = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all LangChain components on startup."""
    global vectorstore, memory, agent_fn, summarizer, doc_count, news_count

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("[WARNING] GROQ_API_KEY not set - some features will be unavailable.")
    else:
        vectorstore = VectorStoreEngine()
        sk = bootstrap_support_knowledge_base(vectorstore)
        if sk:
            print(f"[OK] Support KB: ingested {sk} chunk(s) into intellidigest_support.")
        memory = ConversationMemory(groq_api_key=groq_key)
        agent_fn = create_research_agent(vectorstore)
        summarizer = Summarizer(groq_api_key=groq_key)
        print("[OK] All LangChain components initialized.")

    yield


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="IntelliDigest API",
    description="Multi-source AI research assistant powered by LangChain",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ── Routes ───────────────────────────────────────────────────────────────────

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
async def get_stats():
    """Get knowledge base statistics."""
    total_chunks = 0
    chat_msgs = 0
    if vectorstore:
        total_chunks = vectorstore.get_collection_count()
    if memory:
        chat_msgs = len(memory.get_display_history())

    return StatsResponse(
        total_chunks=total_chunks,
        doc_count=doc_count,
        news_count=news_count,
        chat_messages=chat_msgs,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the research agent."""
    if not agent_fn:
        raise HTTPException(status_code=503, detail="Agent not initialized. Check API keys.")

    chat_context = ""
    if memory:
        chat_context = memory.get_context_string()

    result = agent_fn(
        user_query=req.message,
        persona_id=req.persona,
        chat_history=chat_context,
    )

    if memory:
        memory.add_exchange(req.message, result["answer"])

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        tools_used=result.get("tools_used", []),
    )


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and ingest a document into the knowledge base."""
    global doc_count

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
            chunks,
            source=file.filename,
            metadata_extras={"type": "document", "filename": file.filename},
        )
        doc_count += 1
        return {
            "filename": file.filename,
            "chunks_ingested": count,
            "total_chunks": vectorstore.get_collection_count(),
        }
    finally:
        os.unlink(tmp_path)


@app.post("/api/news/search")
async def search_news(req: NewsSearchRequest):
    """Search for news articles and ingest them into the knowledge base."""
    global news_count

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

    count = vectorstore.add_articles(articles)
    news_count += len(articles)

    return {
        "articles": articles,
        "chunks_ingested": count,
        "total_chunks": vectorstore.get_collection_count(),
    }


@app.post("/api/summarize")
async def summarize_articles(req: SummarizeRequest):
    """Summarize the latest news articles."""
    if not summarizer:
        raise HTTPException(status_code=503, detail="Summarizer not initialized.")

    # This would typically use stored articles; for now we search the vectorstore
    raise HTTPException(
        status_code=400,
        detail="Use /api/news/search to fetch articles, then /api/chat to ask about them.",
    )


@app.get("/api/search")
async def semantic_search(q: str = Query(..., min_length=1), k: int = Query(5, ge=1, le=20)):
    """Semantic search across the knowledge base."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    total = vectorstore.get_collection_count()
    if total == 0:
        return {"results": [], "total_chunks": 0}

    docs = vectorstore.search_similar(q, k=k)
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
async def clear_knowledge_base():
    """Clear all documents from the knowledge base."""
    global doc_count, news_count

    if vectorstore:
        vectorstore.clear_collection()
    doc_count = 0
    news_count = 0
    return {"message": "Knowledge base cleared."}


@app.delete("/api/chat/clear")
async def clear_chat():
    """Clear chat history."""
    if memory:
        memory.clear()
    return {"message": "Chat history cleared."}


@app.get("/api/chat/history")
async def get_chat_history():
    """Get the full chat history."""
    if not memory:
        return {"history": []}
    return {"history": memory.get_display_history()}


# ── Support & ticketing (lab 6 integration) ─────────────────────────────────

@app.post("/api/support/chat", response_model=SupportChatResponse)
async def support_chat(req: SupportChatRequest):
    """Customer-support agent with KB search, classification, and ticket creation."""
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not set.")
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    sid = (req.session_id or "").strip() or str(uuid.uuid4())
    response_text, ticket_actions = await asyncio.to_thread(
        process_support_message,
        msg,
        sid,
        vectorstore,
    )
    return SupportChatResponse(
        response=response_text,
        session_id=sid,
        ticket_actions=ticket_actions,
    )


@app.get("/api/tickets")
async def list_tickets():
    """List all support tickets (newest first)."""
    try:
        tickets = await asyncio.to_thread(get_all_tickets)
        return {"tickets": tickets, "count": len(tickets)}
    except Exception as e:
        print(f"[API Error] List tickets: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve tickets.")


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    """Get a single ticket by id."""
    try:
        t = await asyncio.to_thread(get_ticket_by_id, ticket_id)
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
async def patch_ticket(ticket_id: str, body: TicketPatchRequest):
    """Update ticket fields (only provided keys are applied)."""
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:

        def _apply():
            return update_ticket_in_db(ticket_id, **patch)

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
    body: TicketCloseRequest = TicketCloseRequest(),
):
    """Mark ticket closed; optional resolution note stored on the ticket."""
    note = (body.resolution_note or "").strip()

    def _close():
        return finalize_close_ticket(ticket_id, note)

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
async def support_sessions_clear(req: SupportSessionClearRequest):
    """Clear LangChain memory and cached executor for a support session."""
    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")
    try:
        cleared_mem = clear_support_memory(req.session_id)
        clear_support_agent(req.session_id, vectorstore)
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
async def n8n_webhook(payload: N8nWebhookPayload):
    """Receive email insight results from n8n and ingest into the knowledge base."""
    global doc_count

    if not vectorstore:
        raise HTTPException(status_code=503, detail="Vector store not initialized.")

    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Empty content received.")

    source_label = f"n8n-email: {payload.email}" if payload.email else "n8n-email-insight"
    subject_label = payload.subject or "Email Insight"

    # Chunk the insight content
    chunks = semantic_chunk(payload.content, max_chunk_size=500)
    count = vectorstore.add_texts(
        chunks,
        source=source_label,
        metadata_extras={
            "type": "n8n-email-insight",
            "email": payload.email,
            "subject": subject_label,
            "prompt": payload.prompt,
        },
    )
    doc_count += 1

    return {
        "status": "ingested",
        "chunks": count,
        "source": source_label,
        "total_chunks": vectorstore.get_collection_count(),
    }


@app.post("/api/n8n/telegram")
async def n8n_telegram_forward(req: N8nTelegramRequest):
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
