from fastapi.testclient import TestClient

from app.llm.checker import ModelOutput, Quote, Verdict
from app.main import app
from app.review import seeds

client = TestClient(app)

AD = {"product": "personal_loan", "channel": "landing_page", "body": "No credit check needed! Rates from 9.99% APR."}


def rule(rules, rule_id):
    return next(r for r in rules if r["id"] == rule_id)


def add(**body):
    return client.post("/api/rules", json={"products": [], "channels": [], **body})


def check(payload=AD):
    return client.post("/api/assets", json=payload).json()


def test_phrase_rule_flags_new_checks_as_check_failed(fake_model):
    res = add(name="Banned credit-check claims", kind="phrases", phrases=["no credit check", "$0 down"])
    custom = rule(res.json(), "custom-1")
    assert (custom["type"], custom["source"], custom["enabled"]) == ("check_failed", "custom", True)

    asset = check()
    [flag] = [f for f in asset["flags"] if f["rule_id"] == "custom-1"]
    assert flag["type"] == "check_failed"
    assert flag["spans"][0]["quote"] == "No credit check"  # case-insensitive, the ad's own text
    assert flag["citation"] == "ClearPath policy (custom rule)"


def test_phrase_rule_matches_whole_phrases_including_symbols(fake_model):
    add(name="Down payment claims", kind="phrases", phrases=["$0 down"])
    hit = check({**AD, "body": "Get in for $0 down today."})
    miss = check({**AD, "body": "Get in for $10 downtown today."})
    assert "custom-1" in [f["rule_id"] for f in hit["flags"]]
    assert "custom-1" not in [f["rule_id"] for f in miss["flags"]]


def test_plain_english_rule_goes_to_the_model_as_needs_judgment(fake_model):
    res = add(name="No lifestyle promises", kind="instruction", instruction="Implies a loan will improve the reader's lifestyle or happiness.")
    assert rule(res.json(), "custom-1")["type"] == "needs_judgment"

    fake_model.output = ModelOutput(
        verdicts=[Verdict(violated=True, rule_id="custom-1", quotes=[Quote(text="No credit check needed!", field="body")], why="Lifestyle promise.")]
    )
    asset = check()
    assert "custom-1: Implies a loan will improve" in fake_model.prompts[-1]
    assert [f["type"] for f in asset["flags"] if f["rule_id"] == "custom-1"] == ["needs_judgment"]


def test_switching_a_rule_off_affects_new_checks_only(fake_model):
    before = check()
    assert "regz-24c-rate-as-apr" not in [f["rule_id"] for f in before["flags"]]  # 9.99% APR is fine
    stated = check({**AD, "body": "Rates from 9.99% interest."})
    assert "regz-24c-rate-as-apr" in [f["rule_id"] for f in stated["flags"]]

    res = client.patch("/api/rules/regz-24c-rate-as-apr", json={"enabled": False})
    assert rule(res.json(), "regz-24c-rate-as-apr")["enabled"] is False

    again = check({**AD, "body": "Rates from 8.99% interest."})
    assert "regz-24c-rate-as-apr" not in [f["rule_id"] for f in again["flags"]]
    # The earlier ad keeps the flag it was checked with.
    kept = client.get(f"/api/assets/{stated['id']}").json()
    assert "regz-24c-rate-as-apr" in [f["rule_id"] for f in kept["flags"]]


def test_unknown_rules_and_builtin_deletes_are_refused():
    assert client.patch("/api/rules/nope", json={"enabled": False}).status_code == 404
    assert client.delete("/api/rules/regz-24c-rate-as-apr").status_code == 422
    assert client.delete("/api/rules/custom-99").status_code == 404


def test_custom_rules_can_be_deleted(fake_model):
    add(name="Temp", kind="phrases", phrases=["act now"])
    res = client.delete("/api/rules/custom-1")
    assert "custom-1" not in [r["id"] for r in res.json()]


def test_rule_validation():
    assert add(name="Empty", kind="phrases", phrases=["  "]).status_code == 422
    assert add(name="Short", kind="instruction", instruction="too short").status_code == 422
    assert add(name="  ", kind="phrases", phrases=["x"]).status_code == 422
    assert add(name="Long", kind="instruction", instruction="x" * 501).status_code == 422


def test_reset_restores_default_rules(fake_model):
    add(name="Temp", kind="phrases", phrases=["act now"])
    client.patch("/api/rules/canspam-address", json={"enabled": False})
    seeds.reset()
    rules = client.get("/api/rules").json()
    assert not [r for r in rules if r["source"] == "custom"]
    assert rule(rules, "canspam-address")["enabled"] is True


def test_rule_changes_are_logged_with_who_and_why(fake_model):
    add(name="Temp", kind="phrases", phrases=["act now"])
    client.patch("/api/rules/regz-24c-rate-as-apr", json={"enabled": False, "note": "Too noisy on search ads"})
    client.patch("/api/rules/regz-24c-rate-as-apr", json={"enabled": False})  # no change: not logged
    client.delete("/api/rules/custom-1")
    history = client.get("/api/rules/history").json()
    assert [(e["action"], e["rule_id"]) for e in history] == [
        ("deleted", "custom-1"),
        ("switched_off", "regz-24c-rate-as-apr"),
        ("created", "custom-1"),
    ]
    assert history[1]["note"] == "Too noisy on search ads"
    assert history[1]["rule_name"] == "Rate not stated as APR"
    assert all(e["actor"] == "Demo reviewer" for e in history)


def test_reset_clears_rule_history(fake_model):
    add(name="Temp", kind="phrases", phrases=["act now"])
    seeds.reset()
    assert client.get("/api/rules/history").json() == []
