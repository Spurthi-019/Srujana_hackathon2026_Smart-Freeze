import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from engine.features import FEATURE_GROUPS, build_features
from engine.score import score_all
from sim.build import build_all


def compute_oof_predictions(X_sub: np.ndarray, y: np.ndarray, seed: int = 42) -> np.ndarray:
    """Computes out-of-fold predicted probabilities using 4-fold StratifiedKFold."""
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=seed)
    oof_preds = np.zeros(len(y))

    for train_idx, val_idx in skf.split(X_sub, y):
        scaler = StandardScaler()
        X_train_std = scaler.fit_transform(X_sub[train_idx])
        X_val_std = scaler.transform(X_sub[val_idx])

        clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
        clf.fit(X_train_std, y[train_idx])
        oof_preds[val_idx] = clf.predict_proba(X_val_std)[:, 1]

    return oof_preds


def main():
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

    # Clean scam_id: treat NaN, float, and "" as blank
    txns_clean = txns.copy()
    txns_clean["scam_id"] = txns_clean["scam_id"].fillna("").astype(str).str.strip()

    # Full model scores and contributions via engine.score.score_all
    scores_df = score_all(accounts, txns, seed=42)
    # Merge with role from account_truth
    scores_df = scores_df.merge(account_truth[["account_id", "role"]], on="account_id", how="left")
    # Also get age_days from accounts
    scores_df = scores_df.merge(accounts[["account_id", "age_days"]], on="account_id", how="left")

    # B+H model
    features_df = build_features(accounts, txns)
    bh_cols = FEATURE_GROUPS["B"] + FEATURE_GROUPS["H"]
    X_bh = features_df[bh_cols].values

    acc_target = accounts.set_index("account_id").loc[features_df.index]
    y = acc_target["is_mule"].astype(int).values
    oof_bh = compute_oof_predictions(X_bh, y, seed=42)

    bh_series = pd.Series(np.round(oof_bh, 4), index=features_df.index, name="S_bh")
    scores_df = scores_df.merge(bh_series, left_on="account_id", right_index=True, how="left")

    # Precompute per-account transaction stats:
    # 1. Distinct scam_ids as src or dst (non-blank)
    # 2. Total amount received via txns with a real scam_id
    # 3. Distinct active days (floor(time / 1440))
    real_scam_txns = txns_clean[txns_clean["scam_id"] != ""]

    scam_ids_per_acc = {}
    total_scam_inflow_per_acc = {}
    active_days_per_acc = {}

    all_accounts = accounts["account_id"].unique()
    for aid in all_accounts:
        scam_ids_per_acc[aid] = set()
        total_scam_inflow_per_acc[aid] = 0.0
        active_days_per_acc[aid] = set()

    # Fill active days from all txns
    for _, row in txns_clean.iterrows():
        t = int(row["time"])
        day = min(29, t // 1440)
        src = row["src"]
        dst = row["dst"]
        if src in active_days_per_acc:
            active_days_per_acc[src].add(day)
        if dst in active_days_per_acc:
            active_days_per_acc[dst].add(day)

    # Fill scam stats
    for _, row in real_scam_txns.iterrows():
        sid = row["scam_id"]
        src = row["src"]
        dst = row["dst"]
        amt = float(row["amount"])
        if src in scam_ids_per_acc:
            scam_ids_per_acc[src].add(sid)
        if dst in scam_ids_per_acc:
            scam_ids_per_acc[dst].add(sid)
            total_scam_inflow_per_acc[dst] += amt

    # 1. For every mule (is_mule = 1) print one row:
    # account_id, age_days, number of distinct scam_ids it appears in (as src or dst),
    # total amount received via txns with a real scam_id, number of distinct active days,
    # S from the full model, S from the B+H-only model.
    print("=" * 80)
    print("1. MULE ACCOUNTS (is_mule = 1)")
    print("=" * 80)
    mules_df = scores_df[scores_df["is_mule"] == 1].copy()

    mule_rows = []
    zero_scam_mules = []
    for _, r in mules_df.iterrows():
        aid = r["account_id"]
        age = int(r["age_days"])
        n_scams = len(scam_ids_per_acc.get(aid, set()))
        if n_scams == 0:
            zero_scam_mules.append(aid)
        tot_scam_rcvd = total_scam_inflow_per_acc.get(aid, 0.0)
        n_active_days = len(active_days_per_acc.get(aid, set()))
        s_full = r["S"]
        s_bh = r["S_bh"]
        mule_rows.append({
            "account_id": aid,
            "age_days": age,
            "distinct_scams": n_scams,
            "scam_received_amt": tot_scam_rcvd,
            "active_days": n_active_days,
            "S_full": s_full,
            "S_bh": s_bh,
        })

    mules_summary_df = pd.DataFrame(mule_rows)
    print(mules_summary_df.to_string(index=False))

    # 2. List mules that appear in zero scams
    print("\n" + "=" * 80)
    print("2. MULES APPEARING IN ZERO SCAMS")
    print("=" * 80)
    if zero_scam_mules:
        for aid in zero_scam_mules:
            print(f"- {aid}")
    else:
        print("None (all mules appear in at least 1 scam)")

    # 3. For every account with role starting with "lookalike" or role "aggregator_tainted",
    # print: role, S (full model), S (B+H only), and the B, T, H contribution values from score_all.
    print("\n" + "=" * 80)
    print("3. LOOK-ALIKE & AGGREGATOR_TAINTED ACCOUNTS")
    print("=" * 80)
    target_roles_df = scores_df[
        scores_df["role"].str.startswith("lookalike") | (scores_df["role"] == "aggregator_tainted")
    ]
    lookalike_rows = []
    for _, r in target_roles_df.iterrows():
        lookalike_rows.append({
            "account_id": r["account_id"],
            "role": r["role"],
            "S_full": r["S"],
            "S_bh": r["S_bh"],
            "B": r["B"],
            "T": r["T"],
            "H": r["H"],
        })
    target_summary_df = pd.DataFrame(lookalike_rows)
    print(target_summary_df.to_string(index=False))

    # 4. Print the 10 non-mule accounts with the highest full-model S: account_id, role, S.
    print("\n" + "=" * 80)
    print("4. TOP 10 NON-MULE ACCOUNTS WITH HIGHEST S (FULL MODEL)")
    print("=" * 80)
    non_mules_df = scores_df[scores_df["is_mule"] == 0]
    top10_non_mules = non_mules_df.sort_values(by="S", ascending=False).head(10)
    print(top10_non_mules[["account_id", "role", "S"]].to_string(index=False))

    # 5. Print the median full-model S of non-mule accounts and how many non-mules have S above 0.5.
    print("\n" + "=" * 80)
    print("5. NON-MULE DISTRIBUTION SUMMARY (FULL MODEL)")
    print("=" * 80)
    median_non_mule_s = float(non_mules_df["S"].median())
    non_mule_above_half = int((non_mules_df["S"] > 0.5).sum())
    total_non_mules = len(non_mules_df)
    print(f"Median S (non-mules): {median_non_mule_s:.4f}")
    print(f"Non-mules with S > 0.5: {non_mule_above_half} / {total_non_mules} ({non_mule_above_half / total_non_mules * 100:.2f}%)")


if __name__ == "__main__":
    main()
