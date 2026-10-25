"""
Mule scoring engine for Smart Freeze.
Calculates investigation priority score S = f(B, T, H) using Logistic Regression.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from engine.features import FEATURE_GROUPS, READABLE, build_features

# Module-level model fitted on all data for new accounts
MODEL = None
SCALER = None


def score_all(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    seed: int = 42,
    as_of: float | None = None,
) -> pd.DataFrame:
    """
    Computes investigation priority S and group contributions B, T, H.
    Uses out-of-fold predictions from StratifiedKFold cross-validation.
    Returns DataFrame with columns:
    [account_id, S, B, T, H, reasons_for, reasons_against, is_mule]
    """
    global MODEL, SCALER

    # Filter txns to time <= as_of first
    if as_of is not None:
        txns = txns[txns["time"] <= as_of]

    # 1. Build features
    features_df = build_features(accounts, txns, as_of=as_of)
    feature_names = features_df.columns.tolist()

    # Align with target label is_mule
    acc_target = accounts.set_index("account_id").loc[features_df.index]
    y = acc_target["is_mule"].astype(int).values
    X_raw = features_df.values

    # Placeholders for results
    n_samples = len(features_df)
    oof_S = np.zeros(n_samples)
    oof_B = np.zeros(n_samples)
    oof_T = np.zeros(n_samples)
    oof_H = np.zeros(n_samples)
    oof_reasons_for = [[] for _ in range(n_samples)]
    oof_reasons_against = [[] for _ in range(n_samples)]

    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=seed)

    # Cross-validation
    for train_idx, val_idx in skf.split(X_raw, y):
        scaler_fold = StandardScaler()
        X_train_std = scaler_fold.fit_transform(X_raw[train_idx])
        X_val_std = scaler_fold.transform(X_raw[val_idx])

        clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
        clf.fit(X_train_std, y[train_idx])

        # Predicted probabilities: S = investigation priority in [0, 1]
        probs = clf.predict_proba(X_val_std)[:, 1]
        oof_S[val_idx] = probs

        # Coefficients
        coef = clf.coef_[0]  # shape (n_features,)

        # Contributions for each sample in validation fold
        # contrib_matrix shape: (len(val_idx), n_features)
        contribs = X_val_std * coef

        for i_local, i_global in enumerate(val_idx):
            row_contribs = contribs[i_local]
            # Group contributions
            b_val = sum(row_contribs[feature_names.index(f)] for f in FEATURE_GROUPS["B"])
            t_val = sum(row_contribs[feature_names.index(f)] for f in FEATURE_GROUPS["T"])
            h_val = sum(row_contribs[feature_names.index(f)] for f in FEATURE_GROUPS["H"])

            oof_B[i_global] = round(float(b_val), 3)
            oof_T[i_global] = round(float(t_val), 3)
            oof_H[i_global] = round(float(h_val), 3)

            # reasons_for / reasons_against:
            # top 3 features by positive / negative contribution, mapped through READABLE;
            # only include features whose contribution has the right sign and absolute value above 0.1
            pos_contribs = []
            neg_contribs = []

            for f_name, c_val in zip(feature_names, row_contribs):
                if c_val > 0.1:
                    phrase = READABLE[f_name][0]
                    pos_contribs.append((c_val, phrase))
                elif c_val < -0.1:
                    phrase = READABLE[f_name][1]
                    neg_contribs.append((abs(c_val), phrase))

            # Sort descending by contribution magnitude
            pos_contribs.sort(key=lambda x: x[0], reverse=True)
            neg_contribs.sort(key=lambda x: x[0], reverse=True)

            oof_reasons_for[i_global] = [p for _, p in pos_contribs[:3]]
            oof_reasons_against[i_global] = [p for _, p in neg_contribs[:3]]

    # Fit final model on all data for future inference
    SCALER = StandardScaler()
    X_all_std = SCALER.fit_transform(X_raw)
    MODEL = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
    MODEL.fit(X_all_std, y)

    scores_df = pd.DataFrame({
        "account_id": features_df.index,
        "S": np.round(oof_S, 4),
        "B": oof_B,
        "T": oof_T,
        "H": oof_H,
        "reasons_for": oof_reasons_for,
        "reasons_against": oof_reasons_against,
        "is_mule": y,
    })

    return scores_df


def mule_score(account_id: str, scores_df: pd.DataFrame) -> dict:
    """
    Extracts scored metrics for an account.
    Raises KeyError if account is not scored.
    """
    matched = scores_df[scores_df["account_id"] == account_id]
    if matched.empty:
        raise KeyError(f"Account {account_id} not found in scores_df")

    row = matched.iloc[0]
    return {
        "S": float(row["S"]),
        "B": float(row["B"]),
        "T": float(row["T"]),
        "H": float(row["H"]),
        "reasons_for": list(row["reasons_for"]),
        "reasons_against": list(row["reasons_against"]),
    }
