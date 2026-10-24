"""
Tests for harm model (engine/harm.py).
"""

import os
import numpy as np
import pandas as pd
import pytest

from engine.harm import harm_all, innocent_blocked
from sim.build import build_all


@pytest.fixture(scope="module")
def sim_data():
    accounts_path = os.path.join("data", "accounts.csv")
    txns_path = os.path.join("data", "transactions.csv")
    if os.path.exists(accounts_path) and os.path.exists(txns_path):
        accounts = pd.read_csv(accounts_path)
        txns = pd.read_csv(txns_path)
    else:
        accounts, txns, _, _ = build_all(42)
    return accounts, txns


def test_harm_all_basic(sim_data):
    accounts, txns = sim_data
    df = harm_all(accounts, txns)

    # One row per account
    assert len(df) == len(accounts)
    assert set(df.index) == set(accounts["account_id"])

    # No NaN in columns
    for col in ["harm_score", "salary_dependence", "float_need", "thin_cover", "cover_days"]:
        assert not df[col].isna().any(), f"NaN found in {col}"

    # All harm_score within [0, 1]
    assert (df["harm_score"] >= 0.0).all()
    assert (df["harm_score"] <= 1.0).all()


def test_merchant_float_need_higher_than_gig(sim_data):
    accounts, txns = sim_data
    df = harm_all(accounts, txns)
    acc_map = accounts.set_index("account_id")["type"]

    merchant_float = df.loc[acc_map == "merchant", "float_need"]
    gig_float = df.loc[acc_map == "gig", "float_need"]

    assert len(merchant_float) > 0
    assert len(gig_float) > 0
    assert merchant_float.mean() > gig_float.mean()


def test_salaried_dependence(sim_data):
    accounts, txns = sim_data
    df = harm_all(accounts, txns)
    acc_map = accounts.set_index("account_id")["type"]

    salaried_dep = df.loc[acc_map == "salaried", "salary_dependence"]
    assert len(salaried_dep) > 0
    assert (salaried_dep > 0.5).any()


def test_as_of_filtering(sim_data):
    accounts, txns = sim_data
    as_of = 5000
    df1 = harm_all(accounts, txns, as_of=as_of)
    df2 = harm_all(accounts, txns[txns["time"] <= as_of], as_of=as_of)

    pd.testing.assert_frame_equal(df1, df2)


def test_truth_independence(sim_data):
    accounts, txns = sim_data
    accounts_shuffled = accounts.copy()
    rng = np.random.default_rng(42)
    accounts_shuffled["is_mule"] = rng.permutation(accounts_shuffled["is_mule"].values)

    df1 = harm_all(accounts, txns)
    df2 = harm_all(accounts_shuffled, txns)

    pd.testing.assert_frame_equal(df1, df2)


def test_innocent_blocked():
    # innocent_blocked(4000, 1920, 3000, 4000) == {"low": 1000, "high": 2080}
    res = innocent_blocked(4000, 1920, 3000, 4000)
    assert res == {"low": 1000.0, "high": 2080.0}

    # held 0 gives low 0 and high 0
    res0 = innocent_blocked(4000, 1920, 3000, 0)
    assert res0 == {"low": 0.0, "high": 0.0}

    # held 3000 gives low 0 and high 1080
    res3000 = innocent_blocked(4000, 1920, 3000, 3000)
    assert res3000 == {"low": 0.0, "high": 1080.0}

    # held above balance is clipped (e.g. balance 4000, held 6000 -> clipped to 4000)
    res_clip = innocent_blocked(4000, 1920, 3000, 6000)
    assert res_clip == {"low": 1000.0, "high": 2080.0}
