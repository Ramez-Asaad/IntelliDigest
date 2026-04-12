"""Remove leaked tool-call markup that some LLMs print in plain text (never show users)."""

import re


def sanitize_support_reply(text: str) -> str:
    """
    Strip fake <function=...> blocks, ReAct debris, and similar that should never
    appear in end-user copy.
    """
    if not text or not isinstance(text, str):
        return text

    t = text

    # Full <function=name>...</function> (common Groq / fine-tune leakage pattern)
    t = re.sub(r"<function\s*=[^>]*>.*?</function>", "", t, flags=re.DOTALL | re.IGNORECASE)

    # Unclosed: <function=name>{ "json": "..." }  (no closing tag)
    t = re.sub(r"<function\s*=[^>]*>\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*", "", t, flags=re.DOTALL)

    # Stray opening tag through end of line
    t = re.sub(r"<function\s*=[^>]*>[^\n]*", "", t, flags=re.IGNORECASE)

    t = re.sub(r"</function>", "", t, flags=re.IGNORECASE)

    # Classic ReAct lines that should not reach users
    for prefix in (
        r"^Action\s*:\s*.*$",
        r"^Action\s+Input\s*:\s*.*$",
        r"^Observation\s*:\s*.*$",
    ):
        t = re.sub(prefix, "", t, flags=re.MULTILINE | re.IGNORECASE)

    # Collapse awkward gaps left after removals
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\btry\s+to\s+to\b", "try to", t, flags=re.IGNORECASE)
    # "Additionally, I can try to " left empty after tag removal → drop the scaffolding
    t = re.sub(r"(?i)\bAdditionally,\s*I can try to\s+(?=determine\b)", "", t)

    t = re.sub(r"\n\s*\n\s*$", "\n", t).strip()
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t
