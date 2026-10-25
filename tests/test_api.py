"""
Tests for Smart Freeze FastAPI backend.
"""

from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)

FORBIDDEN_TERMS = ["is_mule", "role", "mule_ids", "victim_ids"]


def check_no_forbidden_terms(response_text: str) -> None:
    for term in FORBIDDEN_TERMS:
        assert term not in response_text, f"Forbidden term '{term}' found in response: {response_text}"


def test_scams_endpoint():
    res = client.get("/api/scams")
    assert res.status_code == 200
    check_no_forbidden_terms(res.text)

    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert set(first.keys()) == {"scam_id", "start_time", "total_stolen"}


def test_endpoints_on_first_scam():
    # 1. Scams
    res_scams = client.get("/api/scams")
    assert res_scams.status_code == 200
    check_no_forbidden_terms(res_scams.text)
    scam_id = res_scams.json()[0]["scam_id"]

    # 2. Graph
    res_graph = client.get(f"/api/graph?scam_id={scam_id}&delay=60")
    assert res_graph.status_code == 200
    check_no_forbidden_terms(res_graph.text)
    graph_data = res_graph.json()
    assert set(graph_data.keys()) == {"nodes", "edges", "start_time", "as_of"}
    assert len(graph_data["nodes"]) > 0
    assert set(graph_data["nodes"][0].keys()) == {"id", "type", "balance", "tainted_min", "tainted_max", "S"}
    if len(graph_data["edges"]) > 0:
        assert set(graph_data["edges"][0].keys()) == {"src", "dst", "amount", "time"}

    # 3. Decisions
    res_dec = client.get(f"/api/decisions?scam_id={scam_id}&delay=60&lam=0.05")
    assert res_dec.status_code == 200
    check_no_forbidden_terms(res_dec.text)
    dec_data = res_dec.json()
    assert isinstance(dec_data, list)
    assert len(dec_data) > 0
    expected_dec_keys = {
        "account_id", "type", "balance", "tainted_min", "tainted_max",
        "S", "action", "lien_amount", "cap_share", "hold_hours", "needs_human", "note"
    }
    assert set(dec_data[0].keys()) == expected_dec_keys

    target_acc = next((d["account_id"] for d in dec_data if d["S"] > 0.0), dec_data[0]["account_id"])

    # 4. Account
    res_acc = client.get(f"/api/account?account_id={target_acc}&scam_id={scam_id}&delay=60&lam=0.05")
    assert res_acc.status_code == 200
    check_no_forbidden_terms(res_acc.text)
    acc_data = res_acc.json()
    expected_acc_keys = {
        "balance", "type", "tainted_prop", "tainted_fifo", "tainted_libr",
        "tainted_min", "tainted_max", "S", "B", "T", "H", "reasons_for",
        "reasons_against", "harm_score", "cover_days", "float_need",
        "salary_dependence", "thin_cover", "decision", "blanket", "smart"
    }
    assert set(acc_data.keys()) == expected_acc_keys
    assert set(acc_data["blanket"].keys()) == {"held", "clean_low", "clean_high"}
    assert set(acc_data["smart"].keys()) == {"held", "clean_low", "clean_high"}

    # 5. WhatIf: evidence_count=4 gives S_new below S
    res_whatif = client.post(
        "/api/whatif",
        json={
            "account_id": target_acc,
            "scam_id": scam_id,
            "delay": 60,
            "lam": 0.05,
            "evidence_count": 4,
        },
    )
    assert res_whatif.status_code == 200
    check_no_forbidden_terms(res_whatif.text)
    whatif_data = res_whatif.json()
    assert set(whatif_data.keys()) == {"before", "after"}
    assert set(whatif_data["before"].keys()) == {"S", "action", "held"}
    assert set(whatif_data["after"].keys()) == {"S", "action", "held"}
    assert whatif_data["after"]["S"] < whatif_data["before"]["S"]

    # 6. Trade-off
    res_tradeoff = client.get("/api/tradeoff?delay=60")
    assert res_tradeoff.status_code == 200
    check_no_forbidden_terms(res_tradeoff.text)
    tradeoff_data = res_tradeoff.json()
    assert isinstance(tradeoff_data, list)
    assert len(tradeoff_data) > 0
    assert "policy" in tradeoff_data[0]
    assert "rec_rate_mean" in tradeoff_data[0]


def test_unknown_scam_or_account_returns_404():
    res_bad_scam = client.get("/api/graph?scam_id=UNKNOWN_SCAM&delay=60")
    assert res_bad_scam.status_code == 404
    check_no_forbidden_terms(res_bad_scam.text)

    res_bad_dec = client.get("/api/decisions?scam_id=UNKNOWN_SCAM&delay=60&lam=0.05")
    assert res_bad_scam.status_code == 404
    check_no_forbidden_terms(res_bad_dec.text)

    res_bad_acc = client.get("/api/account?account_id=UNKNOWN_ACC&scam_id=S01&delay=60&lam=0.05")
    assert res_bad_acc.status_code == 404
    check_no_forbidden_terms(res_bad_acc.text)


def test_bad_delay_returns_422():
    res_bad_delay = client.get("/api/graph?scam_id=S01&delay=99")
    assert res_bad_delay.status_code == 422
    check_no_forbidden_terms(res_bad_delay.text)

    res_bad_tradeoff = client.get("/api/tradeoff?delay=99")
    assert res_bad_tradeoff.status_code == 422
    check_no_forbidden_terms(res_bad_tradeoff.text)
