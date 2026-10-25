from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score
from engine.features import build_features
from engine.score import mule_score, score_all
from sim.build import build_all


@pytest.fixture(scope="module")
def sim_data():
    """Builds frames once or loads from data/."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    acc_path = data_dir / "accounts.csv"
    txn_path = data_dir / "transactions.csv"
    truth_path = data_dir / "account_truth.csv"

    if not (acc_path.exists() and txn_path.exists() and truth_path.exists()):
        accounts, txns, _, account_truth = build_all(42)
    else:
        accounts = pd.read_csv(acc_path)
        txns = pd.read_csv(txn_path)
        account_truth = pd.read_csv(truth_path)

    features_df = build_features(accounts, txns)
    scores_df = score_all(accounts, txns, seed=42)
    return accounts, txns, account_truth, scores_df, features_df


def test_features_clean_and_exclusions(sim_data):
    """Features have no NaN or inf; victim and exit accounts are absent."""
    accounts, txns, _, _, features_df = sim_data

    # No NaN or inf
    assert not features_df.isna().any().any()
    assert not np.isinf(features_df.values).any()

    # Exclude victim and exit
    excluded_ids = set(accounts[accounts["type"].isin(["victim", "exit"])]["account_id"])
    assert not any(aid in features_df.index for aid in excluded_ids)


def test_scores_dataframe_structure(sim_data):
    """S within [0,1]; every scored account has all columns."""
    _, _, _, scores_df, _ = sim_data
    expected_cols = [
        "account_id",
        "S",
        "B",
        "T",
        "H",
        "reasons_for",
        "reasons_against",
        "is_mule",
    ]
    assert list(scores_df.columns) == expected_cols

    # S in [0, 1]
    assert (scores_df["S"] >= 0.0).all()
    assert (scores_df["S"] <= 1.0).all()


def test_auc_performance(sim_data):
    """Out-of-fold ROC AUC for is_mule at least 0.90."""
    _, _, _, scores_df, _ = sim_data
    auc = roc_auc_score(scores_df["is_mule"], scores_df["S"])
    assert auc >= 0.90, f"OOF AUC {auc:.4f} is below 0.90"


def test_mule_vs_non_mule_separation(sim_data):
    """
    Mean S of mules is greater than mean S of non-mules;
    mean S of accounts with role 'bystander' is lower than mean S of mules.
    """
    _, _, account_truth, scores_df, _ = sim_data
    merged = scores_df.merge(account_truth[["account_id", "role"]], on="account_id")

    mean_s_mules = merged[merged["role"] == "mule"]["S"].mean()
    mean_s_non_mules = merged[merged["role"] != "mule"]["S"].mean()
    mean_s_bystanders = merged[merged["role"] == "bystander"]["S"].mean()

    assert mean_s_mules > mean_s_non_mules
    assert mean_s_bystanders < mean_s_mules


def test_reasons_for_mules(sim_data):
    """Every mule with S above 0.5 has at least one entry in reasons_for."""
    _, _, account_truth, scores_df, _ = sim_data
    merged = scores_df.merge(account_truth[["account_id", "role"]], on="account_id")

    high_s_mules = merged[(merged["role"] == "mule") & (merged["S"] > 0.5)]
    for _, row in high_s_mules.iterrows():
        assert len(row["reasons_for"]) >= 1, (
            f"Mule {row['account_id']} with S={row['S']} has empty reasons_for"
        )


def test_mule_score_function(sim_data):
    """mule_score returns the same S as scores_df for a sample account and raises KeyError for absent."""
    _, _, _, scores_df, _ = sim_data
    sample_aid = scores_df.iloc[0]["account_id"]
    res = mule_score(sample_aid, scores_df)

    assert res["S"] == scores_df.iloc[0]["S"]
    assert res["B"] == scores_df.iloc[0]["B"]
    assert res["T"] == scores_df.iloc[0]["T"]
    assert res["H"] == scores_df.iloc[0]["H"]
    assert res["reasons_for"] == scores_df.iloc[0]["reasons_for"]
    assert res["reasons_against"] == scores_df.iloc[0]["reasons_against"]

    with pytest.raises(KeyError):
        mule_score("NON_EXISTENT_ACC", scores_df)


def test_scam_inflow_share_by_role(sim_data):
    """Mean scam_inflow_share for role 'normal' is below 0.05, and above 0.5 for mules."""
    _, _, account_truth, _, features_df = sim_data
    merged = features_df.merge(account_truth[["account_id", "role"]], on="account_id")

    mean_normal_scam_inflow = merged[merged["role"] == "normal"]["scam_inflow_share"].mean()
    mean_mule_scam_inflow = merged[merged["role"] == "mule"]["scam_inflow_share"].mean()

    assert mean_normal_scam_inflow < 0.05, f"Normal scam_inflow_share too high: {mean_normal_scam_inflow:.4f}"
    assert mean_mule_scam_inflow > 0.50, f"Mule scam_inflow_share too low: {mean_mule_scam_inflow:.4f}"


def test_as_of_consistency(sim_data):
    """
    as_of=None equals as_of=43200 for features/scores (within 1e-9);
    with as_of=5000, results equal those from txns[time <= 5000] with as_of=5000.
    """
    accounts, txns, _, _, _ = sim_data

    # as_of=None vs as_of=43200
    f_none = build_features(accounts, txns, as_of=None)
    f_43200 = build_features(accounts, txns, as_of=43200)
    assert np.allclose(f_none.values, f_43200.values, atol=1e-9)

    s_none = score_all(accounts, txns, seed=42, as_of=None)
    s_43200 = score_all(accounts, txns, seed=42, as_of=43200)
    assert np.allclose(s_none["S"].values, s_43200["S"].values, atol=1e-9)

    # with as_of=5000 equals txns[time <= 5000] with as_of=5000
    txns_5000 = txns[txns["time"] <= 5000]

    f_asof_5000 = build_features(accounts, txns, as_of=5000)
    f_filt_5000 = build_features(accounts, txns_5000, as_of=5000)
    assert np.allclose(f_asof_5000.values, f_filt_5000.values, atol=1e-9)

    s_asof_5000 = score_all(accounts, txns, seed=42, as_of=5000)
    s_filt_5000 = score_all(accounts, txns_5000, seed=42, as_of=5000)
    assert np.allclose(s_asof_5000["S"].values, s_filt_5000["S"].values, atol=1e-9)

