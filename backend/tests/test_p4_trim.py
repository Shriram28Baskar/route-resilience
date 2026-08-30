import pytest
from app.integrations.groq_client import _trim_messages
import copy

def test_trim_messages_overflow_large():
    # System is 10 chars, budget is 200. Leaving 190 for user.
    # User message is 500 chars.
    msgs = [
        {"role": "system", "content": "1234567890"}, 
        {"role": "user", "content": "A" * 500}
    ]
    # We must pass a copy if we want to preserve original in tests, but it modifies in place anyway
    res = _trim_messages(copy.deepcopy(msgs), max_chars=200)
    assert len(res) == 2
    assert res[0]["content"] == "1234567890"
    # allowed_chars = 200 - 10 - 50 = 140. 
    # length should be len("...[CONTEXT TRUNCATED]...\n") + 140 = 26 + 140 = 166.
    assert "...[CONTEXT TRUNCATED]..." in res[1]["content"]

