"""
engine.py
---------
ChromaDB vector store with HuggingFace sentence-transformer embeddings.
Main KB uses one Chroma collection per authenticated user; support KB stays global.
"""

import hashlib
import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
SUPPORT_COLLECTION_NAME = "intellidigest_support"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _main_collection_name_for_user(user_id: str) -> str:
    """Stable Chroma collection id from user uuid (alphanumeric suffix)."""
    u = user_id.replace("-", "").lower()
    if len(u) != 32 or not u.isalnum():
        u = hashlib.sha256(user_id.encode()).hexdigest()[:32]
    return f"intellidigest_u_{u}"


class VectorStoreEngine:
    """Manages vector embeddings: per-user main collection + shared support collection."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._user_main_chroma: dict[str, Chroma] = {}
        self.support_vectorstore = Chroma(
            collection_name=SUPPORT_COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

    def _get_user_main_chroma(self, user_id: str) -> Chroma:
        if user_id not in self._user_main_chroma:
            name = _main_collection_name_for_user(user_id)
            self._user_main_chroma[user_id] = Chroma(
                collection_name=name,
                embedding_function=self.embeddings,
                persist_directory=CHROMA_PERSIST_DIR,
            )
        return self._user_main_chroma[user_id]

    # ── Add content (main KB, per user) ──────────────────────────────────

    def add_texts(
        self,
        user_id: str,
        chunks: list[str],
        source: str = "document",
        metadata_extras: dict | None = None,
    ) -> int:
        vs = self._get_user_main_chroma(user_id)
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
        vs.add_documents(documents)
        return len(documents)

    def add_articles(self, user_id: str, articles: list[dict]) -> int:
        vs = self._get_user_main_chroma(user_id)
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
        vs.add_documents(documents)
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

    def search_similar(self, user_id: str, query: str, k: int = 5) -> list[Document]:
        vs = self._get_user_main_chroma(user_id)
        return vs.similarity_search(query, k=k)

    def search_with_scores(
        self, user_id: str, query: str, k: int = 5
    ) -> list[tuple[Document, float]]:
        vs = self._get_user_main_chroma(user_id)
        return vs.similarity_search_with_score(query, k=k)

    def search_support_knowledge_with_scores(
        self, query: str, k: int = 5
    ) -> list[tuple[Document, float]]:
        return self.support_vectorstore.similarity_search_with_score(query, k=k)

    # ── Management ───────────────────────────────────────────────────────

    def get_collection_count(self, user_id: str) -> int:
        vs = self._get_user_main_chroma(user_id)
        return vs._collection.count()

    def get_support_collection_count(self) -> int:
        return self.support_vectorstore._collection.count()

    def clear_collection(self, user_id: str) -> None:
        name = _main_collection_name_for_user(user_id)
        if user_id in self._user_main_chroma:
            try:
                self._user_main_chroma[user_id].delete_collection()
            except Exception:
                pass
            del self._user_main_chroma[user_id]
        self._user_main_chroma[user_id] = Chroma(
            collection_name=name,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

    def get_retriever(self, user_id: str, k: int = 5):
        vs = self._get_user_main_chroma(user_id)
        return vs.as_retriever(search_kwargs={"k": k})
