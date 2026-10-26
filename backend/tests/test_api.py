from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_analyze_returns_flags():
    res = client.post(
        "/api/analyze",
        json={"body": "Personal loans at 5.99% interest.", "product": "personal_loan", "channel": "landing_page"},
    )
    assert res.status_code == 200
    [flag] = res.json()["flags"]
    assert flag["rule_id"] == "regz-24c-rate-as-apr"
    assert flag["type"] == "check_failed"
    assert flag["spans"][0]["quote"] == "5.99%"


def test_analyze_rejects_unknown_product():
    res = client.post("/api/analyze", json={"body": "hi", "product": "boat_loan", "channel": "email"})
    assert res.status_code == 422


def test_analyze_rejects_empty_body():
    res = client.post("/api/analyze", json={"body": "", "product": "mortgage", "channel": "email"})
    assert res.status_code == 422


def test_rules_lists_the_builtin_rules():
    res = client.get("/api/rules")
    assert res.status_code == 200
    assert len(res.json()) == 8
    assert all(r["source"] == "builtin" and r["type"] == "check_failed" for r in res.json())
