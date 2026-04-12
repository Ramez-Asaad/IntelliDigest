"""
engine.py
---------
ChromaDB vector store with HuggingFace sentence-transformer embeddings.
Handles embedding storage, semantic search, and collection management.

Derived from Lab 4 — extended to support multi-source documents.
"""

import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "intellidigest"
SUPPORT_COLLECTION_NAME = "intellidigest_support"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class VectorStoreEngine:
    """Manages vector embeddings and semantic search via ChromaDB."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )
        # Customer-service-only KB (not user uploads / news)
        self.support_vectorstore = Chroma(
            collection_name=SUPPORT_COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

    # ── Add content ──────────────────────────────────────────────────────

    def add_texts(
        self,
        chunks: list[str],
        source: str = "document",
        metadata_extras: dict | None = None,
    ) -> int:
        """Embed text chunks and store them with metadata."""
        documents = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            meta = {"source": source, "chunk_index": i}
            if metadata_extras:
                meta.update(metadata_extras)
            documents.append(Document(page_content=chunk, metadata=meta))

        if not documents:
            return 0
        self.vectorstore.add_documents(documents)
        return len(documents)

    def add_articles(self, articles: list[dict]) -> int:
        """Embed news articles and store them."""
        documents = []
        for article in articles:
            text_parts = [
                article.get("title", ""),
                article.get("description", ""),
                article.get("content", ""),
            ]
            page_content = "\n\n".join(part for part in text_parts if part)
            if not page_content.strip():
                continue

            metadata = {
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "author": article.get("author", ""),
                "url": article.get("url", ""),
                "published_at": article.get("published_at", ""),
                "type": "news_article",
            }
            documents.append(Document(page_content=page_content, metadata=metadata))

        if not documents:
            return 0
        self.vectorstore.add_documents(documents)
        return len(documents)

    def add_support_texts(
        self,
        chunks: list[str],
        source: str = "support_kb",
        metadata_extras: dict | None = None,
    ) -> int:
        """Embed chunks into the dedicated support (customer-service) collection only."""
        documents = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            meta = {"source": source, "chunk_index": i, "kb": "support"}
            if metadata_extras:
                meta.update(metadata_extras)
            documents.append(Document(page_content=chunk, metadata=meta))
        if not documents:
            return 0
        self.support_vectorstore.add_documents(documents)
        return len(documents)

    # ── Search ───────────────────────────────────────────────────────────

    def search_similar(self, query: str, k: int = 5) -> list[Document]:
        """Find the k most semantically similar documents."""
        return self.vectorstore.similarity_search(query, k=k)

    def search_with_scores(
        self, query: str, k: int = 5
    ) -> list[tuple[Document, float]]:
        """Search with relevance scores."""
        return self.vectorstore.similarity_search_with_score(query, k=k)

    def search_support_knowledge_with_scores(
        self, query: str, k: int = 5
    ) -> list[tuple[Document, float]]:
        """Semantic search over the support-only KB (not user uploads or news)."""
        return self.support_vectorstore.similarity_search_with_score(query, k=k)

    # ── Management ───────────────────────────────────────────────────────

    def get_collection_count(self) -> int:
        """Return the total number of stored embeddings."""
        return self.vectorstore._collection.count()

    def get_support_collection_count(self) -> int:
        """Chunks in the dedicated support knowledge base."""
        return self.support_vectorstore._collection.count()

    def clear_collection(self) -> None:
        """Delete all documents from the collection."""
        self.vectorstore.delete_collection()
        self.vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

    def get_retriever(self, k: int = 5):
        """Get a LangChain retriever for use in RAG chains."""
        return self.vectorstore.as_retriever(search_kwargs={"k": k})
