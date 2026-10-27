import pytest
from fastapi.testclient import TestClient

from app.llm.checker import ModelOutput, Quote, Verdict
from app.main import app
from app.review import seeds

client = TestClient(app)

BAD_LOAN = {
    "product": "personal_loan",
    "channel": "landing_page",
    "body": "Everyone qualifies! Personal loans at 5.99% interest.",
}


@pytest.fixture
def judged(fake_model):
    """The model flags "Everyone qualifies!" as a misleading claim."""
    fake_model.output = ModelOutput(
        verdicts=[Verdict(violated=True, rule_id="llm-udaap-misleading", quotes=[Quote(text="Everyone qualifies!", field="body")], why="Implies guaranteed approval.")]
    )
    return fake_model


def create(payload=BAD_LOAN):
    res = client.post("/api/assets", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def flag(asset, rule_id):
    return next(f for f in asset["flags"] if f["rule_id"] == rule_id)


# --- creating and listing ---------------------------------------------------------------


def test_new_ad_is_stored_with_its_flags_and_history(judged):
    asset = create()
    assert asset["status"] == "in_review"
    assert asset["title"] == "Everyone qualifies! Personal loans at 5.99% interest."
    assert {f["rule_id"] for f in asset["flags"]} == {"regz-24c-rate-as-apr", "llm-udaap-misleading"}
    assert all(f["status"] == "open" for f in asset["flags"])
    assert asset["version"]["ai"]["status"] == "ran"
    assert [e["action"] for e in asset["events"]] == ["checked", "submitted"]


def test_queue_counts_open_flags_by_type(judged):
    asset = create()
    client.post(f"/api/flags/{flag(asset, 'llm-udaap-misleading')['id']}/acknowledge")
    [item] = client.get("/api/assets").json()
    assert (item["open_failed"], item["open_judgment"], item["total"]) == (1, 0, 2)


def test_unknown_ad_is_404():
    assert client.get("/api/assets/999").status_code == 404


# --- resolving flags (D5, D6) --------------------------------------------------------------


def test_dismiss_records_reason_note_and_who(judged):
    asset = create()
    f = flag(asset, "regz-24c-rate-as-apr")
    res = client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "met_elsewhere", "note": "APR in the footer"})
    dismissed = flag(res.json(), "regz-24c-rate-as-apr")
    assert (dismissed["status"], dismissed["reason"], dismissed["note"]) == ("dismissed", "met_elsewhere", "APR in the footer")
    assert dismissed["resolved_by"] == "Demo reviewer"
    assert res.json()["events"][0]["action"] == "flag_dismissed"


def test_dismiss_needs_a_known_reason(judged):
    f = flag(create(), "regz-24c-rate-as-apr")
    assert client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "busy"}).status_code == 422


def test_other_needs_a_note(judged):
    f = flag(create(), "regz-24c-rate-as-apr")
    assert client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "other", "note": "  "}).status_code == 422
    assert client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "other", "note": "Legacy copy"}).status_code == 200


def test_only_judgment_flags_can_be_acknowledged(judged):
    asset = create()
    assert client.post(f"/api/flags/{flag(asset, 'regz-24c-rate-as-apr')['id']}/acknowledge").status_code == 422
    assert client.post(f"/api/flags/{flag(asset, 'llm-udaap-misleading')['id']}/acknowledge").status_code == 200


def test_reopen_undoes_a_resolution(judged):
    f = flag(create(), "regz-24c-rate-as-apr")
    client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "false_positive"})
    reopened = client.post(f"/api/flags/{f['id']}/reopen").json()
    assert flag(reopened, "regz-24c-rate-as-apr")["status"] == "open"
    assert flag(reopened, "regz-24c-rate-as-apr")["reason"] is None
    assert reopened["events"][0]["action"] == "flag_reopened"


# --- decisions ---------------------------------------------------------------------------


def test_approve_is_blocked_until_every_flag_is_resolved(judged):
    asset = create()
    res = client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "approve"})
    assert res.status_code == 409
    assert "2 open flag" in res.json()["detail"]

    client.post(f"/api/flags/{flag(asset, 'regz-24c-rate-as-apr')['id']}/dismiss", json={"reason": "met_elsewhere"})
    client.post(f"/api/flags/{flag(asset, 'llm-udaap-misleading')['id']}/acknowledge")
    approved = client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "approve"}).json()
    assert approved["status"] == "approved"
    assert approved["decided_by"] == "Demo reviewer"


def test_reject_is_allowed_with_open_flags(judged):
    asset = create()
    res = client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "reject", "note": "Too many issues"})
    assert res.json()["status"] == "rejected"
    assert res.json()["decision_note"] == "Too many issues"


def test_decided_ads_are_locked(judged):
    asset = create()
    client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "reject"})
    f = flag(asset, "regz-24c-rate-as-apr")
    assert client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "false_positive"}).status_code == 409
    assert client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "approve"}).status_code == 409


# --- rules page stats (D7) ---------------------------------------------------------------


def test_rules_report_how_often_they_fire_and_get_dismissed(judged):
    for _ in range(2):
        f = flag(create(), "regz-24c-rate-as-apr")
        client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "met_elsewhere"})
    rule = next(r for r in client.get("/api/rules").json() if r["id"] == "regz-24c-rate-as-apr")
    assert rule["stats"] == {"flagged": 2, "dismissed": 2, "reasons": {"met_elsewhere": 2}}


# --- demo seed and reset (D14) -------------------------------------------------------------


def test_reset_restores_the_demo_queue(fake_model):
    seeds.seed()
    first = client.get("/api/assets").json()
    client.post(f"/api/assets/{first[0]['id']}/decision", json={"decision": "reject"})

    res = client.post("/api/demo/reset")
    assert res.json() == {"seeded": len(seeds.SEEDS)}
    after = client.get("/api/assets").json()
    assert len(after) == len(seeds.SEEDS)
    assert all(a["status"] == "in_review" for a in after)


def test_seeding_ignores_the_visitor_limit_and_reuses_stored_ai_results(fake_model):
    seeds.seed()
    calls = len(fake_model.prompts)
    assert calls == len(seeds.SEEDS)
    seeds.reset()
    assert len(fake_model.prompts) == calls  # second seed came from stored results


def test_hidden_text_seed_is_caught_by_the_code_backstop(fake_model):
    seeds.seed()
    widget = next(a for a in client.get("/api/assets").json() if a["title"] == "Loan comparison widget")
    detail = client.get(f"/api/assets/{widget['id']}").json()
    assert "security-injection" in [f["rule_id"] for f in detail["flags"]]


# --- throughput metrics --------------------------------------------------------------------


def test_metrics_start_empty():
    m = client.get("/api/metrics").json()
    assert m["in_review"] == 0 and m["median_decision_minutes"] is None and m["dismiss_rate"] is None


def test_metrics_track_queue_decisions_and_dismissals(judged):
    first, second = create(), create({**BAD_LOAN, "body": "Everyone qualifies! Loans at 4.99% interest."})
    client.post(f"/api/flags/{flag(first, 'regz-24c-rate-as-apr')['id']}/dismiss", json={"reason": "false_positive"})
    client.post(f"/api/flags/{flag(first, 'llm-udaap-misleading')['id']}/acknowledge")
    client.post(f"/api/assets/{first['id']}/decision", json={"decision": "approve"})

    m = client.get("/api/metrics").json()
    assert (m["in_review"], m["approved"], m["rejected"]) == (1, 1, 0)
    assert m["median_decision_minutes"] >= 0
    assert m["oldest_waiting_minutes"] >= 0
    assert m["flags_per_ad"] == 2
    assert m["dismiss_rate"] == 0.5  # 1 of 2 resolved flags was dismissed


def test_rule_health_lists_every_rule_that_fired(judged):
    asset = create()
    client.post(f"/api/flags/{flag(asset, 'regz-24c-rate-as-apr')['id']}/dismiss", json={"reason": "false_positive"})
    health = client.get("/api/metrics").json()["rule_health"]
    assert health == [
        {
            "rule_id": "regz-24c-rate-as-apr",
            "rule_name": "Rate not stated as APR",
            "type": "check_failed",
            "flagged": 1,
            "dismissed": 1,
            "top_reason": "false_positive",
        },
        {
            "rule_id": "llm-udaap-misleading",
            "rule_name": "Misleading or deceptive claim",
            "type": "needs_judgment",
            "flagged": 1,
            "dismissed": 0,
            "top_reason": None,
        },
    ]


def test_metrics_time_range_excludes_older_ads(judged):
    from datetime import datetime, timedelta, timezone

    from app.review import store as review_store
    from app.rules.models import Asset

    old = Asset(body="Loans at 6.99% interest.", product="personal_loan", channel="landing_page")
    review_store.create_asset(
        title="Old ad", submitter="Archive", asset=old, found=[], ai=_ai(), actor="x",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    create()
    assert client.get("/api/metrics").json()["submitted"] == 2
    week = client.get("/api/metrics?days=7").json()
    assert week["submitted"] == 1
    assert week["in_review"] == 2  # the backlog is always the current one


def _ai():
    from app.analysis import AIStatus

    return AIStatus(status="disabled", message="", remaining_this_hour=0)


def test_queue_items_list_the_rules_that_flagged_them(judged):
    create()
    [item] = client.get("/api/assets").json()
    assert sorted(item["rule_ids"]) == ["llm-udaap-misleading", "regz-24c-rate-as-apr"]


def test_rules_with_enough_flags_rank_above_small_samples(judged):
    for i in range(3):
        create({**BAD_LOAN, "body": f"Everyone qualifies! Loans at {i + 4}.99% interest."})
    small = create({**BAD_LOAN, "product": "mortgage", "body": "Talk to a counselor today."})
    client.post(f"/api/flags/{flag(small, 'regz-24i6-counselor')['id']}/dismiss", json={"reason": "false_positive"})
    order = [r["rule_id"] for r in client.get("/api/metrics").json()["rule_health"]]
    # The counselor rule is 100% dismissed, but on 1 flag: it ranks below rules with 3+ flags.
    assert order[-1] == "regz-24i6-counselor"
