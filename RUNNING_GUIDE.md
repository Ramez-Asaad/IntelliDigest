# IntelliDigest Running Guide & Internal Architecture

Welcome to the detailed guide on how to run **IntelliDigest** and how its internal engine works.

This guide covers the quickest way to launch the app (using Docker) and dives deep into the API, LangChain reasoning agent, and n8n integration.

---

## 🚀 How to Run the App

The easiest and most reliable way to run IntelliDigest and its automated research workflows is via **Docker Compose**. This will automatically spin up both the FastAPI backend and the n8n automation engine.

### Prerequisites

- [Docker & Docker Compose](https://www.docker.com/products/docker-desktop/) installed.
- API keys for **Groq** and (optionally) **NewsAPI**.

### Step 1: Environment Setup

In the root directory of the project, duplicate the `.env.example` file and name it `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
GROQ_API_KEY=gsk_your_groq_key_here
NEWSAPI_KEY=your_newsapi_key_here
```

### Step 2: Launch the Stack

Run the following command to build the Docker image and start the services in detached mode:

```bash
docker compose up -d --build
```

### Step 3: Access the App

Once the containers are running:

1. **IntelliDigest Web App (FastAPI + UI):** Open `http://localhost:8000` in your browser.
2. **n8n Automation Dashboard:** Open `http://localhost:5678` to view and configure automated insight workflows.

To view logs for debugging:

```bash
docker compose logs -f
```

To stop the application:

```bash
docker compose down
```

---

## 🧠 How it Works Internally

IntelliDigest separates its logic across well-defined modules. While the frontend handles the premium UI and animations, the Python backend orchestrates the heavy lifting using **LangChain**.

### The API Layer (`server.py`)

`server.py` is a FastAPI application that serves the frontend files and exposes identical REST API endpoints.

- `/api/chat`, `/api/upload`, `/api/news/search`
- **Global States:** When the server starts up, it initializes global instances of the `VectorStoreEngine` and the `ConversationMemory`.

### The Agentic Core (`agents/research_agent.py`)

When a user asks a question via the chat interface, the request is routed to `research_agent.py`.

- **Reasoning Approach:** Instead of using a complex loop-based `AgentExecutor`, IntelliDigest employs a highly-optimized, hardcoded prompt-based approach.
- **Tooling:** The agent runs a semantic search on the ChromaDB vector database. If it finds context, it conditionally constructs its system prompt to ground itself in the retrieved sources. This allows Llama 3.3 to respond reliably without hallucinating tool inputs.

### Knowledge Storage (`vectorstore/` & `ingestion/`)

- Documents (PDFs, text files, Excel sheets) and live NewsAPI articles are ingested through the `document_loader.py` and `news_retriever.py` modules.
- **Chunking:** Texts are split using semantic splitters.
- **Embedding:** Chunks are vectorized locally using HuggingFace's `all-MiniLM-L6-v2` transformer model.
- **Retrieval:** They are stored persistently in the `chroma_db/` folder, allowing for blazing-fast semantic lookups during chat.

### Automation via n8n

IntelliDigest features a powerful automation bridge to process external data (like monitoring an email inbox) automatically.

1. From the frontend "Tools" drawer, a user can trigger an automated summary by sending a payload to the FastAPI `/api/n8n/trigger` endpoint.
2. This triggers the **n8n** webhook.
3. n8n runs a visual workflow (`lab 5/workflow.json`), connecting to Google Mail, parsing incoming threads, sending a massive prompt payload directly back to Groq REST API via an HTTP node.
4. n8n sends the distilled email insights back to IntelliDigest's `/api/n8n/webhook` endpoint.
5. The FastAPI server ingests the summary directly into the ChromaDB vector store, making it instantly queryable in the UI chat.

---

## Modifying the App 🛠️

- **Adding API Routes:** Very easy. Just add a new `@app.post` to `server.py`.
- **Tweak Styles:** Change variables in `frontend/styles.css`.
- **Modifying AI logic:** To change how the AI answers, tweak the system prompts in `personas/personas.py` and `agents/research_agent.py`. Note that adding true "LangChain Tool Calling" logic will require refactoring `research_agent.py` to use a LangGraph construct or an `AgentExecutor`.
