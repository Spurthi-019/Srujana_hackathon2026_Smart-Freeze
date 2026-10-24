import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from engine.features import FEATURE_GROUPS, build_features
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

    features_df = build_features(accounts, txns)
    all_features = list(features_df.columns)

    acc_target = accounts.set_index("account_id").loc[features_df.index]
    truth_target = account_truth.set_index("account_id").loc[features_df.index]
    y = acc_target["is_mule"].astype(int).values

    # 1. Ablation AUC Table
    feature_sets = {
        "all features": all_features,
        "B only": FEATURE_GROUPS["B"],
        "H only": FEATURE_GROUPS["H"],
        "T only": FEATURE_GROUPS["T"],
        "B+H (no T)": FEATURE_GROUPS["B"] + FEATURE_GROUPS["H"],
        "B+T": FEATURE_GROUPS["B"] + FEATURE_GROUPS["T"],
        "H+T": FEATURE_GROUPS["H"] + FEATURE_GROUPS["T"],
    }

    print("=" * 60)
    print("1. Out-of-fold ROC AUC for Feature Sets")
    print("=" * 60)
    print(f"{'Feature Set':<20} | {'Features Count':<16} | {'OOF ROC AUC'}")
    print("-" * 60)

    oof_preds_dict = {}
    for name, cols in feature_sets.items():
        X_sub = features_df[cols].values
        oof = compute_oof_predictions(X_sub, y, seed=42)
        oof_preds_dict[name] = oof
        auc = roc_auc_score(y, oof)
        print(f"{name:<20} | {len(cols):<16} | {auc:.4f}")

    # 2. Using B+H model (no T features)
    oof_bh = oof_preds_dict["B+H (no T)"]
    bh_df = pd.DataFrame({
        "account_id": features_df.index,
        "S": np.round(oof_bh, 4),
        "role": truth_target["role"].values,
        "type": acc_target["type"].values,
        "age_days": acc_target["age_days"].values,
        "is_mule": y,
    })

    print("\n" + "=" * 60)
    print("2. B+H Model (No Trail features) Out-of-Fold S")
    print("=" * 60)

    # Hard mules (age > 700)
    hard_mules = bh_df[(bh_df["is_mule"] == 1) & (bh_df["age_days"] > 700)]
    print("\nHard mules (age_days > 700):")
    for _, r in hard_mules.iterrows():
        print(f"  {r['account_id']} (age {r['age_days']}d): S = {r['S']:.4f}")

    # Every aggregator
    aggs = bh_df[bh_df["type"] == "aggregator"]
    print("\nAggregators:")
    for _, r in aggs.iterrows():
        print(f"  {r['account_id']} ({r['role']}): S = {r['S']:.4f}")

    # The 3 look-alikes
    lookalikes = bh_df[bh_df["role"].str.startswith("lookalike")]
    print("\nLook-alikes:")
    for _, r in lookalikes.iterrows():
        print(f"  {r['account_id']} ({r['role']}): S = {r['S']:.4f}")

    # Role averages under B+H
    mean_s_bystander = bh_df[bh_df["role"] == "bystander"]["S"].mean()
    mean_s_mule = bh_df[bh_df["role"] == "mule"]["S"].mean()
    mean_s_normal = bh_df[bh_df["role"] == "normal"]["S"].mean()
    print("\nRole Means (B+H):")
    print(f"  Mean S of bystanders : {mean_s_bystander:.4f}")
    print(f"  Mean S of mules      : {mean_s_mule:.4f}")
    print(f"  Mean S of normals    : {mean_s_normal:.4f}")

    # Lowest mule S
    lowest_mule_s = bh_df[bh_df["is_mule"] == 1]["S"].min()
    non_mule_above_lowest = (bh_df[bh_df["is_mule"] == 0]["S"] > lowest_mule_s).sum()
    print(f"\nLowest mule S in B+H model: {lowest_mule_s:.4f}")
    print(f"Number of non-mule accounts with S > lowest mule S: {non_mule_above_lowest}")

    # 3. Mean value of each of the 11 features for groups
    # Groups: mule, hard mule (age_days > 700), normal, aggregator, lookalike_busy, bystander
    feat_with_meta = features_df.copy()
    feat_with_meta["role"] = truth_target["role"].values
    feat_with_meta["type"] = acc_target["type"].values
    feat_with_meta["age_days"] = acc_target["age_days"].values

    groups = {
        "mule": feat_with_meta[feat_with_meta["role"] == "mule"],
        "hard mule": feat_with_meta[(feat_with_meta["role"] == "mule") & (feat_with_meta["age_days"] > 700)],
        "normal": feat_with_meta[feat_with_meta["role"] == "normal"],
        "aggregator": feat_with_meta[feat_with_meta["type"] == "aggregator"],
        "lookalike_busy": feat_with_meta[feat_with_meta["role"] == "lookalike_busy"],
        "bystander": feat_with_meta[feat_with_meta["role"] == "bystander"],
    }

    mean_table_data = {}
    for g_name, g_df in groups.items():
        mean_table_data[g_name] = g_df[all_features].mean()

    mean_df = pd.DataFrame(mean_table_data)
    print("\n" + "=" * 105)
    print("3. Mean Values of 11 Features Across Key Groups")
    print("=" * 105)
    print(mean_df.round(4).to_string())

    # 4. In full model, print 10 non-mule accounts with highest S
    oof_full = oof_preds_dict["all features"]
    full_df = pd.DataFrame({
        "account_id": features_df.index,
        "role": truth_target["role"].values,
        "is_mule": y,
        "S": np.round(oof_full, 4),
    })

    top10_non_mules = full_df[full_df["is_mule"] == 0].sort_values(by="S", ascending=False).head(10)

    print("\n" + "=" * 60)
    print("4. Top 10 Non-Mule Accounts with Highest S (Full Model)")
    print("=" * 60)
    print(top10_non_mules[["account_id", "role", "S"]].to_string(index=False))


if __name__ == "__main__":
    main()
