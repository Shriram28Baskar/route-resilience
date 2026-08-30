import pytest
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.api.copilot import BRIEF_SYSTEM_PROMPT, generate_brief_narrative

client = TestClient(app)

def test_brief_narrative_normal():
    response = client.post("/copilot/brief-narrative", json={
        "flood_data": {"water_level": 894, "flooded_nodes": 3722},
        "impact_data": {"population": {"affected": 233000}},
        "ward_data": {"critical_wards_count": 5}
    })
    assert response.status_code == 200

def test_brief_narrative_no_flood():
    response = client.post("/copilot/brief-narrative", json={
        "flood_data": {"water_level": 850, "flooded_nodes": 0},
        "impact_data": {},
        "ward_data": {"critical_wards_count": 0}
    })
    assert response.status_code == 200

def test_brief_narrative_extreme_flood():
    response = client.post("/copilot/brief-narrative", json={
        "flood_data": {"water_level": 920, "flooded_nodes": 125000},
        "impact_data": {"population": {"affected": 8000000}},
        "ward_data": {"critical_wards_count": 198}
    })
    assert response.status_code == 200

def test_brief_narrative_missing_data():
    response = client.post("/copilot/brief-narrative", json={
        "flood_data": {},
        "impact_data": {},
        "ward_data": {}
    })
    assert response.status_code == 200

def test_system_prompt_constraints():
    assert "NEVER invent, hallucinate, or calculate new numbers" in BRIEF_SYSTEM_PROMPT
    assert "ONLY use the numbers and facts provided" in BRIEF_SYSTEM_PROMPT

@patch('app.api.copilot.groq_chat', side_effect=Exception("Groq API Timeout"))
def test_brief_narrative_timeout(mock_groq):
    response = client.post("/copilot/brief-narrative", json={
        "flood_data": {}, "impact_data": {}, "ward_data": {}
    })
    assert response.status_code == 200
    assert response.json()["narrative"] == "AI narrative generation unavailable. Please refer to the structured data below."

