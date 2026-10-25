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


def test_decide_all_on_data():
    """
    Test decide_all on data/*.csv for the first scam_id in data/scam_truth.csv:
    one row per account, no NaN, valid actions;
    scrambling is_mule/role in inputs leaves the output unchanged.
    """
    from pathlib import Path
    import numpy as np
    import pandas as pd
    from engine.actions import decide_all
    from engine.harm import harm_all
    from engine.score import score_all
    from engine.taint import trace

    data_dir = Path(__file__).resolve().parent.parent / "data"
    accounts = pd.read_csv(data_dir / "accounts.csv")
    txns = pd.read_csv(data_dir / "transactions.csv")
    scam_truth = pd.read_csv(data_dir / "scam_truth.csv")
    account_truth = pd.read_csv(data_dir / "account_truth.csv")

    first_scam_id = scam_truth.iloc[0]["scam_id"]
    trace_df = trace(accounts, txns, first_scam_id)
    scores_df = score_all(accounts, txns, seed=42)
    harm_df = harm_all(accounts, txns)

    first_scam_start = float(scam_truth.iloc[0]["start_time"])
    dec_df = decide_all(trace_df, scores_df, harm_df, txns, as_of=first_scam_start + 120, lam=1.0)

    # 1. One row per trace_df account
    assert len(dec_df) == len(trace_df)
    assert list(dec_df["account_id"]) == list(trace_df["account_id"])

    # 2. No NaN values in any column (losses is dict, others numeric/str)
    for col in dec_df.columns:
        if col != "losses":
            assert not dec_df[col].isna().any(), f"NaN found in column {col}"

    # 3. Valid actions
    valid_actions = {"none", "lien", "lien_cap", "timed_hold"}
    assert set(dec_df["action"]).issubset(valid_actions)

    # 4. Scrambling is_mule / role leaves output unchanged
    # (decide_all itself never reads is_mule or role)
    accounts_scrambled = accounts.copy()
    rng = np.random.default_rng(999)
    accounts_scrambled["is_mule"] = rng.permutation(accounts_scrambled["is_mule"].values)

    # Scramble role in account_truth as well if passed
    trace_df_scrambled = trace(accounts_scrambled, txns, first_scam_id)
    dec_df_scrambled = decide_all(trace_df_scrambled, scores_df, harm_df, txns, as_of=first_scam_start + 120, lam=1.0)

    pd.testing.assert_frame_equal(dec_df, dec_df_scrambled)


def test_decide_all_missing_defaults():
    """
    Missing from scores_df -> S=0.
    Missing from harm_df -> harm_score=0.5.
    as_of=None -> recent_inflow=0.
    """
    import pandas as pd
    from engine.actions import decide_all

    trace_df = pd.DataFrame([
        {"account_id": "ACC_X", "balance": 5000.0, "tainted_min": 1000.0, "tainted_max": 2000.0}
    ])
    # Empty scores and harm
    scores_df = pd.DataFrame(columns=["account_id", "S"])
    harm_df = pd.DataFrame(columns=["harm_score"]).set_index(pd.Index([], name="account_id"))
    txns = pd.DataFrame(columns=["time", "dst", "amount"])

    res = decide_all(trace_df, scores_df, harm_df, txns, as_of=None, lam=1.0)
    assert len(res) == 1
    # When S=0, s = tmin = 1000.
    # harm_score = 0.5.
    # clean = 5000 - 1000 = 4000.
    assert res.iloc[0]["action"] == "lien"
    assert res.iloc[0]["lien_amount"] == 1000.0

