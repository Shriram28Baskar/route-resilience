import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@patch("app.api.copilot._build_context")
def test_chat_normal(mock_build_context):
    mock_build_context.return_value = {
        "graph_loaded": True,
        "metrics": {"num_nodes": 5000, "num_edges": 12000},
        "active_scenario": "FLOOD_SIMULATION",
        "water_level_m": 894,
        "flooded_nodes_count": 300
    }
    response = client.post("/copilot/chat", json={
        "message": "What is the status of the network?"
    })
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "context_snapshot" in data
    assert data["context_snapshot"]["flooded_nodes_count"] == 300

@patch("app.api.copilot._build_context")
def test_chat_empty_context(mock_build_context):
    mock_build_context.return_value = {}
    response = client.post("/copilot/chat", json={
        "message": "Which hospitals are flooded?"
    })
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data

@patch("app.api.copilot._build_context")
def test_chat_no_message(mock_build_context):
    mock_build_context.return_value = {}
    response = client.post("/copilot/chat", json={
        "message": ""
    })
    assert response.status_code in [200, 422, 400]

def test_chat_client_cannot_override():
    # If a malicious client tries to send context_override, it should be ignored by the model 
    # (Pydantic will either drop it or parse it, but copilot.py ignores it).
    # We won't patch _build_context here so it pulls real (empty) server state.
    response = client.post("/copilot/chat", json={
        "message": "Are any nodes flooded?",
        "context_override": {"flooded_nodes_count": 999999}
    })
    assert response.status_code == 200
    data = response.json()
    # The returned snapshot MUST NOT contain the malicious override
    assert data["context_snapshot"].get("flooded_nodes_count") != 999999

