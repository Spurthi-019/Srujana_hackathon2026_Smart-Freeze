"""
Tests for evaluation harness in eval.harness.
"""

from pathlib import Path
import pandas as pd
import pytest

from engine.taint import trace
from eval.harness import evaluate_all, replay_scam_txns


def test_chain_replay():
    """
    3-account chain (V->M1 scam, M1->M2, M2->exit later), as_of after hop 1:
    hold on M1 recovers all, none recovers 0, lien of half recovers half.
    """
    accounts = pd.DataFrame([
        {"account_id": "V", "type": "victim", "opening_balance": 1000.0, "is_mule": 0},
        {"account_id": "M1", "type": "mule", "opening_balance": 0.0, "is_mule": 1},
        {"account_id": "M2", "type": "mule", "opening_balance": 0.0, "is_mule": 1},
        {"account_id": "EXIT", "type": "exit", "opening_balance": 0.0, "is_mule": 0},
    ])

    txns = pd.DataFrame([
        {"txn_id": "1", "time": 10, "src": "V", "dst": "M1", "amount": 100.0, "scam_id": "S1"},
        {"txn_id": "2", "time": 30, "src": "M1", "dst": "M2", "amount": 100.0, "scam_id": "S1"},
        {"txn_id": "3", "time": 40, "src": "M2", "dst": "EXIT", "amount": 100.0, "scam_id": "S1"},
    ])

    # as_of = 20 (after hop 1, before hop 2)
    as_of = 20
    trace_df = trace(accounts, txns, "S1", as_of=as_of)

    # 1. hold on M1 recovers all (100)
    act_hold = {"M1": {"action": "timed_hold", "lien_amount": 100.0, "cap_share": 0.0}}
    rec_hold = replay_scam_txns(accounts, txns, "S1", as_of, trace_df, act_hold)
    assert rec_hold == pytest.approx(100.0, abs=1e-5)

    # 2. none recovers 0
    act_none = {"M1": {"action": "none", "lien_amount": 0.0, "cap_share": 0.0}}
    rec_none = replay_scam_txns(accounts, txns, "S1", as_of, trace_df, act_none)
    assert rec_none == pytest.approx(0.0, abs=1e-5)

    # 3. lien of half (50) on M1 recovers half (50)
    act_lien_half = {"M1": {"action": "lien", "lien_amount": 50.0, "cap_share": 0.0}}
    rec_lien_half = replay_scam_txns(accounts, txns, "S1", as_of, trace_df, act_lien_half)
    assert rec_lien_half == pytest.approx(50.0, abs=1e-5)


def test_harness_on_data():
    """
    On simulated data:
    recovered <= total_stolen for every row,
    and blanket recovered >= lien_only recovered.
    """
    data_dir = Path(__file__).resolve().parent.parent / "data"
    acc_path = data_dir / "accounts.csv"
    txn_path = data_dir / "transactions.csv"
    scam_path = data_dir / "scam_truth.csv"

    if not (acc_path.exists() and txn_path.exists() and scam_path.exists()):
        pytest.skip("Data files do not exist.")

    accounts = pd.read_csv(acc_path)
    txns = pd.read_csv(txn_path)
    scams = pd.read_csv(scam_path)

    results_df, diag = evaluate_all(accounts, txns, scams)

    # recovered <= total_stolen for every row
    for _, row in results_df.iterrows():
        assert row["recovered"] <= row["total_stolen"] + 1e-2, (
            f"Policy {row['policy']} recovered {row['recovered']} > total_stolen {row['total_stolen']}"
        )

    # blanket recovered >= lien_only recovered
    blanket_rec = results_df.loc[results_df["policy"] == "blanket", "recovered"].iloc[0]
    lien_rec = results_df.loc[results_df["policy"] == "lien_only", "recovered"].iloc[0]
    assert blanket_rec >= lien_rec - 1e-2, (
        f"Blanket recovered {blanket_rec} < Lien recovered {lien_rec}"
    )


def test_innocent_only_harm():
    """
    clean_low/clean_high equal the sum over non-mule accounts only
    (small hand-built case with one mule and one innocent).
    """
    from engine.harm import innocent_blocked
    from eval.harness import compute_policy_harm_metrics

    accounts = pd.DataFrame([
        {"account_id": "MULE_1", "type": "mule", "is_mule": 1},
        {"account_id": "INNOCENT_1", "type": "salaried", "is_mule": 0},
    ])

    trace_df = pd.DataFrame([
        {
            "account_id": "MULE_1",
            "balance": 1000.0,
            "tainted_min": 200.0,
            "tainted_max": 500.0,
        },
        {
            "account_id": "INNOCENT_1",
            "balance": 800.0,
            "tainted_min": 100.0,
            "tainted_max": 300.0,
        },
    ])

    actions_dict = {
        "MULE_1": {"action": "timed_hold", "lien_amount": 1000.0, "cap_share": 0.0},
        "INNOCENT_1": {"action": "timed_hold", "lien_amount": 800.0, "cap_share": 0.0},
    }

    metrics = compute_policy_harm_metrics(accounts, trace_df, actions_dict)

    # Harm on innocent only:
    # INNOCENT_1: held=800, balance=800, tmin=100, tmax=300
    # low = max(0, 800 - 300) = 500
    # high = max(0, 800 - 100) = 700
    expected_innocent_blocked = innocent_blocked(800.0, 100.0, 300.0, 800.0)

    assert metrics["clean_low"] == pytest.approx(expected_innocent_blocked["low"], abs=1e-5)
    assert metrics["clean_high"] == pytest.approx(expected_innocent_blocked["high"], abs=1e-5)
    assert metrics["innocent_touched"] == 1
    assert metrics["holds_on_innocents"] == 1
    assert metrics["mules_actioned"] == 1

