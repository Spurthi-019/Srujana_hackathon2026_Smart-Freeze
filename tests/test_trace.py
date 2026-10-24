"""
Tests for the tracing engine in engine.taint.

Convention:
- An account's opening_balance is clean money and counts as the OLDEST money (relevant for FIFO).
- Taint is seeded only by txns whose scam_id equals the given scam_id and whose src is a victim account.
- The victim's own balance is never tainted.
- trace(accounts, txns, scam_id) -> DataFrame with columns:
  [account_id, balance, tainted_prop, tainted_fifo, tainted_libr, tainted_min, tainted_max]
- Returns one row for EVERY account in accounts.
"""

import pandas as pd
import pytest
from engine.taint import trace


@pytest.fixture
def reference_data():
    accounts = pd.DataFrame([
        {"account_id": "V", "type": "victim", "age_days": 1000, "avg_monthly_inflow": 0, "opening_balance": 10000.0, "is_mule": 0},
        {"account_id": "R", "type": "salaried", "age_days": 1000, "avg_monthly_inflow": 0, "opening_balance": 1000.0, "is_mule": 0},
        {"account_id": "C", "type": "salaried", "age_days": 1000, "avg_monthly_inflow": 0, "opening_balance": 5000.0, "is_mule": 0},
        {"account_id": "X1", "type": "merchant", "age_days": 1000, "avg_monthly_inflow": 0, "opening_balance": 0.0, "is_mule": 0},
        {"account_id": "X2", "type": "merchant", "age_days": 1000, "avg_monthly_inflow": 0, "opening_balance": 0.0, "is_mule": 0},
    ])

    txns = pd.DataFrame([
        {"txn_id": "1", "time": 1, "src": "V", "dst": "R", "amount": 4000.0, "scam_id": "S01"},
        {"txn_id": "2", "time": 2, "src": "R", "dst": "X1", "amount": 2000.0, "scam_id": ""},
        {"txn_id": "3", "time": 3, "src": "C", "dst": "R", "amount": 2000.0, "scam_id": ""},
        {"txn_id": "4", "time": 4, "src": "R", "dst": "X2", "amount": 1000.0, "scam_id": ""},
    ])

    return accounts, txns


def test_reference_case(reference_data):
    """Test 1: Reference case checking expected taint values per method across accounts."""
    accounts, txns = reference_data
    df = trace(accounts, txns, "S01")

    expected_cols = [
        "account_id",
        "balance",
        "tainted_prop",
        "tainted_fifo",
        "tainted_libr",
        "tainted_min",
        "tainted_max",
    ]
    assert list(df.columns) == expected_cols
    assert len(df) == len(accounts)

    by_id = df.set_index("account_id")

    # R: balance 4000, tainted_prop 1920, tainted_fifo 2000, tainted_libr 3000, tainted_min 1920, tainted_max 3000
    r = by_id.loc["R"]
    assert r["balance"] == pytest.approx(4000.0, abs=0.01)
    assert r["tainted_prop"] == pytest.approx(1920.0, abs=0.01)
    assert r["tainted_fifo"] == pytest.approx(2000.0, abs=0.01)
    assert r["tainted_libr"] == pytest.approx(3000.0, abs=0.01)
    assert r["tainted_min"] == pytest.approx(1920.0, abs=0.01)
    assert r["tainted_max"] == pytest.approx(3000.0, abs=0.01)

    # X1: balance 2000, prop 1600, fifo 1000, libr 1000
    x1 = by_id.loc["X1"]
    assert x1["balance"] == pytest.approx(2000.0, abs=0.01)
    assert x1["tainted_prop"] == pytest.approx(1600.0, abs=0.01)
    assert x1["tainted_fifo"] == pytest.approx(1000.0, abs=0.01)
    assert x1["tainted_libr"] == pytest.approx(1000.0, abs=0.01)
    assert x1["tainted_min"] == pytest.approx(1000.0, abs=0.01)
    assert x1["tainted_max"] == pytest.approx(1600.0, abs=0.01)

    # X2: balance 1000, prop 480, fifo 1000, libr 0
    x2 = by_id.loc["X2"]
    assert x2["balance"] == pytest.approx(1000.0, abs=0.01)
    assert x2["tainted_prop"] == pytest.approx(480.0, abs=0.01)
    assert x2["tainted_fifo"] == pytest.approx(1000.0, abs=0.01)
    assert x2["tainted_libr"] == pytest.approx(0.0, abs=0.01)
    assert x2["tainted_min"] == pytest.approx(0.0, abs=0.01)
    assert x2["tainted_max"] == pytest.approx(1000.0, abs=0.01)

    # V: balance 6000, all tainted columns 0
    v = by_id.loc["V"]
    assert v["balance"] == pytest.approx(6000.0, abs=0.01)
    assert v["tainted_prop"] == pytest.approx(0.0, abs=0.01)
    assert v["tainted_fifo"] == pytest.approx(0.0, abs=0.01)
    assert v["tainted_libr"] == pytest.approx(0.0, abs=0.01)
    assert v["tainted_min"] == pytest.approx(0.0, abs=0.01)
    assert v["tainted_max"] == pytest.approx(0.0, abs=0.01)

    # C: balance 3000, all tainted columns 0
    c = by_id.loc["C"]
    assert c["balance"] == pytest.approx(3000.0, abs=0.01)
    assert c["tainted_prop"] == pytest.approx(0.0, abs=0.01)
    assert c["tainted_fifo"] == pytest.approx(0.0, abs=0.01)
    assert c["tainted_libr"] == pytest.approx(0.0, abs=0.01)
    assert c["tainted_min"] == pytest.approx(0.0, abs=0.01)
    assert c["tainted_max"] == pytest.approx(0.0, abs=0.01)


def test_invariants(reference_data):
    """Test 2: Invariants on the reference case."""
    accounts, txns = reference_data
    df = trace(accounts, txns, "S01")

    # For every row: 0 <= tainted_min <= tainted_max <= balance
    for _, row in df.iterrows():
        b = row["balance"]
        t_min = row["tainted_min"]
        t_max = row["tainted_max"]
        p = row["tainted_prop"]
        f = row["tainted_fifo"]
        l = row["tainted_libr"]

        assert 0.0 <= t_min + 1e-6, f"tainted_min < 0 for {row['account_id']}"
        assert t_min <= t_max + 1e-6, f"tainted_min > tainted_max for {row['account_id']}"
        assert t_max <= b + 1e-6, f"tainted_max > balance for {row['account_id']}"

        # tainted_min equals min of three methods and tainted_max equals max
        assert t_min == pytest.approx(min(p, f, l), abs=0.01)
        assert t_max == pytest.approx(max(p, f, l), abs=0.01)

    # Total balance across accounts equals total opening balance (conservation of money)
    assert df["balance"].sum() == pytest.approx(accounts["opening_balance"].sum(), abs=0.01)


def test_nonexistent_scam(reference_data):
    """Test 3: Calling trace with a nonexistent scam_id returns all tainted columns equal to 0."""
    accounts, txns = reference_data
    df = trace(accounts, txns, "NONEXISTENT_SCAM")

    assert (df["tainted_prop"] == 0.0).all()
    assert (df["tainted_fifo"] == 0.0).all()
    assert (df["tainted_libr"] == 0.0).all()
    assert (df["tainted_min"] == 0.0).all()
    assert (df["tainted_max"] == 0.0).all()

    # Balances should still reflect transactions
    assert df["balance"].sum() == pytest.approx(accounts["opening_balance"].sum(), abs=0.01)
