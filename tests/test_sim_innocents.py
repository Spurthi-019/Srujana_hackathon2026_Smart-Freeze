from pathlib import Path
import pandas as pd
import pytest
from sim.build import build_all
from sim.innocents import add_innocents
from sim.normal import generate_normal
from sim.scams import add_scams


def test_reproducibility():
    """Same seed gives identical output."""
    accs1, txns1, scam1, truth1 = build_all(seed=42)
    accs2, txns2, scam2, truth2 = build_all(seed=42)

    pd.testing.assert_frame_equal(accs1, accs2)
    pd.testing.assert_frame_equal(txns1, txns2)
    pd.testing.assert_frame_equal(scam1, scam2)
    pd.testing.assert_frame_equal(truth1, truth2)


def test_contract_columns():
    """accounts.csv has exactly the contract columns."""
    accs, txns, scam_truth, account_truth = build_all(seed=42)
    expected_cols = [
        "account_id",
        "type",
        "age_days",
        "avg_monthly_inflow",
        "opening_balance",
        "is_mule",
    ]
    assert list(accs.columns) == expected_cols

    # Check saved CSV directly
    data_dir = Path(__file__).resolve().parent.parent / "data"
    csv_df = pd.read_csv(data_dir / "accounts.csv")
    assert list(csv_df.columns) == expected_cols


def test_bystander_properties():
    """
    Every bystander has opening_balance above its true_tainted_received
    and at least 3 outgoing txns after receiving it.
    At least 24 bystanders, and every scam with start_time before day 25
    has at least one bystander where an eligible normal account exists.
    """
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    bystanders = account_truth[account_truth["role"] == "bystander"]
    assert len(bystanders) >= 24

    # Every scam with start_time before day 25 gets at least one bystander
    eligible_scams = scam_truth[scam_truth["start_time"] < 25 * 1440]["scam_id"].tolist()
    bystander_scams = set()
    for s_str in bystanders["scam_ids"]:
        for s in s_str.split(","):
            if s:
                bystander_scams.add(s)
    for sid in eligible_scams:
        assert sid in bystander_scams, f"Eligible scam {sid} has no bystander associated"

    acc_map = dict(zip(accs["account_id"], accs["opening_balance"]))

    # Map receipt times for bystanders
    mule_accs = set(accs[accs["is_mule"] == 1]["account_id"])

    for _, b_row in bystanders.iterrows():
        bid = b_row["account_id"]
        tainted = b_row["true_tainted_received"]
        op_bal = acc_map[bid]

        assert op_bal > tainted, (
            f"Bystander {bid} opening_balance ({op_bal}) not above tainted ({tainted})"
        )

        # Find earliest receipt time from a mule with scam_id
        receipt_txns = txns[
            (txns["dst"] == bid)
            & (txns["src"].isin(mule_accs))
            & (txns["scam_id"] != "")
        ]
        assert not receipt_txns.empty, (
            f"Bystander {bid} has no recorded scam transfer from a mule"
        )
        receipt_time = receipt_txns["time"].min()

        # Check outgoing txns after receipt time
        outgoing_after = txns[
            (txns["src"] == bid) & (txns["time"] >= receipt_time)
        ]
        assert len(outgoing_after) >= 3, (
            f"Bystander {bid} has fewer than 3 outgoing transactions after receiving tainted payment"
        )


def test_lookalike_and_aggregator_roles():
    """4 per look-alike role (16 total), is_mule 0, no scam_id on look-alike txns, one aggregator_tainted."""
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    roles = account_truth["role"].value_counts()
    assert "lookalike_busy" in roles
    assert "lookalike_festival" in roles
    assert "lookalike_new" in roles
    assert "lookalike_payout" in roles

    # 4 per look-alike role (16 total)
    assert roles.get("lookalike_busy") == 4
    assert roles.get("lookalike_festival") == 4
    assert roles.get("lookalike_new") == 4
    assert roles.get("lookalike_payout") == 4

    lookalike_roles = ["lookalike_busy", "lookalike_festival", "lookalike_new", "lookalike_payout"]
    lookalike_ids = set(account_truth[account_truth["role"].isin(lookalike_roles)]["account_id"])
    assert len(lookalike_ids) == 16

    # Look-alikes must have is_mule == 0
    merged = accs.merge(account_truth[["account_id", "role"]], on="account_id")
    lookalike_accs = merged[merged["role"].isin(lookalike_roles)]
    assert (lookalike_accs["is_mule"] == 0).all()

    # No scam_id on look-alike transactions (neither as src nor dst should have a scam_id)
    lookalike_txns = txns[txns["src"].isin(lookalike_ids) | txns["dst"].isin(lookalike_ids)]
    assert (lookalike_txns["scam_id"] == "").all()

    # Exactly one aggregator_tainted
    assert roles.get("aggregator_tainted") == 1


def test_is_mule_labeling_only_for_mules():
    """is_mule equals 1 only for mules."""
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    merged = accs.merge(account_truth, on="account_id")
    mules = merged[merged["is_mule"] == 1]
    assert (mules["role"] == "mule").all()

    non_mules = merged[merged["is_mule"] == 0]
    assert (non_mules["role"] != "mule").all()


def test_no_negative_balance_final_replay():
    """No negative balance anywhere in the final timeline after replay."""
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    balances = dict(zip(accs["account_id"], accs["opening_balance"].astype(float)))

    # Replay sorted by (time, txn_id)
    sorted_txns = txns.sort_values(by=["time", "txn_id"]).reset_index(drop=True)
    for _, row in sorted_txns.iterrows():
        src = row["src"]
        dst = row["dst"]
        amt = float(row["amount"])

        assert amt > 0
        assert balances[src] >= amt - 1e-6, (
            f"Account {src} went negative: balance={balances[src]}, txn={amt}"
        )

        balances[src] -= amt
        balances[dst] += amt

        assert balances[src] >= -1e-6
