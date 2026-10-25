"""
Tests for decision engine (engine/actions.py).
"""

import pytest
from engine.actions import (
    CAP_SHARE,
    FUTURE_FACTOR,
    HARM_BASE,
    HOLD_HOURS,
    TIE_TOL,
    decide,
)


def test_raju_reference():
    """
    Raju (balance 4000, tmin 1920, tmax 3000, S .01, harm .5, r 0, lam 1) -> lien ~1920.
    """
    row = {
        "account_id": "ACC_RAJU",
        "balance": 4000,
        "tainted_min": 1920,
        "tainted_max": 3000,
        "S": 0.01,
        "harm_score": 0.5,
        "recent_inflow": 0,
    }
    res = decide(row, lam=1)
    assert res["action"] == "lien"
    assert pytest.approx(res["lien_amount"], rel=1e-3) == 1920
    assert not res["needs_human"]
    assert "Rs" in res["note"]
    assert "1,920" in res["note"] or "1920" in res["note"]


def test_zero_tainted():
    """
    tmin=tmax=0, S .01 -> none.
    """
    row = {
        "account_id": "ACC_CLEAN",
        "balance": 5000,
        "tainted_min": 0,
        "tainted_max": 0,
        "S": 0.01,
        "harm_score": 0.5,
        "recent_inflow": 0,
    }
    res = decide(row, lam=1)
    assert res["action"] == "none"
    assert res["lien_amount"] == 0.0
    assert not res["needs_human"]


def test_mule_high_priority():
    """
    mule (100000, 95000, 100000, S .99, harm .5, r 50000, lam 1) -> timed_hold.
    """
    row = {
        "account_id": "ACC_MULE",
        "balance": 100000,
        "tainted_min": 95000,
        "tainted_max": 100000,
        "S": 0.99,
        "harm_score": 0.5,
        "recent_inflow": 50000,
    }
    res = decide(row, lam=1)
    assert res["action"] == "timed_hold"
    assert res["needs_human"]
    assert res["hold_hours"] == HOLD_HOURS
    assert res["lien_amount"] == 100000


def test_monotonicity_across_lambda():
    """
    For row (20000, 2000, 9000, S .4, harm .8, r 3000)
    restrictiveness never rises across lam [0, .1, .25, .5, 1, 2, 4, 8, 16]
    and lam=1e6 -> lien.
    """
    row = {
        "account_id": "ACC_TEST",
        "balance": 20000,
        "tainted_min": 2000,
        "tainted_max": 9000,
        "S": 0.4,
        "harm_score": 0.8,
        "recent_inflow": 3000,
    }
    rank = {"none": 0, "lien": 1, "lien_cap": 2, "timed_hold": 3}
    lambdas = [0, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16]

    actions = [decide(row, lam=l)["action"] for l in lambdas]
    ranks = [rank[a] for a in actions]

    # As lambda increases, penalty on clean blocked increases, so restrictiveness should never rise
    for i in range(len(ranks) - 1):
        assert ranks[i + 1] <= ranks[i], f"Restrictiveness rose from lam={lambdas[i]} to {lambdas[i+1]}"

    # Extreme lambda penalty -> lien
    res_large_lam = decide(row, lam=1e6)
    assert res_large_lam["action"] == "lien"


def test_lambda_negative_error():
    """lam < 0 -> ValueError."""
    row = {
        "account_id": "ACC_1",
        "balance": 1000,
        "tainted_min": 100,
        "tainted_max": 200,
        "S": 0.1,
        "harm_score": 0.2,
    }
    with pytest.raises(ValueError):
        decide(row, lam=-1)


def test_missing_key_error():
    """missing key -> KeyError."""
    row = {
        "account_id": "ACC_1",
        "balance": 1000,
        "tainted_min": 100,
        "tainted_max": 200,
        "S": 0.1,
        # harm_score missing
    }
    with pytest.raises(KeyError):
        decide(row, lam=1)
