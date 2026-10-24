import numpy as np
import pandas as pd
import pytest
from sim.normal import generate_normal


def test_reproducibility():
    """Same seed gives identical output."""
    accs1, txns1 = generate_normal(seed=42)
    accs2, txns2 = generate_normal(seed=42)

    pd.testing.assert_frame_equal(accs1, accs2)
    pd.testing.assert_frame_equal(txns1, txns2)

    # Different seed gives different output
    accs3, txns3 = generate_normal(seed=999)
    assert not accs1.equals(accs3) or not txns1.equals(txns3)


def test_required_columns():
    """Required columns exist and have correct types."""
    accs, txns = generate_normal(seed=42)

    expected_acc_cols = [
        "account_id",
        "type",
        "age_days",
        "avg_monthly_inflow",
        "opening_balance",
        "is_mule",
    ]
    expected_txn_cols = ["txn_id", "time", "src", "dst", "amount", "scam_id"]

    assert list(accs.columns) == expected_acc_cols
    assert list(txns.columns) == expected_txn_cols

    # is_mule should be 0 for all
    assert (accs["is_mule"] == 0).all()

    # scam_id should be blank for all
    assert (txns["scam_id"] == "").all()

    # types
    valid_types = {"salaried", "merchant", "gig", "aggregator"}
    assert set(accs["type"].unique()).issubset(valid_types)

    # time within 0..43200
    assert (txns["time"] >= 0).all()
    assert (txns["time"] <= 43200).all()


def test_account_count_and_aggregators():
    """Account count within 450-550; at least 3 aggregators."""
    accs, txns = generate_normal(seed=42)

    assert 450 <= len(accs) <= 550
    agg_count = (accs["type"] == "aggregator").sum()
    assert agg_count >= 3


def test_no_negative_running_balance():
    """Hard rule: No negative running balance for any account at any point in simulation."""
    accs, txns = generate_normal(seed=42)

    balances = dict(zip(accs["account_id"], accs["opening_balance"].astype(float)))

    # Ensure initial balances are non-negative
    for aid, bal in balances.items():
        assert bal >= 0, f"Account {aid} started with negative balance: {bal}"

    # Verify transactions are in chronological order
    times = txns["time"].tolist()
    assert times == sorted(times), "Transactions are not strictly in time order"

    for _, row in txns.iterrows():
        src = row["src"]
        dst = row["dst"]
        amt = float(row["amount"])

        assert amt > 0, f"Non-positive transaction amount: {amt}"
        assert balances[src] >= amt - 1e-6, (
            f"Account {src} had insufficient balance ({balances[src]}) for txn of {amt}"
        )

        balances[src] -= amt
        balances[dst] += amt

        # Assert no negative balance
        assert balances[src] >= -1e-6, f"Account {src} went negative: {balances[src]}"
