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
    At least 6 bystanders.
    """
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    bystanders = account_truth[account_truth["role"] == "bystander"]
    assert len(bystanders) >= 6

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
    """Exactly 4 look-alike roles present; one aggregator_tainted."""
    accs, txns, scam_truth, account_truth = build_all(seed=42)

    roles = account_truth["role"].value_counts()
    assert "lookalike_busy" in roles
    assert "lookalike_festival" in roles
    assert "lookalike_new" in roles
    assert "lookalike_payout" in roles

    # Exactly 4 look-alike accounts present (1 per role)
    assert roles.get("lookalike_busy") == 1
    assert roles.get("lookalike_festival") == 1
    assert roles.get("lookalike_new") == 1
    assert roles.get("lookalike_payout") == 1

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
