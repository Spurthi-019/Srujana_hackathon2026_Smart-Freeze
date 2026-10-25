"""
Evaluation harness for Smart Freeze.

Evaluates trace, mule scoring, harm, and decision policies (blanket, lien_only, tarazu)
against simulated scam data over time.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from engine.actions import decide_all
from engine.harm import harm_all, innocent_blocked
from engine.score import score_all
from engine.taint import trace

DELAY = 60
LAMBDAS = [0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
DUST = 1.0


def calibrate_scores(scores_df: pd.DataFrame, is_mule_series: pd.Series) -> pd.DataFrame:
    """
    Calibrates S by undoing balanced class weights:
    pi = share of is_mule in scored accounts
    S = sigmoid(logit(clip(S, 1e-6, 1 - 1e-6)) + ln(pi / (1 - pi)))
    """
    calibrated = scores_df.copy()
    pi = float(is_mule_series.mean())
    if pi <= 0.0 or pi >= 1.0:
        return calibrated

    s_raw = calibrated["S"].values.astype(float)
    s_clipped = np.clip(s_raw, 1e-6, 1.0 - 1e-6)
    logit_s = np.log(s_clipped / (1.0 - s_clipped))
    shift = np.log(pi / (1.0 - pi))
    s_cal = 1.0 / (1.0 + np.exp(-(logit_s + shift)))
    calibrated["S"] = np.round(s_cal, 4)
    return calibrated


def replay_scam_txns(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    scam_id: str,
    as_of: float,
    trace_df: pd.DataFrame,
    actions_dict: Dict[str, Dict[str, Any]],
) -> float:
    """
    Replays transactions for scam_id to evaluate funds recovered under given actions.

    stolen[i] at as_of = max(0, scam inflow - scam outflow up to as_of), capped at balance(as_of).
    For this scam's txns with time > as_of in order, amount x from src:
      - timed_hold moves 0
      - lien moves min(x, max(0, stolen - lien_amount))
      - lien_cap moves min(x * (1 - cap_share), max(0, stolen - lien_amount))
      - none moves x
      stolen[src] -= moved; stolen[dst] += moved
    End:
      recovered = stolen for timed_hold, min(lien_amount, stolen) for lien/lien_cap, else 0.
      Exclude exit accounts.
    """
    all_aids = accounts["account_id"].tolist()
    exit_ids = set(accounts.loc[accounts["type"] == "exit", "account_id"])
    bal_map = dict(zip(trace_df["account_id"], trace_df["balance"].astype(float)))

    clean_scam = txns["scam_id"].fillna("").astype(str).str.strip()
    scam_txns = txns[clean_scam == scam_id].sort_values(["time", "txn_id"]).copy()

    txns_up_to_asof = scam_txns[scam_txns["time"] <= as_of]
    txns_after = scam_txns[scam_txns["time"] > as_of]

    inflows = txns_up_to_asof.groupby("dst")["amount"].sum().to_dict()
    outflows = txns_up_to_asof.groupby("src")["amount"].sum().to_dict()

    stolen = {}
    for aid in all_aids:
        net = max(0.0, float(inflows.get(aid, 0.0)) - float(outflows.get(aid, 0.0)))
        bal = bal_map.get(aid, 0.0)
        stolen[aid] = min(net, bal)

    for _, tx in txns_after.iterrows():
        src = tx["src"]
        dst = tx["dst"]
        x = float(tx["amount"])

        act_info = actions_dict.get(src, {"action": "none", "lien_amount": 0.0, "cap_share": 0.0})
        act = act_info.get("action", "none")
        lien_amt = float(act_info.get("lien_amount", 0.0))
        c_share = float(act_info.get("cap_share", 0.0))
        s_src = stolen.get(src, 0.0)

        if act == "timed_hold":
            moved = 0.0
        elif act == "lien":
            moved = min(x, max(0.0, s_src - lien_amt))
        elif act == "lien_cap":
            moved = min(x * (1.0 - c_share), max(0.0, s_src - lien_amt))
        else:
            moved = x

        stolen[src] = max(0.0, stolen.get(src, 0.0) - moved)
        stolen[dst] = stolen.get(dst, 0.0) + moved

    recovered = 0.0
    for aid in all_aids:
        if aid in exit_ids:
            continue
        act_info = actions_dict.get(aid, {"action": "none", "lien_amount": 0.0, "cap_share": 0.0})
        act = act_info.get("action", "none")
        lien_amt = float(act_info.get("lien_amount", 0.0))
        s_aid = stolen.get(aid, 0.0)

        if act == "timed_hold":
            recovered += s_aid
        elif act in ("lien", "lien_cap"):
            recovered += min(lien_amt, s_aid)

    return float(recovered)


def compute_policy_harm_metrics(
    accounts: pd.DataFrame,
    trace_df: pd.DataFrame,
    actions_dict: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Computes harm and action counts:
    held = balance(as_of) for timed_hold, lien_amount for lien/lien_cap.
    clean_low/high = sum of innocent_blocked(balance, tmin, tmax, held).
    innocent_touched = is_mule=0 accounts with action != none.
    holds_on_innocents = is_mule=0 with timed_hold.
    mules_actioned = is_mule=1 with action != none.
    """
    acc_map = accounts.set_index("account_id").to_dict(orient="index")
    tr_map = trace_df.set_index("account_id").to_dict(orient="index")

    clean_low = 0.0
    clean_high = 0.0
    innocent_touched = 0
    holds_on_innocents = 0
    mules_actioned = 0

    for aid, act_info in actions_dict.items():
        act = act_info.get("action", "none")
        if act == "none":
            continue

        acc_info = acc_map.get(aid, {})
        is_mule = int(acc_info.get("is_mule", 0))

        if is_mule == 1:
            mules_actioned += 1
        else:
            innocent_touched += 1
            if act == "timed_hold":
                holds_on_innocents += 1

        tr_info = tr_map.get(aid, {})
        bal = float(tr_info.get("balance", 0.0))
        tmin = float(tr_info.get("tainted_min", 0.0))
        tmax = float(tr_info.get("tainted_max", 0.0))

        if act == "timed_hold":
            held = bal
        elif act in ("lien", "lien_cap"):
            held = float(act_info.get("lien_amount", 0.0))
        else:
            held = 0.0

        blocked = innocent_blocked(bal, tmin, tmax, held)
        clean_low += blocked["low"]
        clean_high += blocked["high"]

    return {
        "clean_low": float(clean_low),
        "clean_high": float(clean_high),
        "innocent_touched": int(innocent_touched),
        "holds_on_innocents": int(holds_on_innocents),
        "mules_actioned": int(mules_actioned),
    }


def evaluate_all(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    scams: pd.DataFrame,
    delay: float = DELAY,
    lambdas: List[float] = LAMBDAS,
    dust: float = DUST,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Runs the full evaluation across all scams and policies.
    Returns:
      results_df: DataFrame aggregated across scams per (policy, lam)
      metadata: Diagnostics including score calibration stats for the first scam.
    """
    scores_cache: Dict[float, Tuple[pd.DataFrame, pd.DataFrame]] = {}

    victim_ids = set(accounts.loc[accounts["type"] == "victim", "account_id"])
    exit_ids = set(accounts.loc[accounts["type"] == "exit", "account_id"])
    non_target_ids = victim_ids | exit_ids

    is_mule_series = accounts.set_index("account_id")["is_mule"].astype(int)

    # Prepare policy tracking list of dicts per scam
    scam_eval_records = []
    first_scam_diag = {}

    sorted_scams = scams.sort_values("start_time").reset_index(drop=True)

    for idx, scam_row in sorted_scams.iterrows():
        sid = scam_row["scam_id"]
        t0 = float(scam_row["start_time"])
        as_of = t0 + delay
        stolen_total = float(scam_row["total_stolen"])

        # Cache score_all per as_of
        if as_of not in scores_cache:
            raw_scores = score_all(accounts, txns, seed=42, as_of=as_of)
            cal_scores = calibrate_scores(raw_scores, is_mule_series.loc[raw_scores["account_id"]])
            scores_cache[as_of] = (raw_scores, cal_scores)
        else:
            raw_scores, cal_scores = scores_cache[as_of]

        if idx == 0:
            # Diagnostics for the first scam
            non_mules_raw_high = int(((raw_scores["is_mule"] == 0) & (raw_scores["S"] > 0.5)).sum())
            non_mules_cal_high = int(((cal_scores["is_mule"] == 0) & (cal_scores["S"] > 0.5)).sum())
            first_scam_diag = {
                "scam_id": sid,
                "t0": t0,
                "as_of": as_of,
                "non_mules_raw_s_gt_05": non_mules_raw_high,
                "non_mules_cal_s_gt_05": non_mules_cal_high,
            }

        # Tracing and Harm
        trace_df = trace(accounts, txns, sid, as_of=as_of)
        harm_df = harm_all(accounts, txns, as_of=as_of)

        # Touched accounts: tainted_max > DUST, type not victim/exit
        touched_mask = (trace_df["tainted_max"] > dust) & (~trace_df["account_id"].isin(non_target_ids))
        touched_df = trace_df[touched_mask].copy()
        touched_aids = touched_df["account_id"].tolist()

        bal_dict = dict(zip(trace_df["account_id"], trace_df["balance"].astype(float)))

        # Clean scam txns up to as_of for lien_only
        clean_scam = txns["scam_id"].fillna("").astype(str).str.strip()
        scam_txns_up_to_asof = txns[(clean_scam == sid) & (txns["time"] <= as_of)]
        scam_inflows = scam_txns_up_to_asof.groupby("dst")["amount"].sum().to_dict()

        # Build policies
        policies = []

        # 1. Blanket
        blanket_actions = {
            aid: {"action": "timed_hold", "lien_amount": bal_dict.get(aid, 0.0), "cap_share": 0.0}
            for aid in touched_aids
        }
        policies.append(("blanket", None, blanket_actions))

        # 2. Lien only
        lien_actions = {
            aid: {
                "action": "lien",
                "lien_amount": min(bal_dict.get(aid, 0.0), float(scam_inflows.get(aid, 0.0))),
                "cap_share": 0.0,
            }
            for aid in touched_aids
        }
        policies.append(("lien_only", None, lien_actions))

        # 3. Tarazu(lam)
        for lam in lambdas:
            if len(touched_df) > 0:
                dec_df = decide_all(touched_df, cal_scores, harm_df, txns, as_of=as_of, lam=lam)
                tarazu_actions = dec_df.set_index("account_id").to_dict(orient="index")
            else:
                tarazu_actions = {}
            policies.append((f"tarazu_{lam}", lam, tarazu_actions))

        # Evaluate each policy for this scam
        for pol_name, lam_val, act_dict in policies:
            rec = replay_scam_txns(accounts, txns, sid, as_of, trace_df, act_dict)
            harm_m = compute_policy_harm_metrics(accounts, trace_df, act_dict)

            scam_eval_records.append({
                "scam_id": sid,
                "policy": pol_name,
                "lam": lam_val,
                "total_stolen": stolen_total,
                "recovered": rec,
                "clean_low": harm_m["clean_low"],
                "clean_high": harm_m["clean_high"],
                "innocent_touched": harm_m["innocent_touched"],
                "holds_on_innocents": harm_m["holds_on_innocents"],
                "mules_actioned": harm_m["mules_actioned"],
            })

    eval_df = pd.DataFrame(scam_eval_records)

    # Aggregate over scams per (policy, lam)
    # Sum over scams per (policy, lam): total_stolen, recovered, recovery_rate, clean_low, clean_high, innocent_touched, holds_on_innocents, mules_actioned
    agg_rows = []
    # Preserve ordering of policies
    policy_order = [("blanket", None), ("lien_only", None)] + [(f"tarazu_{l}", l) for l in lambdas]

    for pol_name, lam_val in policy_order:
        sub = eval_df[eval_df["policy"] == pol_name]
        tot_stolen = sub["total_stolen"].sum()
        tot_rec = sub["recovered"].sum()
        rec_rate = (tot_rec / tot_stolen) if tot_stolen > 0 else 0.0

        agg_rows.append({
            "policy": pol_name,
            "lam": lam_val,
            "total_stolen": round(float(tot_stolen), 2),
            "recovered": round(float(tot_rec), 2),
            "recovery_rate": round(float(rec_rate), 4),
            "clean_low": round(float(sub["clean_low"].sum()), 2),
            "clean_high": round(float(sub["clean_high"].sum()), 2),
            "innocent_touched": int(sub["innocent_touched"].sum()),
            "holds_on_innocents": int(sub["holds_on_innocents"].sum()),
            "mules_actioned": int(sub["mules_actioned"].sum()),
        })

    results_df = pd.DataFrame(agg_rows)
    return results_df, first_scam_diag
