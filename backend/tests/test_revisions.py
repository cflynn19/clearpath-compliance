from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AD = {
    "product": "personal_loan",
    "channel": "landing_page",
    "body": "Personal loans at 5.99% interest, just $199/month. Talk to us today.",
}


def flag(asset, rule_id):
    return next(f for f in asset["flags"] if f["rule_id"] == rule_id)


def request_changes(asset, note="Add the APR and terms"):
    res = client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "request_changes", "note": note})
    assert res.status_code == 200, res.text
    return res.json()


def revise(asset, body):
    res = client.post(f"/api/assets/{asset['id']}/revisions", json={"body": body})
    assert res.status_code == 200, res.text
    return res.json()


def test_request_changes_sends_the_ad_back_with_its_open_flags(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    back = request_changes(asset)
    assert back["status"] == "needs_changes"
    assert back["decided_by"] is None  # not a final decision
    assert back["events"][0]["action"] == "changes_requested"
    assert back["events"][0]["detail"] == {"note": "Add the APR and terms", "open_flags": 2}
    # Flags are locked while the ad is with the submitter.
    f = flag(back, "regz-24c-rate-as-apr")
    assert client.post(f"/api/flags/{f['id']}/dismiss", json={"reason": "false_positive"}).status_code == 409


def test_revision_is_checked_again_and_compared_with_the_last_version(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    request_changes(asset)
    v2 = revise(asset, "Personal loans from 5.99% APR, terms of 36 to 60 months. Talk to a counselor today.")
    assert v2["status"] == "in_review"
    assert v2["version"]["number"] == 2
    assert v2["comparison"] == {
        "version": 2,
        "fixed": ["Rate not stated as APR", "Trigger term without full disclosure"],
        "still_flagged": [],
        "new": [],
        "carried_over": 0,
    }
    assert v2["flags"] == []  # "counselor" only matters in mortgage ads


def test_resolutions_carry_over_when_the_same_rule_fires_on_the_same_text(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    client.post(
        f"/api/flags/{flag(asset, 'regz-24c-rate-as-apr')['id']}/dismiss",
        json={"reason": "met_elsewhere", "note": "APR is on the linked rates page"},
    )
    request_changes(asset)
    # Fixes the payment disclosure but keeps the same "5.99% interest" wording.
    v2 = revise(asset, "Personal loans at 5.99% interest, with repayment terms of 36 to 60 months at 5.99% APR.")
    carried = flag(v2, "regz-24c-rate-as-apr")
    assert carried["status"] == "dismissed" and carried["carried_over"] is True
    assert carried["note"] == "APR is on the linked rates page"
    assert v2["comparison"]["carried_over"] == 1
    assert v2["comparison"]["fixed"] == ["Trigger term without full disclosure"]


def test_changed_text_reopens_the_flag(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    client.post(f"/api/flags/{flag(asset, 'regz-24c-rate-as-apr')['id']}/dismiss", json={"reason": "false_positive"})
    request_changes(asset)
    v2 = revise(asset, "Personal loans at 4.99% interest, just $199/month for 36 months at 4.99% APR.")
    reopened = flag(v2, "regz-24c-rate-as-apr")
    assert reopened["status"] == "open" and reopened["carried_over"] is False
    assert "Rate not stated as APR" in v2["comparison"]["still_flagged"]


def test_old_versions_flags_dont_block_approving_the_new_one(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    request_changes(asset)
    v2 = revise(asset, "Personal loans from 5.99% APR with terms of 36 to 60 months.")
    res = client.post(f"/api/assets/{v2['id']}/decision", json={"decision": "approve"})
    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_revisions_only_after_changes_are_requested(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    res = client.post(f"/api/assets/{asset['id']}/revisions", json={"body": "New copy"})
    assert res.status_code == 409


def test_an_ad_waiting_on_the_submitter_can_still_be_rejected(fake_model):
    asset = client.post("/api/assets", json=AD).json()
    request_changes(asset)
    res = client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "reject", "note": "Withdrawn"})
    assert res.json()["status"] == "rejected"
    assert client.post(f"/api/assets/{asset['id']}/decision", json={"decision": "approve"}).status_code == 409
