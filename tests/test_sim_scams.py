import pandas as pd
import pytest
from sim.normal import generate_normal
from sim.scams import add_scams


def test_reproducibility():
    """Same seed gives identical output."""
    accs, txns = generate_normal(seed=42)
    accs1, txns1, truth1 = add_scams(accs, txns, n_scams=14, seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    pd.testing.assert_frame_equal(accs1, accs2)
    pd.testing.assert_frame_equal(txns1, txns2)
    pd.testing.assert_frame_equal(truth1, truth2)


def test_shapes_and_exits():
    """All four shapes present and exactly 3 exit accounts."""
    accs, txns = generate_normal(seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    expected_shapes = {"layered_chain", "fan_out", "fan_in", "fan_out_gather"}
    assert set(truth2["shape"].unique()) == expected_shapes

    exits = accs2[accs2["type"] == "exit"]
    assert len(exits) == 3
    assert set(exits["account_id"]) == {"EXIT_ATM_1", "EXIT_JEWELLER_1", "EXIT_EXCH_1"}
    assert (exits["is_mule"] == 0).all()


def test_is_mule_labeling():
    """Mules have is_mule 1 and everyone else 0; exactly 16 mules."""
    accs, txns = generate_normal(seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    mules = accs2[accs2["is_mule"] == 1]
    assert len(mules) == 16
    assert (mules["type"] == "mule").all()

    non_mules = accs2[accs2["is_mule"] == 0]
    assert (non_mules["type"] != "mule").all()


def test_mule_properties():
    """At least 2 mules appear in 2 or more scams, and at least 4 mules have age_days > 700."""
    accs, txns = generate_normal(seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    mules = accs2[accs2["type"] == "mule"]
    hard_mules = mules[mules["age_days"] > 700]
    assert len(hard_mules) >= 4

    # Mule participation in scams
    all_mule_lists = [m.split(",") for m in truth2["mule_ids"]]
    flat_mules = [m for sublist in all_mule_lists for m in sublist]
    mule_counts = pd.Series(flat_mules).value_counts()
    multi_scam_mules = (mule_counts >= 2).sum()
    assert multi_scam_mules >= 2


def test_scam_accounting():
    """Every scam_id in truth_df; exit_total + remaining_in_mules <= total_stolen."""
    accs, txns = generate_normal(seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    assert len(truth2) == 14
    scam_ids_in_txns = set(txns2[txns2["scam_id"] != ""]["scam_id"])
    assert scam_ids_in_txns == set(truth2["scam_id"])

    for _, row in truth2.iterrows():
        stolen = row["total_stolen"]
        exit_tot = row["exit_total"]
        rem = row["remaining_in_mules"]
        assert exit_tot + rem <= stolen + 1e-2, (
            f"Accounting mismatch in {row['scam_id']}: exit ({exit_tot}) + rem ({rem}) > stolen ({stolen})"
        )


def test_no_negative_balance_replay():
    """No negative balance after merge when replayed in chronological order."""
    accs, txns = generate_normal(seed=42)
    accs2, txns2, truth2 = add_scams(accs, txns, n_scams=14, seed=42)

    balances = dict(zip(accs2["account_id"], accs2["opening_balance"].astype(float)))

    # Ensure txns2 is sorted by time
    times = txns2["time"].tolist()
    assert times == sorted(times)

    for _, row in txns2.iterrows():
        src = row["src"]
        dst = row["dst"]
        amt = float(row["amount"])

        assert amt > 0
        assert balances[src] >= amt - 1e-6, f"Account {src} went negative: {balances[src]} for txn {amt}"

        balances[src] -= amt
        balances[dst] += amt

        assert balances[src] >= -1e-6
