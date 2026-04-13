"""
app.py
------
Streamlit web UI for IntelliDigest — a multi-source AI research assistant.

Features:
  - Document upload (PDF, DOCX, Excel, TXT)
  - Live news search via NewsAPI
  - RAG-powered chat with source citations
  - Persona switching for tone-adaptive responses
  - Semantic search across the knowledge base
  - Conversation memory with summary compression

Design: Follows DESIGN.md — deep blue + aqua palette,
soft human-centered modern minimal, premium professional polish.
"""

import streamlit as st
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

# Single-user id for Streamlit demo (separate Chroma collection from FastAPI users).
STREAMLIT_USER_ID = os.getenv("STREAMLIT_USER_ID", "00000000-0000-4000-8000-000000000001")

from ingestion.document_loader import load_uploaded_file, semantic_chunk, SUPPORTED_EXTENSIONS
from ingestion.news_retriever import NewsRetriever
from vectorstore.engine import VectorStoreEngine
from chains.summarizer import Summarizer
from chains.qa_chain import QAChain
from memory.conversation import ConversationMemory
from personas.personas import PERSONAS, DEFAULT_PERSONA, get_persona_list
from agents.research_agent import create_research_agent


# ── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="IntelliDigest — AI Research Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Custom CSS (DESIGN.md Blueprint) ────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Root Variables ────────────────────────────────────── */
    :root {
        --primary: #1E3A8A;
        --primary-hover: #1A3378;
        --accent-aqua: #22D3EE;
        --accent-soft: #A5F3FC;
        --success: #86EFAC;
        --bg-base: #F5F7FA;
        --surface-1: #FFFFFF;
        --surface-2: #EEF3F8;
        --border: #D6DEE8;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --text-muted: #94A3B8;
        --shadow-subtle: 0 2px 6px rgba(0,0,0,0.04);
        --shadow-medium: 0 8px 24px rgba(0,0,0,0.06);
        --shadow-elevated: 0 16px 40px rgba(0,0,0,0.08);
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 16px;
        --radius-xl: 20px;
        --transition: all 200ms cubic-bezier(0.22, 1, 0.36, 1);
    }

    /* ── Global Styling ───────────────────────────────────── */
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background: var(--bg-base) !important;
    }

    /* ── Sidebar ─────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F1D3D 0%, #162033 100%) !important;
        border-right: 1px solid #24324A !important;
    }

    section[data-testid="stSidebar"] * {
        color: #E2E8F0 !important;
    }

    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] .stFileUploader label {
        color: #94A3B8 !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.03em !important;
        text-transform: uppercase !important;
    }

    section[data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #1E3A8A, #22D3EE) !important;
        color: white !important;
        border: none !important;
        border-radius: var(--radius-md) !important;
        padding: 0.6rem 1.2rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: var(--transition) !important;
        width: 100% !important;
    }

    section[data-testid="stSidebar"] .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 16px rgba(34, 211, 238, 0.3) !important;
    }

    /* ── Hero Header ─────────────────────────────────────── */
    .hero-header {
        background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 60%, #162033 100%);
        padding: 2.5rem 2rem;
        border-radius: var(--radius-xl);
        margin-bottom: 1.5rem;
        position: relative;
        overflow: hidden;
        box-shadow: var(--shadow-elevated);
    }

    .hero-header::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -20%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, rgba(34, 211, 238, 0.15) 0%, transparent 70%);
        border-radius: 50%;
    }

    .hero-header::after {
        content: '';
        position: absolute;
        bottom: -30%;
        left: -10%;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(134, 239, 172, 0.08) 0%, transparent 70%);
        border-radius: 50%;
    }

    .hero-header h1 {
        color: #FFFFFF !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        position: relative;
        z-index: 1;
    }

    .hero-header p {
        color: #94A3B8 !important;
        font-size: 1rem !important;
        margin-top: 0.5rem !important;
        position: relative;
        z-index: 1;
    }

    .hero-header .accent {
        color: var(--accent-aqua) !important;
    }

    /* ── Chat Messages ───────────────────────────────────── */
    .chat-user {
        background: linear-gradient(135deg, #1E3A8A, #2548A0);
        color: #FFFFFF;
        padding: 1rem 1.25rem;
        border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
        margin: 0.75rem 0;
        margin-left: 15%;
        box-shadow: var(--shadow-subtle);
        font-size: 0.95rem;
        line-height: 1.6;
    }

    .chat-ai {
        background: var(--surface-1);
        color: var(--text-primary);
        padding: 1.25rem 1.5rem;
        border-radius: var(--radius-sm) var(--radius-lg) var(--radius-lg) var(--radius-lg);
        margin: 0.75rem 0;
        margin-right: 10%;
        box-shadow: var(--shadow-medium);
        border-left: 3px solid var(--accent-aqua);
        font-size: 0.95rem;
        line-height: 1.7;
    }

    .chat-ai .source-tag {
        display: inline-block;
        background: var(--surface-2);
        color: var(--text-secondary);
        padding: 0.2rem 0.6rem;
        border-radius: var(--radius-sm);
        font-size: 0.78rem;
        margin: 0.3rem 0.3rem 0.3rem 0;
        border: 1px solid var(--border);
    }

    /* ── Stats Cards ─────────────────────────────────────── */
    .stat-card {
        background: var(--surface-1);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 1.25rem;
        text-align: center;
        box-shadow: var(--shadow-subtle);
        transition: var(--transition);
    }

    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-medium);
    }

    .stat-card .stat-number {
        font-size: 2rem;
        font-weight: 700;
        color: var(--primary);
        line-height: 1;
    }

    .stat-card .stat-label {
        font-size: 0.8rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.4rem;
    }

    /* ── News Card ────────────────────────────────────────── */
    .news-card {
        background: var(--surface-1);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 1.25rem;
        margin: 0.75rem 0;
        box-shadow: var(--shadow-subtle);
        transition: var(--transition);
    }

    .news-card:hover {
        box-shadow: var(--shadow-medium);
        border-color: var(--accent-soft);
    }

    .news-card h4 {
        color: var(--text-primary) !important;
        margin: 0 0 0.5rem 0 !important;
        font-size: 1rem !important;
    }

    .news-card .meta {
        color: var(--text-muted);
        font-size: 0.82rem;
    }

    .news-card .summary {
        color: var(--text-secondary);
        font-size: 0.9rem;
        line-height: 1.6;
        margin-top: 0.5rem;
    }

    /* ── Persona Badge ───────────────────────────────────── */
    .persona-badge {
        display: inline-block;
        background: linear-gradient(135deg, #1E3A8A, #22D3EE);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }

    /* ── General Overrides ───────────────────────────────── */
    .stTextInput > div > div > input {
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--border) !important;
        padding: 0.75rem 1rem !important;
        font-family: 'Inter', sans-serif !important;
        background: var(--surface-2) !important;
        transition: var(--transition) !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: var(--accent-aqua) !important;
        box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.15) !important;
    }

    div[data-testid="stMetric"] {
        background: var(--surface-1) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-lg) !important;
        padding: 1rem !important;
        box-shadow: var(--shadow-subtle) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: var(--radius-md) !important;
        padding: 0.5rem 1.25rem !important;
        font-weight: 500 !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--primary) !important;
        color: white !important;
    }

    /* ── Scrollbar ────────────────────────────────────────── */
    ::-webkit-scrollbar {
        width: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: var(--border);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }
</style>
""", unsafe_allow_html=True)


# ── Initialize Session State ─────────────────────────────────────────────────

def init_session_state():
    """Initialize all session state variables."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "persona" not in st.session_state:
        st.session_state.persona = DEFAULT_PERSONA
    if "vectorstore" not in st.session_state:
        st.session_state.vectorstore = None
    if "memory" not in st.session_state:
        st.session_state.memory = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "doc_count" not in st.session_state:
        st.session_state.doc_count = 0
    if "news_count" not in st.session_state:
        st.session_state.news_count = 0
    if "summary_mode" not in st.session_state:
        st.session_state.summary_mode = "brief"


def initialize_components():
    """Initialize LangChain components."""
    if st.session_state.initialized:
        return True

    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        st.error("⚠️ GROQ_API_KEY not found in .env file. Please set it up.")
        return False

    try:
        st.session_state.vectorstore = VectorStoreEngine()
        st.session_state.memory = ConversationMemory(groq_api_key=groq_key)
        st.session_state.agent = create_research_agent(
            st.session_state.vectorstore
        )
        st.session_state.initialized = True
        return True
    except Exception as e:
        st.error(f"⚠️ Initialization error: {e}")
        return False


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    """Render the sidebar with settings and document upload."""
    with st.sidebar:
        # Logo / Brand
        st.markdown("### 🧠 IntelliDigest")
        st.markdown(
            '<span style="color: #94A3B8; font-size: 0.85rem;">'
            'Multi-Source AI Research Assistant</span>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # ── Persona Selector ──
        st.markdown("##### 🎭 Active Persona")
        personas = get_persona_list()
        persona_options = {f"{p['emoji']} {p['name']}": p["id"] for p in personas}
        current_display = next(
            (k for k, v in persona_options.items() if v == st.session_state.persona),
            list(persona_options.keys())[0],
        )
        selected = st.selectbox(
            "Persona",
            options=list(persona_options.keys()),
            index=list(persona_options.keys()).index(current_display),
            label_visibility="collapsed",
        )
        st.session_state.persona = persona_options[selected]

        st.markdown("---")

        # ── Document Upload ──
        st.markdown("##### 📄 Upload Documents")
        uploaded_files = st.file_uploader(
            "Drop files here",
            type=[ext.lstrip('.') for ext in SUPPORTED_EXTENSIONS],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded_files:
            if st.button("📦 Ingest Documents", key="ingest_btn"):
                with st.spinner("Processing documents..."):
                    total_chunks = 0
                    for f in uploaded_files:
                        try:
                            text = load_uploaded_file(f)
                            chunks = semantic_chunk(text, max_chunk_size=500)
                            count = st.session_state.vectorstore.add_texts(
                                STREAMLIT_USER_ID,
                                chunks,
                                source=f.name,
                                metadata_extras={"type": "document", "filename": f.name},
                            )
                            total_chunks += count
                            st.session_state.doc_count += 1
                        except Exception as e:
                            st.error(f"Error processing {f.name}: {e}")

                    if total_chunks > 0:
                        st.success(f"✅ {total_chunks} chunks from {len(uploaded_files)} file(s) ingested!")

        st.markdown("---")

        # ── News Search ──
        st.markdown("##### 📰 Search News")
        news_topic = st.text_input("Topic", placeholder="e.g. artificial intelligence", label_visibility="collapsed")

        if st.button("🔍 Fetch & Ingest News", key="news_btn"):
            if news_topic:
                newsapi_key = os.getenv("NEWSAPI_KEY")
                if not newsapi_key:
                    st.warning("NEWSAPI_KEY not set in .env")
                else:
                    with st.spinner(f"Searching for '{news_topic}'..."):
                        try:
                            retriever = NewsRetriever(api_key=newsapi_key)
                            articles = retriever.search_articles(news_topic, page_size=5)

                            if articles:
                                count = st.session_state.vectorstore.add_articles(
                                    STREAMLIT_USER_ID, articles
                                )
                                st.session_state.news_count += len(articles)
                                st.success(f"✅ {count} articles ingested!")

                                # Store articles for the news tab
                                if "latest_articles" not in st.session_state:
                                    st.session_state.latest_articles = []
                                st.session_state.latest_articles = articles
                            else:
                                st.info("No articles found for this topic.")
                        except Exception as e:
                            st.error(f"News search error: {e}")
            else:
                st.warning("Please enter a topic.")

        st.markdown("---")

        # ── Summary Mode ──
        st.markdown("##### ⚙️ Summary Mode")
        st.session_state.summary_mode = st.radio(
            "Mode",
            ["brief", "detailed"],
            index=0 if st.session_state.summary_mode == "brief" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )

        st.markdown("---")

        # ── Knowledge Base Stats ──
        st.markdown("##### 📊 Knowledge Base")
        if st.session_state.vectorstore:
            total = st.session_state.vectorstore.get_collection_count(STREAMLIT_USER_ID)
            st.markdown(
                f'<div style="text-align: center; padding: 0.8rem; '
                f'background: rgba(34,211,238,0.1); border-radius: 12px; '
                f'margin: 0.5rem 0;">'
                f'<div style="font-size: 1.8rem; font-weight: 700; '
                f'color: #22D3EE;">{total}</div>'
                f'<div style="font-size: 0.75rem; color: #94A3B8; '
                f'text-transform: uppercase; letter-spacing: 0.05em;">'
                f'Embedded Chunks</div></div>',
                unsafe_allow_html=True,
            )

        if st.button("🗑️ Clear Knowledge Base", key="clear_kb"):
            if st.session_state.vectorstore:
                st.session_state.vectorstore.clear_collection(STREAMLIT_USER_ID)
                st.session_state.doc_count = 0
                st.session_state.news_count = 0
                st.success("Knowledge base cleared.")

        if st.button("🗑️ Clear Chat History", key="clear_chat"):
            st.session_state.chat_history = []
            if st.session_state.memory:
                st.session_state.memory.clear()
            st.rerun()


# ── Main Content ─────────────────────────────────────────────────────────────

def render_hero():
    """Render the hero header."""
    persona = PERSONAS.get(st.session_state.persona, PERSONAS[DEFAULT_PERSONA])
    st.markdown(
        f"""
        <div class="hero-header">
            <h1>🧠 Intelli<span class="accent">Digest</span></h1>
            <p>Multi-source AI research assistant — Upload documents, fetch news,
            and chat with your knowledge base.</p>
            <div style="margin-top: 0.8rem;">
                <span class="persona-badge">{persona['emoji']} {persona['name']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stats():
    """Render the stats dashboard."""
    total_chunks = 0
    if st.session_state.vectorstore:
        total_chunks = st.session_state.vectorstore.get_collection_count(STREAMLIT_USER_ID)

    cols = st.columns(4)
    with cols[0]:
        st.metric("📄 Documents", st.session_state.doc_count)
    with cols[1]:
        st.metric("📰 Articles", st.session_state.news_count)
    with cols[2]:
        st.metric("🧩 Chunks", total_chunks)
    with cols[3]:
        st.metric("💬 Messages", len(st.session_state.chat_history))


def render_chat():
    """Render the chat interface."""
    # Display chat history
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-user">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            content = msg["content"]
            sources_html = ""
            if msg.get("sources"):
                source_tags = "".join(
                    f'<span class="source-tag">'
                    f'{"📄" if not s.get("url") else "🔗"} {s.get("title") or s.get("source", "Unknown")}'
                    f'</span>'
                    for s in msg["sources"]
                    if s.get("source") or s.get("title")
                )
                if source_tags:
                    sources_html = f'<div style="margin-top: 0.75rem;">{source_tags}</div>'

            tools_html = ""
            if msg.get("tools_used"):
                tools_html = (
                    '<div style="margin-top: 0.5rem; font-size: 0.78rem; '
                    'color: #94A3B8;">'
                    + " · ".join(msg["tools_used"])
                    + '</div>'
                )

            st.markdown(
                f'<div class="chat-ai">{content}{sources_html}{tools_html}</div>',
                unsafe_allow_html=True,
            )

    # Chat input
    user_input = st.chat_input("Ask anything about your knowledge base...")

    if user_input and st.session_state.agent:
        # Add user message
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
        })

        # Get agent response
        with st.spinner("Thinking..."):
            try:
                chat_context = ""
                if st.session_state.memory:
                    chat_context = st.session_state.memory.get_context_string()

                result = st.session_state.agent(
                    user_query=user_input,
                    persona_id=st.session_state.persona,
                    chat_history=chat_context,
                    user_id=STREAMLIT_USER_ID,
                )

                # Add AI response
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "sources": result.get("sources", []),
                    "tools_used": result.get("tools_used", []),
                })

                # Update memory
                if st.session_state.memory:
                    st.session_state.memory.add_exchange(
                        user_input, result["answer"]
                    )

            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Sorry, I encountered an error: {str(e)}",
                    "sources": [],
                    "tools_used": ["❌ Error"],
                })

        st.rerun()


def render_news_tab():
    """Render the news articles tab."""
    articles = st.session_state.get("latest_articles", [])
    if not articles:
        st.info("No news articles loaded yet. Use the sidebar to search for a topic.")
        return

    # Summarize option
    if st.button("📝 Summarize All Articles"):
        try:
            summarizer = Summarizer()
            with st.spinner("Generating summaries..."):
                summaries = summarizer.summarize_articles(
                    articles,
                    mode=st.session_state.summary_mode,
                    persona_id=st.session_state.persona,
                )

            for s in summaries:
                st.markdown(
                    f"""
                    <div class="news-card">
                        <h4>{s['title']}</h4>
                        <div class="meta">{s['source']}</div>
                        <div class="summary">{s['summary']}</div>
                        <div style="margin-top: 0.5rem;">
                            <a href="{s['url']}" target="_blank"
                               style="color: #22D3EE; font-size: 0.85rem;">
                               🔗 Read full article
                            </a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        except Exception as e:
            st.error(f"Summarization error: {e}")
    else:
        for article in articles:
            st.markdown(
                f"""
                <div class="news-card">
                    <h4>{article.get('title', 'Untitled')}</h4>
                    <div class="meta">
                        {article.get('source', 'Unknown')} ·
                        {article.get('author', 'Unknown')} ·
                        {article.get('published_at', '')[:10]}
                    </div>
                    <div class="summary">{article.get('description', '')}</div>
                    <div style="margin-top: 0.5rem;">
                        <a href="{article.get('url', '#')}" target="_blank"
                           style="color: #22D3EE; font-size: 0.85rem;">
                           🔗 Read full article
                        </a>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_search_tab():
    """Render the semantic search tab."""
    if not st.session_state.vectorstore:
        st.info("Knowledge base not initialized.")
        return

    total = st.session_state.vectorstore.get_collection_count(STREAMLIT_USER_ID)
    if total == 0:
        st.info("Knowledge base is empty. Upload documents or fetch news first.")
        return

    st.markdown(f"**{total} chunks** in the knowledge base")

    query = st.text_input("Semantic search query", placeholder="Search by meaning...")

    if query:
        with st.spinner("Searching..."):
            results = st.session_state.vectorstore.search_similar(
                STREAMLIT_USER_ID, query, k=5
            )

        for i, doc in enumerate(results, 1):
            title = doc.metadata.get("title", "")
            source = doc.metadata.get("source", "Unknown")
            url = doc.metadata.get("url", "")
            snippet = doc.page_content[:300].replace("\n", " ")

            link_html = ""
            if url:
                link_html = (
                    f'<a href="{url}" target="_blank" '
                    f'style="color: #22D3EE; font-size: 0.85rem;">🔗 Source</a>'
                )

            st.markdown(
                f"""
                <div class="news-card">
                    <h4>[{i}] {title or source}</h4>
                    <div class="meta">Source: {source}</div>
                    <div class="summary">{snippet}...</div>
                    {link_html}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_session_state()
    render_sidebar()

    # Try to initialize components
    ready = initialize_components()

    # Main content
    render_hero()

    if not ready:
        st.warning(
            "Please set up your API keys in the `.env` file to get started.\n\n"
            "1. Copy `.env.example` to `.env`\n"
            "2. Add your `GROQ_API_KEY` and optionally `NEWSAPI_KEY`\n"
            "3. Restart the app"
        )
        return

    render_stats()

    # Tabs
    tab_chat, tab_news, tab_search = st.tabs([
        "💬 Chat",
        "📰 News Feed",
        "🔍 Semantic Search",
    ])

    with tab_chat:
        render_chat()

    with tab_news:
        render_news_tab()

    with tab_search:
        render_search_tab()


if __name__ == "__main__":
    main()
