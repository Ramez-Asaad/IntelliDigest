"""Chroma-backed search_support_knowledge_base tool — support-only collection."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from support.config import TOP_K_RESULTS
from vectorstore.engine import VectorStoreEngine


class SearchInput(BaseModel):
    query: str = Field(
        description="A clear search query describing the user's question or issue."
    )


def make_search_support_knowledge_tool(vectorstore_engine: VectorStoreEngine, k: int | None = None):
    """Search only the dedicated support KB (customer-service docs), not user uploads or news."""
    top_k = k if k is not None else TOP_K_RESULTS

    @tool("search_support_knowledge_base", args_schema=SearchInput)
    def search_support_knowledge_base(query: str) -> str:
        """
        Semantic search over IntelliDigest's **support knowledge base** (curated customer-service docs).
        Does **not** include the user's uploaded documents or news articles from the main app KB.
        """
        try:
            if vectorstore_engine.get_support_collection_count() == 0:
                return (
                    "The support knowledge library has no documents yet (empty collection). "
                    "Answer from general IntelliDigest product facts from your instructions, "
                    "and offer a ticket if they need follow-up."
                )
            results = vectorstore_engine.search_support_knowledge_with_scores(query, k=top_k)
            if not results:
                return "No relevant passages found in the support knowledge base for that query."
            formatted = []
            for i, (doc, score) in enumerate(results, 1):
                source = doc.metadata.get("source", "Unknown")
                source_name = str(source).replace("\\", "/").split("/")[-1]
                if len(source_name) > 80:
                    source_name = source_name[:77] + "..."
                formatted.append(
                    f"[Result {i}] (Source: {source_name}, Relevance: {1 - float(score):.2f})\n"
                    f"{doc.page_content.strip()}"
                )
            return "\n\n---\n\n".join(formatted)
        except Exception as e:
            return f"Error searching support knowledge base: {str(e)}"

    return search_support_knowledge_base
