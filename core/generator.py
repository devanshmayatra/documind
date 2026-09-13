from core.qdrant_engine import ai_client

def rewrite_query(current_query: str, chat_history: list) -> str:
    """Reformulates conversational follow-ups into standalone queries."""
    if not chat_history:
        return current_query

    history_summary = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-4:]])
    prompt = (
        "Given the conversation history below, rewrite the user's latest question into an "
        "independent, complete search query. Preserve all entities. Return ONLY the rewritten query.\n\n"
        f"History:\n{history_summary}\n\n"
        f"Follow-up: {current_query}\nStandalone Query:"
    )
    res = ai_client.models.generate_content(model="models/gemini-3.6-flash", contents=prompt)
    return res.text.strip()