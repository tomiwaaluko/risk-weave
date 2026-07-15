"""Evaluation-dashboard endpoint tests (RIS-21, `RW-OPS-001`, §15)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from riskweave_api.main import app

client = TestClient(app)


def test_report_endpoint_returns_all_six_families():
    resp = client.get("/evaluation/report")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["families"]) == 6
    assert {row["family"] for row in body["rows"]} == set(body["families"])
    assert body["snapshot_id"]
    assert body["generated_at"]


def test_report_endpoint_marks_pass_fail_per_row():
    body = client.get("/evaluation/report").json()
    # Every row is either informational (passed=None) or an explicit bool the
    # UI can paint green/red — a miss is never hidden (RW-SAFE-003 spirit).
    for row in body["rows"]:
        assert row["passed"] in (True, False, None)
        assert row["target_display"]
        assert row["actual_display"]
    assert body["all_passed"] is True


def test_report_endpoint_is_read_only_and_unauthenticated():
    # No bearer key required; the quality view must render in the demo build.
    resp = client.get("/evaluation/report")
    assert resp.status_code == 200
