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
