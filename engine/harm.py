"""
Harm model for Smart Freeze.

Quantifies the harm to an account if it is wrongfully frozen or restricted.
Assumptions and weights are tunable constants.
"""

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd

# Assumptions, tunable
FLOAT_NEED_BY_TYPE = {
    "merchant": 1.0,
    "aggregator": 0.8,
    "gig": 0.6,
    "salaried": 0.3,
}
DEFAULT_FLOAT_NEED = 0.5  # mule, victim, exit, or any other type

WEIGHT_FLOAT_NEED = 0.4
WEIGHT_SALARY_DEPENDENCE = 0.3
WEIGHT_THIN_COVER = 0.3


def harm_all(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    as_of: Optional[float] = None,
) -> pd.DataFrame:
    """Compute harm scores and components for all accounts.

    Args:
        accounts: DataFrame containing account_id, type, opening_balance, etc.
        txns: DataFrame containing txn_id, time, src, dst, amount, scam_id.
        as_of: Optional cutoff time in minutes. If provided, uses txns with time <= as_of.

    Returns:
        DataFrame indexed by account_id with columns:
        [harm_score, salary_dependence, float_need, thin_cover, cover_days]
    """
    if as_of is not None:
        valid_txns = txns[txns["time"] <= as_of]
        window_days = max(as_of, 1440.0) / 1440.0
    else:
        valid_txns = txns
        window_days = 30.0

    acc_df = accounts.copy()
    acc_ids = acc_df["account_id"]

    # Vectorised net balance and inflow/outflow computation
    if len(valid_txns) > 0:
        inflows_total = valid_txns.groupby("dst")["amount"].sum()
        outflows_total = valid_txns.groupby("src")["amount"].sum()
        largest_inflow = valid_txns.groupby("dst")["amount"].max()
    else:
        inflows_total = pd.Series(0.0, index=acc_ids)
        outflows_total = pd.Series(0.0, index=acc_ids)
        largest_inflow = pd.Series(0.0, index=acc_ids)

    # Align with all accounts
    tot_in = acc_ids.map(inflows_total).fillna(0.0).astype(float)
    tot_out = acc_ids.map(outflows_total).fillna(0.0).astype(float)
    max_in = acc_ids.map(largest_inflow).fillna(0.0).astype(float)

    opening = acc_df["opening_balance"].astype(float).values
    balance = opening + tot_in.values - tot_out.values

    # 1. salary_dependence: only for type "salaried": (largest single inflow) / (total inflow), 0 if no inflow
    is_salaried = (acc_df["type"] == "salaried").values
    sal_dep = np.zeros(len(acc_df), dtype=float)
    salaried_inflow = tot_in.values[is_salaried]
    salaried_max = max_in.values[is_salaried]
    with np.errstate(divide="ignore", invalid="ignore"):
        computed_sal_dep = np.where(salaried_inflow > 0, salaried_max / salaried_inflow, 0.0)
    sal_dep[is_salaried] = computed_sal_dep

    # 2. float_need from account type (NEVER read is_mule)
    float_need = acc_df["type"].map(FLOAT_NEED_BY_TYPE).fillna(DEFAULT_FLOAT_NEED).astype(float).values

    # 3. cover_days = balance / (total sent / window_days + 1)
    # thin_cover = clip(1 - cover_days / 30, 0, 1)
    daily_burn = tot_out.values / float(window_days)
    cover_days = balance / (daily_burn + 1.0)
    thin_cover = np.clip(1.0 - cover_days / 30.0, 0.0, 1.0)

    # 4. harm_score = 0.4*float_need + 0.3*salary_dependence + 0.3*thin_cover
    harm_score = (
        WEIGHT_FLOAT_NEED * float_need
        + WEIGHT_SALARY_DEPENDENCE * sal_dep
        + WEIGHT_THIN_COVER * thin_cover
    )

    result_df = pd.DataFrame(
        {
            "harm_score": harm_score,
            "salary_dependence": sal_dep,
            "float_need": float_need,
            "thin_cover": thin_cover,
            "cover_days": cover_days,
        },
        index=acc_df["account_id"],
    )
    return result_df


def innocent_blocked(
    balance: float,
    tainted_min: float,
    tainted_max: float,
    held: float,
) -> Dict[str, float]:
    """Calculate the range of clean rupees blocked if `held` rupees are held.

    Args:
        balance: Account total balance.
        tainted_min: Minimum estimated tainted money in account.
        tainted_max: Maximum estimated tainted money in account.
        held: Amount of rupees frozen / placed on hold.

    Returns:
        dict with "low" and "high" clean rupees blocked.
    """
    clipped_held = float(np.clip(held, 0.0, balance))
    return {
        "low": float(max(0.0, clipped_held - tainted_max)),
        "high": float(max(0.0, clipped_held - tainted_min)),
    }
