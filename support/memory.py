"""Per-session conversation memory for the support agent."""

import warnings

# AgentExecutor still expects classic memory shape; upstream deprecates until LangGraph migration.
warnings.filterwarnings("ignore", message=r".*migrating_memory.*")

from langchain_classic.memory import ConversationBufferWindowMemory

_memory_store: dict[str, ConversationBufferWindowMemory] = {}
MEMORY_WINDOW_SIZE = 10


def get_memory(session_id: str = "default") -> ConversationBufferWindowMemory:
    if session_id not in _memory_store:
        _memory_store[session_id] = ConversationBufferWindowMemory(
            k=MEMORY_WINDOW_SIZE,
            memory_key="chat_history",
            return_messages=True,
            output_key="output",
        )
    return _memory_store[session_id]


def clear_memory(session_id: str = "default") -> bool:
    if session_id in _memory_store:
        _memory_store[session_id].clear()
        del _memory_store[session_id]
        return True
    return False
