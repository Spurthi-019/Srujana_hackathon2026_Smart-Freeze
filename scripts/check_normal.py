import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sim.normal import generate_normal


def main():
    print("=" * 60)
    print("Running check_normal.py")
    print("=" * 60)

    # a. Deterministic check
    accs1, txns1 = generate_normal(seed=42)
    accs2, txns2 = generate_normal(seed=42)
    det_accs = accs1.equals(accs2)
    det_txns = txns1.equals(txns2)
    is_deterministic = det_accs and det_txns

    accounts_df = accs1
    txns_df = txns1

    # b. Account count between 450 and 550, print counts by type, >= 3 aggregators
    n_accounts = len(accounts_df)
    type_counts = accounts_df["type"].value_counts().to_dict()
    print("\nAccount counts by type:")
    for t, c in type_counts.items():
        print(f"  {t}: {c}")
    n_aggregators = type_counts.get("aggregator", 0)
    acc_count_ok = 450 <= n_accounts <= 550 and n_aggregators >= 3

    # c. Txn time range within 0..43200, print count (expect ~5,000-50,000)
    n_txns = len(txns_df)
    min_time = txns_df["time"].min() if n_txns > 0 else -1
    max_time = txns_df["time"].max() if n_txns > 0 else -1
    print(f"\nTotal transactions: {n_txns}")
    print(f"Time range: {min_time} to {max_time} (minutes)")
    time_range_ok = (min_time >= 0) and (max_time <= 43200) and (5000 <= n_txns <= 50000)

    # d. Unknown account_ids, self-transfers, non-positive amounts, duplicate txn_ids
    valid_acc_set = set(accounts_df["account_id"])
    unknown_src = (~txns_df["src"].isin(valid_acc_set)).sum()
    unknown_dst = (~txns_df["dst"].isin(valid_acc_set)).sum()
    self_transfers = (txns_df["src"] == txns_df["dst"]).sum()
    non_positive_amounts = (txns_df["amount"] <= 0).sum()
    duplicate_txns = txns_df["txn_id"].duplicated().sum()
    d_clean = (unknown_src == 0 and unknown_dst == 0 and self_transfers == 0 
               and non_positive_amounts == 0 and duplicate_txns == 0)

    # e. Replay txns sorted by (time, txn_id) starting from opening_balance
    sorted_txns = txns_df.sort_values(by=["time", "txn_id"]).reset_index(drop=True)
    balances = dict(zip(accounts_df["account_id"], accounts_df["opening_balance"].astype(float)))
    negative_balance_events = 0
    for _, row in sorted_txns.iterrows():
        src = row["src"]
        dst = row["dst"]
        amt = float(row["amount"])
        if balances[src] - amt < -1e-6:
            negative_balance_events += 1
        balances[src] -= amt
        balances[dst] += amt
    e_ok = (negative_balance_events == 0)

    # f. For each aggregator: pass-through ratio = total sent / total received (expect ~0.8-1.0)
    agg_ids = accounts_df[accounts_df["type"] == "aggregator"]["account_id"].tolist()
    agg_ratios = {}
    f_ok = True
    for aid in agg_ids:
        sent = txns_df[txns_df["src"] == aid]["amount"].sum()
        recv = txns_df[txns_df["dst"] == aid]["amount"].sum()
        ratio = (sent / recv) if recv > 0 else 0.0
        agg_ratios[aid] = ratio
        if not (0.8 <= ratio <= 1.0):
            f_ok = False
    print("\nAggregator pass-through ratios (sent / received):")
    for aid, r in agg_ratios.items():
        print(f"  {aid}: {r:.4f}")

    # g. Salaried accounts: median of each account's largest inflow vs median avg_monthly_inflow
    salaried_ids = accounts_df[accounts_df["type"] == "salaried"]["account_id"].tolist()
    salaried_txns = txns_df[txns_df["dst"].isin(salaried_ids)]
    max_inflow_per_acc = salaried_txns.groupby("dst")["amount"].max()
    median_max_inflow = float(max_inflow_per_acc.median()) if len(max_inflow_per_acc) > 0 else 0.0
    median_avg_inflow = float(accounts_df[accounts_df["type"] == "salaried"]["avg_monthly_inflow"].median())
    ratio_inflow = (median_max_inflow / median_avg_inflow) if median_avg_inflow > 0 else 0.0
    g_ok = 0.1 <= ratio_inflow <= 10.0
    print(f"\nSalaried Inflow comparison: median largest inflow = {median_max_inflow:.2f}, median avg_monthly_inflow = {median_avg_inflow:.2f}, ratio = {ratio_inflow:.4f}")

    # h. Amount distribution: print describe(); check max/median ratio is above 10
    print("\nAmount Distribution describe():")
    print(txns_df["amount"].describe())
    amt_median = float(txns_df["amount"].median())
    amt_max = float(txns_df["amount"].max())
    max_to_median_ratio = (amt_max / amt_median) if amt_median > 0 else 0.0
    h_ok = max_to_median_ratio > 10.0
    print(f"Max/Median Ratio: {max_to_median_ratio:.2f}")

    # Results Table
    results = [
        ("a. Deterministic", f"Identical: {is_deterministic}", "Two calls match exactly", "PASS" if is_deterministic else "FAIL"),
        ("b. Account Count & Aggregators", f"{n_accounts} total, {n_aggregators} aggregators", "450-550 total, >=3 aggregators", "PASS" if acc_count_ok else "FAIL"),
        ("c. Txn Time Range & Count", f"{n_txns} txns, range [{min_time}, {max_time}]", "0..43200, 5000-50000 txns", "PASS" if time_range_ok else "FAIL"),
        ("d. Referencing & Integrity", f"unknown={unknown_src+unknown_dst}, self={self_transfers}, nonpos={non_positive_amounts}, dups={duplicate_txns}", "All 0", "PASS" if d_clean else "FAIL"),
        ("e. Non-negative Balance Replay", f"{negative_balance_events} negative events", "0 negative events", "PASS" if e_ok else "FAIL"),
        ("f. Aggregator Pass-through Ratio", f"Ratios: {', '.join(f'{k}:{v:.2f}' for k,v in agg_ratios.items())}", "Each within 0.8-1.0", "PASS" if f_ok else "FAIL"),
        ("g. Salaried Largest Inflow vs Avg", f"Median max={median_max_inflow:.0f}, Median avg={median_avg_inflow:.0f} (ratio={ratio_inflow:.2f})", "Within 10x (ratio 0.1-10.0)", "PASS" if g_ok else "FAIL"),
        ("h. Amount Distribution Right Tail", f"Max/Median={max_to_median_ratio:.2f} (max={amt_max:.1f}, med={amt_median:.1f})", "Max/Median > 10", "PASS" if h_ok else "FAIL")
    ]

    print("\n" + "=" * 90)
    print(f"{'Check':<35} | {'Value':<30} | {'Expected':<30} | {'Status'}")
    print("-" * 90)
    all_pass = True
    failing = []
    for name, val, exp, status in results:
        print(f"{name:<35} | {str(val)[:30]:<30} | {str(exp)[:30]:<30} | {status}")
        if status != "PASS":
            all_pass = False
            failing.append(name)
    print("=" * 90)

    if all_pass:
        print("\nVERDICT: READY")
    else:
        print(f"\nVERDICT: NOT READY: {', '.join(failing)}")


if __name__ == "__main__":
    main()
