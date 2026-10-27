from fastapi.testclient import TestClient

from app.llm import store
from app.main import app

client = TestClient(app)

AD = {"body": "Personal loans at 5.99% interest.", "product": "personal_loan", "channel": "landing_page"}


def test_analyze_returns_flags_and_ai_status(fake_model):
    res = client.post("/api/analyze", json=AD)
    assert res.status_code == 200
    [flag] = res.json()["flags"]
    assert flag["rule_id"] == "regz-24c-rate-as-apr"
    assert flag["type"] == "check_failed"
    assert flag["spans"][0]["quote"] == "5.99%"
    assert res.json()["ai"]["status"] == "ran"


def test_analyze_rejects_unknown_product():
    res = client.post("/api/analyze", json={"body": "hi", "product": "boat_loan", "channel": "email"})
    assert res.status_code == 422


def test_analyze_rejects_empty_body():
    res = client.post("/api/analyze", json={"body": "", "product": "mortgage", "channel": "email"})
    assert res.status_code == 422


def test_limits_count_down_per_client_address(fake_model):
    alice, bob = {"x-forwarded-for": "203.0.113.1"}, {"x-forwarded-for": "203.0.113.2"}
    client.post("/api/analyze", json=AD, headers=alice)
    assert client.get("/api/limits", headers=alice).json() == {
        "ai_enabled": True,
        "remaining_this_hour": store.PER_VISITOR_PER_HOUR - 1,
        "limit_per_hour": store.PER_VISITOR_PER_HOUR,
    }
    assert client.get("/api/limits", headers=bob).json()["remaining_this_hour"] == store.PER_VISITOR_PER_HOUR


def test_rules_lists_code_and_judgment_rules():
    res = client.get("/api/rules")
    assert res.status_code == 200
    types = [r["type"] for r in res.json()]
    assert types.count("check_failed") == 10
    assert types.count("needs_judgment") == 9
