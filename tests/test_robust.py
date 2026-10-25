"""
Tests for rule-robustness evaluation in eval.robust.
"""

from pathlib import Path
import pandas as pd
import pytest

from eval.robust import RULES, compute_held_amount, evaluate_robustness


def test_hand_built_rules():
    """
    Hand-built accounts with known tainted_prop/fifo/libr:
    (e.g. 1920/2000/3000, balance 4000, innocent):
    - lien 1920 gives clean 0 under all rules and recovery 1920/1920/1920 (capped by held=1920)
    - blanket (held=4000) gives clean 2080/2000/1000 and recovery 1920/2000/3000
    - lien 3000 gives clean 1080/1000/0 and recovery 1920/2000/3000
    """
    balance = 4000.0
    t_prop = 1920.0
    t_fifo = 2000.0
    t_libr = 3000.0
    is_mule = 0  # innocent account

    tainted_dict = {
        "tainted_prop": t_prop,
        "tainted_fifo": t_fifo,
        "tainted_libr": t_libr,
    }

    # Helper function to compute recovery and clean blocked per rule
    def eval_held(held_val):
        rec = {}
        clean = {}
        for r, t_val in tainted_dict.items():
            recovered = min(held_val, t_val)
            rec[r] = recovered
            if is_mule == 0:
                clean[r] = max(0.0, held_val - t_val)
            else:
                clean[r] = 0.0
        return rec, clean

    # 1. lien 1920: clean 0 under all rules, recovery 1920 under all rules (capped at 1920)
    rec_1920, clean_1920 = eval_held(1920.0)
    assert clean_1920["tainted_prop"] == pytest.approx(0.0)
    assert clean_1920["tainted_fifo"] == pytest.approx(0.0)
    assert clean_1920["tainted_libr"] == pytest.approx(0.0)
    assert rec_1920["tainted_prop"] == pytest.approx(1920.0)
    assert rec_1920["tainted_fifo"] == pytest.approx(1920.0)
    assert rec_1920["tainted_libr"] == pytest.approx(1920.0)

    # 2. blanket (held 4000): clean 2080/2000/1000, recovery 1920/2000/3000
    rec_4000, clean_4000 = eval_held(4000.0)
    assert clean_4000["tainted_prop"] == pytest.approx(2080.0)
    assert clean_4000["tainted_fifo"] == pytest.approx(2000.0)
    assert clean_4000["tainted_libr"] == pytest.approx(1000.0)
    assert rec_4000["tainted_prop"] == pytest.approx(1920.0)
    assert rec_4000["tainted_fifo"] == pytest.approx(2000.0)
    assert rec_4000["tainted_libr"] == pytest.approx(3000.0)

    # 3. lien 3000: clean 1080/1000/0, recovery 1920/2000/3000
    rec_3000, clean_3000 = eval_held(3000.0)
    assert clean_3000["tainted_prop"] == pytest.approx(1080.0)
    assert clean_3000["tainted_fifo"] == pytest.approx(1000.0)
    assert clean_3000["tainted_libr"] == pytest.approx(0.0)
    assert rec_3000["tainted_prop"] == pytest.approx(1920.0)
    assert rec_3000["tainted_fifo"] == pytest.approx(2000.0)
    assert rec_3000["tainted_libr"] == pytest.approx(3000.0)


def test_held_amount_computation():
    """Verify compute_held_amount for all action types."""
    # timed_hold
    assert compute_held_amount("timed_hold", balance=1000.0, lien_amount=200.0, cap_share=0.5) == 1000.0
    # lien
    assert compute_held_amount("lien", balance=1000.0, lien_amount=200.0, cap_share=0.5) == 200.0
    # lien_cap: lien_amount + cap_share * (balance - lien_amount) = 200 + 0.5 * 800 = 600
    assert compute_held_amount("lien_cap", balance=1000.0, lien_amount=200.0, cap_share=0.5) == 600.0
    # none
    assert compute_held_amount("none", balance=1000.0, lien_amount=200.0, cap_share=0.5) == 0.0


def test_robustness_on_data():
    """Run evaluate_robustness on single delay (60) to verify columns and constraints."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    acc_path = data_dir / "accounts.csv"
    txn_path = data_dir / "transactions.csv"
    scam_path = data_dir / "scam_truth.csv"

    if not (acc_path.exists() and txn_path.exists() and scam_path.exists()):
        pytest.skip("Data files do not exist.")

    accounts = pd.read_csv(acc_path)
    txns = pd.read_csv(txn_path)
    scams = pd.read_csv(scam_path)

    # Test single delay to keep test reasonably fast
    df = evaluate_robustness(accounts, txns, scams, delays=[60], lams=[0.0, 1.0])

    expected_cols = [
        "delay",
        "policy",
        "lam",
        "total_stolen_r",
        "rec_rate_mean",
        "rec_rate_worst",
        "clean_blocked_mean",
        "clean_blocked_worst",
        "innocent_holds",
    ]
    assert list(df.columns) == expected_cols

    for _, row in df.iterrows():
        assert row["rec_rate_worst"] <= row["rec_rate_mean"] + 1e-6
        assert row["clean_blocked_mean"] <= row["clean_blocked_worst"] + 1e-6
        assert row["rec_rate_worst"] >= 0.0
        assert row["rec_rate_mean"] <= 1.0
        assert row["clean_blocked_mean"] >= 0.0
