"""
Groq API client for the Urban Planning Copilot.
"""
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "qwen/qwen3.6-27b"   # fast, capable model available on Groq


async def groq_chat(system: str, messages: List[Dict[str, str]]) -> str:
    """
    Send a chat completion request to the Groq API.

    Args:
        system:   System prompt string.
        messages: List of {"role": "user"|"assistant", "content": str} dicts.

    Returns:
        The assistant's reply as a string.

    Raises:
        RuntimeError if the API key is not set or the request fails.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY environment variable is not set. "
                           "Please add it to your .env file.")

    try:
        from groq import AsyncGroq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    client = AsyncGroq(api_key=GROQ_API_KEY, max_retries=0, timeout=10.0)

    full_messages = [{"role": "system", "content": system}] + messages

    # Truncate messages if context is too long (safety for 8000 TPM limit)
    full_messages = _trim_messages(full_messages, max_chars=6000)

    logger.info(f"MESSAGES SENT TO GROQ: {len(full_messages)} messages, roles: {[m['role'] for m in full_messages]}")
    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=full_messages,
            max_tokens=4096,
            temperature=0.3,   # lower temperature for grounded, factual answers
        )

        import re
        reply = response.choices[0].message.content
        reply = re.sub(r'<think>.*?(?:</think>|$)', '', reply, flags=re.DOTALL).strip()
        logger.info(f"Groq response: {len(reply)} chars, "
                    f"tokens used: {response.usage.total_tokens}")
        return reply
    except Exception as e:
        logger.error(f"Groq API Error: {str(e)}")
        if "429" in str(e) or "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            return "Copilot is temporarily unavailable due to the LLM service rate limit. The computed disaster results remain available on the dashboard."
        return f"Copilot encountered an error: {str(e)}"


def _trim_messages(messages: List[Dict], max_chars: int) -> List[Dict]:
    """
    Trim the message list from the oldest user/assistant messages if the total
    character count exceeds max_chars. Always preserves the system message.
    If the final remaining user message is STILL too large, its text content
    is truncated to fit within the max_chars budget to ensure the LLM always
    receives a user query.
    """
    total = sum(len(m["content"]) for m in messages)
    if total <= max_chars:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs  = [m for m in messages if m["role"] != "system"]

    # Drop oldest messages until within budget, BUT always keep at least the last message
    while len(other_msgs) > 1 and sum(len(m["content"]) for m in system_msgs + other_msgs) > max_chars:
        other_msgs.pop(0)

    # If the single remaining message (plus system) is STILL too large, truncate its string content
    current_total = sum(len(m["content"]) for m in system_msgs + other_msgs)
    if current_total > max_chars and other_msgs:
        system_budget = sum(len(m["content"]) for m in system_msgs)
        allowed_chars_for_last_msg = max_chars - system_budget - 50 # 50 chars for truncation notice
        if allowed_chars_for_last_msg > 0:
            last_msg = other_msgs[-1]
            last_msg["content"] = "...[CONTEXT TRUNCATED]...\n" + last_msg["content"][-allowed_chars_for_last_msg:]

    return system_msgs + other_msgs
