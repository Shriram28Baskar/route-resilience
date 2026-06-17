"""
Groq API client for the Urban Planning Copilot.
"""
import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"   # fast, capable model available on Groq


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

    client = AsyncGroq(api_key=GROQ_API_KEY)

    full_messages = [{"role": "system", "content": system}] + messages

    # Truncate messages if context is too long (safety for 8192-token window)
    full_messages = _trim_messages(full_messages, max_chars=20_000)

    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=full_messages,
        max_tokens=1024,
        temperature=0.3,   # lower temperature for grounded, factual answers
    )

    reply = response.choices[0].message.content
    logger.info(f"Groq response: {len(reply)} chars, "
                f"tokens used: {response.usage.total_tokens}")
    return reply


def _trim_messages(messages: List[Dict], max_chars: int) -> List[Dict]:
    """
    Trim the message list from the oldest user/assistant messages if the total
    character count exceeds max_chars. Always preserves the system message and
    the most recent user message.
    """
    total = sum(len(m["content"]) for m in messages)
    if total <= max_chars:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs  = [m for m in messages if m["role"] != "system"]

    # Drop oldest messages until within budget
    while other_msgs and sum(len(m["content"]) for m in system_msgs + other_msgs) > max_chars:
        other_msgs.pop(0)

    return system_msgs + other_msgs
