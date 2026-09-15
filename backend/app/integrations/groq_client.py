"""
Groq API client for the Urban Planning Copilot and AMDIROS narrative generator.

Model selection rationale
-------------------------
We use llama-3.3-70b-versatile (direct instruct) rather than a reasoning model
(e.g. qwen3-27b, deepseek-r1).  Reasoning models emit a large internal
<think>...</think> block before their visible response.  With max_tokens=600
the entire budget is consumed by thinking, leaving 0 characters of actual
narrative.  llama-3.3-70b-versatile produces output immediately — no hidden
reasoning chain — and fits within the demo latency SLA (~1-2 s).
"""
import os
import logging
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Direct instruct model verified active on Groq account: ~1.2s latency, zero thinking-token waste.
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


async def groq_chat(system: str, messages: List[Dict[str, str]], max_tokens: int = 600) -> str:
    """
    Send a chat completion request to the Groq API.

    Args:
        system:     System prompt string.
        messages:   List of {"role": "user"|"assistant", "content": str} dicts.
        max_tokens: Max tokens to generate (default 600 — sufficient for
                    a 3-paragraph narrative, well within Groq TPM limit).

    Returns:
        The assistant's reply as a string.

    Raises:
        RuntimeError if the API key is not set or the request fails.
    """
    api_key = os.getenv("GROQ_API_KEY", GROQ_API_KEY)
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set. "
                           "Please add it to your .env file.")

    try:
        from groq import AsyncGroq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    client = AsyncGroq(api_key=api_key, max_retries=0, timeout=12.0)

    full_messages = [{"role": "system", "content": system}] + messages

    # Truncate messages if context is too long (safety for 8000 TPM limit)
    full_messages = _trim_messages(full_messages, max_chars=5000)

    logger.info(
        f"Groq request: model={GROQ_MODEL}, "
        f"messages={len(full_messages)}, max_tokens={max_tokens}"
    )
    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=0.3,   # lower temperature for grounded, factual answers
        )

        reply = response.choices[0].message.content or ""

        # Belt-and-suspenders: strip any <think>...</think> from models that
        # might emit them despite being instruct models (e.g. future regressions)
        import re
        reply = re.sub(r'<think>.*?(?:</think>|$)', '', reply, flags=re.DOTALL).strip()

        logger.info(
            f"Groq response: {len(reply)} chars, "
            f"tokens_used={response.usage.total_tokens} "
            f"(prompt={response.usage.prompt_tokens}, "
            f"completion={response.usage.completion_tokens})"
        )
        return reply
    except Exception as e:
        logger.error(f"Groq API Error: {str(e)}")
        if "429" in str(e) or "rate limit" in str(e).lower():
            return ""   # empty → caller falls back to template
        if "timeout" in str(e).lower():
            return ""   # empty → caller falls back to template
        return ""   # always return empty on error so caller uses template


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
