"""
Decision engine for Smart Freeze actions.

Evaluates trade-off between recovery of stolen funds and harm to clean accounts
using an optimization model over 4 actions: none, lien, lien_cap, timed_hold.
"""

from typing import Any, Dict, Mapping

CAP_SHARE = 0.5
HOLD_HOURS = 24
FUTURE_FACTOR = 1.0
HARM_BASE = 0.5
TIE_TOL = 1.0

# Action ranking from gentlest to most restrictive
ACTION_ORDER = ["none", "lien", "lien_cap", "timed_hold"]


def decide(row: Mapping[str, Any], lam: float) -> Dict[str, Any]:
    """
    Decide the smallest effective freeze/lien action for an account.

    Args:
        row: Mapping with keys: account_id, balance, tainted_min, tainted_max, S, harm_score.
             Optional key: recent_inflow (default 0).
        lam: Non-negative trade-off parameter lambda (trade recovery vs harm).

    Returns:
        dict containing:
            action: str in {'none', 'lien', 'lien_cap', 'timed_hold'}
            lien_amount: float
            cap_share: float
            hold_hours: int
            needs_human: bool
            expected_recovered: float
            expected_clean_blocked: float
            losses: Dict[str, float]
            note: str (one sentence: rupees, tracing range, S)
    """
    if lam < 0:
        raise ValueError(f"Lambda must be non-negative, got {lam}")

    required_keys = ["account_id", "balance", "tainted_min", "tainted_max", "S", "harm_score"]
    for k in required_keys:
        if k not in row:
            raise KeyError(f"Missing required key in row: {k}")

    account_id = row["account_id"]
    balance = float(row["balance"])
    tmin = float(row["tainted_min"])
    tmax = float(row["tainted_max"])
    S = float(row["S"])
    harm_score = float(row["harm_score"])
    recent_inflow = float(row.get("recent_inflow", 0.0))

    s = tmin + (tmax - tmin) * S
    f = S * recent_inflow * FUTURE_FACTOR
    clean = max(balance - s, 0.0)

    # Actions definition: (name, b, c, fut, lien_amt, cap_share_val, hold_hours_val, needs_human_val)
    action_specs = [
        ("none", 0.0, 0.0, 0.0, 0.0, 0.0, 0, False),
        ("lien", tmin, 0.0, 0.0, tmin, 0.0, 0, False),
        ("lien_cap", s, CAP_SHARE, CAP_SHARE, s, CAP_SHARE, 0, False),
        ("timed_hold", balance, 0.0, 1.0, balance, 0.0, HOLD_HOURS, True),
    ]

    losses = {}
    metrics = {}

    for name, b, c, fut, lien_amt, c_share, h_hrs, nh in action_specs:
        ex = max(0.0, b - s)
        sb = min(b, s)
        stolen_blocked = sb + c * (s - sb) + fut * f
        clean_blocked = ex + c * (clean - ex)
        loss = -stolen_blocked + lam * (1.0 - S) * (HARM_BASE + harm_score) * clean_blocked

        losses[name] = float(loss)
        metrics[name] = {
            "lien_amount": float(lien_amt),
            "cap_share": float(c_share),
            "hold_hours": int(h_hrs),
            "needs_human": bool(nh),
            "expected_recovered": float(stolen_blocked),
            "expected_clean_blocked": float(clean_blocked),
        }

    # Pick minimum loss; ties within TIE_TOL pick the gentler action
    min_loss = min(losses.values())
    chosen_action = "timed_hold"
    for act in ACTION_ORDER:
        if losses[act] <= min_loss + TIE_TOL:
            chosen_action = act
            break

    chosen_meta = metrics[chosen_action]

    # One sentence note: rupees, tracing range, S
    note = (
        f"Account {account_id} with balance Rs {balance:,.2f} has tracing tainted range "
        f"Rs {tmin:,.2f} to Rs {tmax:,.2f} and investigation priority S={S:.4f}."
    )

    return {
        "action": chosen_action,
        "lien_amount": chosen_meta["lien_amount"],
        "cap_share": chosen_meta["cap_share"],
        "hold_hours": chosen_meta["hold_hours"],
        "needs_human": chosen_meta["needs_human"],
        "expected_recovered": chosen_meta["expected_recovered"],
        "expected_clean_blocked": chosen_meta["expected_clean_blocked"],
        "losses": losses,
        "note": note,
    }


def decide_all(
    trace_df: Any,
    scores_df: Any,
    harm_df: Any,
    txns: Any,
    as_of: Any = None,
    lam: float = 1.0,
) -> Any:
    """
    Decide actions for all accounts in trace_df.

    Args:
        trace_df: DataFrame with account_id, balance, tainted_min, tainted_max (from engine.taint.trace).
        scores_df: DataFrame with account_id, S (from engine.score.score_all).
        harm_df: DataFrame indexed by account_id with harm_score (from engine.harm.harm_all).
        txns: DataFrame with time, dst, amount.
        as_of: Optional cutoff time in minutes. If provided, recent_inflow is computed
               as sum of amounts received by dst in (as_of - 120, as_of]. If None, recent_inflow is 0.
        lam: Trade-off parameter lambda, defaults to 1.0.

    Returns:
        DataFrame: one row per trace_df account_id with the decide() fields:
            [account_id, action, lien_amount, cap_share, hold_hours, needs_human,
             expected_recovered, expected_clean_blocked, losses, note]
    """
    import pandas as pd

    # Precompute recent_inflow per account
    recent_inflows = {}
    if as_of is not None and txns is not None and len(txns) > 0:
        window_start = as_of - 120
        recent_txns = txns[(txns["time"] > window_start) & (txns["time"] <= as_of)]
        if len(recent_txns) > 0:
            recent_inflows = recent_txns.groupby("dst")["amount"].sum().to_dict()

    # Precompute scores mapping (account_id -> S)
    scores_map = {}
    if scores_df is not None and "account_id" in scores_df.columns and "S" in scores_df.columns:
        scores_map = dict(zip(scores_df["account_id"], scores_df["S"]))

    # Precompute harm mapping (index or column -> harm_score)
    harm_map = {}
    if harm_df is not None:
        if "harm_score" in harm_df.columns:
            harm_map = harm_df["harm_score"].to_dict()

    results = []
    for _, t_row in trace_df.iterrows():
        aid = t_row["account_id"]
        bal = float(t_row["balance"])
        tmin = float(t_row["tainted_min"])
        tmax = float(t_row["tainted_max"])
        S = float(scores_map.get(aid, 0.0))
        h_score = float(harm_map.get(aid, 0.5))
        r_inflow = float(recent_inflows.get(aid, 0.0))

        row_dict = {
            "account_id": aid,
            "balance": bal,
            "tainted_min": tmin,
            "tainted_max": tmax,
            "S": S,
            "harm_score": h_score,
            "recent_inflow": r_inflow,
        }

        dec_res = decide(row_dict, lam=lam)
        dec_res["account_id"] = aid
        results.append(dec_res)

    res_df = pd.DataFrame(results)
    field_order = [
        "account_id",
        "action",
        "lien_amount",
        "cap_share",
        "hold_hours",
        "needs_human",
        "expected_recovered",
        "expected_clean_blocked",
        "losses",
        "note",
    ]
    return res_df[field_order].copy()

