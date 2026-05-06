"""RAG pipeline: retrieve relevant chunks and stream an answer via Claude."""

from typing import Generator

import anthropic

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided \
documentation context.

Rules:
- Base your answers on the documentation context provided in each message.
- For follow-up questions, you may also reference information from earlier in the conversation.
- If the context does not contain enough information to answer, say so clearly.
- When referencing specific content, mention the source document name.
- Be concise and accurate. Structure long answers with bullet points or headings where helpful."""


def build_context(chunks: list[dict], max_chars: int = 8000) -> str:
    """Format retrieved chunks into a single context block, capped at max_chars."""
    parts = []
    total = 0
    for chunk in chunks:
        block = f"[Source: {chunk['source']}]\n{chunk['text']}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def stream_rag_response(
    query: str,
    chunks: list[dict],
    api_key: str,
    model: str = "claude-opus-4-7",
    chat_history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """Stream a Claude answer grounded in retrieved context, with full conversation history.

    chat_history is the full session history including the current user message as the
    last item. Previous turns are forwarded as-is so Claude can handle follow-up questions.
    The current question is enriched with freshly retrieved RAG context.

    Yields text deltas suitable for Streamlit's `st.write_stream`.
    """
    client = anthropic.Anthropic(api_key=api_key)
    context = build_context(chunks)

    # Current user message enriched with retrieved documentation context
    current_user_content = f"""Documentation context:

{context}

---

Question: {query}"""

    # Build the messages list:
    # - All previous turns (plain Q&A) so Claude remembers the conversation
    # - Current question with fresh RAG context injected
    messages: list[dict] = []
    if chat_history and len(chat_history) > 1:
        # Everything except the last item (the current user message we just appended)
        for msg in chat_history[:-1]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": current_user_content})

    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=messages,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        yield from stream.text_stream


def get_no_context_response() -> str:
    return (
        "No relevant documents found in the knowledge base. "
        "Please make sure you have fetched and processed documentation first."
    )
