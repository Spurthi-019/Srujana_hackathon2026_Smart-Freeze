"""
Feature extraction for mule detection engine.
Extracts Behaviour (B), Trail (T), and History/Legitimacy (H) features.
Excludes victim and exit accounts.
"""

from collections import defaultdict
import networkx as nx
import numpy as np
import pandas as pd
from engine.taint import trace

FEATURE_GROUPS = {
    "B": ["pass_through_ratio", "fast_out_share", "distinct_senders", "burst_ratio", "income_mismatch"],
    "T": ["scam_inflow_share", "hops_from_victim", "tainted_holding_share"],
    "H": ["age_log", "active_days_share", "regular_inflow_share"],
}

READABLE = {
    "pass_through_ratio": (
        "forwards almost all incoming funds",
        "retains incoming funds or spends normally",
    ),
    "fast_out_share": (
        "forwards money within an hour of receiving it",
        "rarely forwards money straight away",
    ),
    "distinct_senders": (
        "receives payments from many different senders",
        "receives payments from few concentrated senders",
    ),
    "burst_ratio": (
        "shows unusual sudden burst of inflow volume",
        "inflow volume is steady and consistent with income",
    ),
    "income_mismatch": (
        "inflow significantly exceeds expected monthly income",
        "inflow aligns with declared monthly income",
    ),
    "scam_inflow_share": (
        "high share of inflows from payments flagged by the trace",
        "inflows come from unflagged normal sources",
    ),
    "hops_from_victim": (
        "close proximity to victim accounts in the scam trail",
        "far or disconnected from scam victim accounts",
    ),
    "tainted_holding_share": (
        "holds a large share of active scam taint relative to balance",
        "holds little to no active scam taint",
    ),
    "age_log": (
        "recently opened account",
        "well-established account with long history",
    ),
    "active_days_share": (
        "sparse activity concentrated around scam events",
        "regular ongoing transaction activity across the month",
    ),
    "regular_inflow_share": (
        "inflows are sporadic or concentrated in few periods",
        "receives regular recurring inflows across the entire month",
    ),
}


def build_features(accounts: pd.DataFrame, txns: pd.DataFrame) -> pd.DataFrame:
    """
    Builds B, T, H features for non-victim, non-exit accounts.
    Returns DataFrame indexed by account_id.
    """
    # Exclude victim and exit accounts
    target_accounts = accounts[~accounts["type"].isin(["victim", "exit"])].copy()
    target_ids = target_accounts["account_id"].tolist()
    target_id_set = set(target_ids)

    # Clean scam_id: treat NaN, float, and "" as blank
    txns_clean = txns.copy()
    txns_clean["scam_id"] = txns_clean["scam_id"].fillna("").astype(str).str.strip()

    # Pre-organize txns
    sorted_txns = txns_clean.sort_values(by=["time", "txn_id"]).copy()

    # Pre-map incoming and outgoing transactions per account
    inflows_by_acc = defaultdict(list)   # aid -> list of (time, amount, src, scam_id)
    outflows_by_acc = defaultdict(list)  # aid -> list of (time, amount, dst, scam_id)

    for _, row in sorted_txns.iterrows():
        t = int(row["time"])
        amt = float(row["amount"])
        src = row["src"]
        dst = row["dst"]
        scam = row["scam_id"]

        outflows_by_acc[src].append((t, amt, dst, scam))
        inflows_by_acc[dst].append((t, amt, src, scam))

    # T (trail) Graph for hops_from_victim
    # shortest hop distance from any victim account following src->dst edges of txns with non-blank scam_id
    scam_txns = sorted_txns[sorted_txns["scam_id"] != ""]
    G = nx.DiGraph()
    for _, row in scam_txns.iterrows():
        G.add_edge(row["src"], row["dst"])

    victim_ids = set(accounts[accounts["type"] == "victim"]["account_id"])
    # Compute shortest distance from any victim
    hops_map = {}
    for aid in target_ids:
        min_dist = 6
        if aid in G:
            for vic in victim_ids:
                if vic in G and nx.has_path(G, vic, aid):
                    try:
                        d = nx.shortest_path_length(G, vic, aid)
                        if d < min_dist:
                            min_dist = d
                    except nx.NetworkXNoPath:
                        pass
        hops_map[aid] = min(6, min_dist)

    # T (trail) tainted_holding_share:
    # max over all scam_ids of tainted_max/balance from trace()
    # (run trace for each scam_id in txns; use 0 if balance is 0)
    unique_scam_ids = [s for s in sorted_txns["scam_id"].unique() if s != ""]
    tainted_holding_share_map = {aid: 0.0 for aid in target_ids}

    for sid in unique_scam_ids:
        trace_df = trace(accounts, sorted_txns, sid)
        for _, r in trace_df.iterrows():
            aid = r["account_id"]
            if aid in target_id_set:
                bal = float(r["balance"])
                t_max = float(r["tainted_max"])
                share = (t_max / bal) if bal > 0 else 0.0
                if share > tainted_holding_share_map[aid]:
                    tainted_holding_share_map[aid] = share

    # Compute features row by row
    records = []
    acc_map = target_accounts.set_index("account_id").to_dict(orient="index")

    for aid in target_ids:
        info = acc_map[aid]
        age_days = float(info["age_days"])
        avg_monthly_inflow = float(info["avg_monthly_inflow"])

        in_list = inflows_by_acc.get(aid, [])
        out_list = outflows_by_acc.get(aid, [])

        total_received = sum(amt for _, amt, _, _ in in_list)
        total_sent = sum(amt for _, amt, _, _ in out_list)

        # B: pass_through_ratio: total sent / total received, capped at 1.5 (0 if nothing received)
        if total_received > 0:
            pass_through_ratio = min(1.5, total_sent / total_received)
        else:
            pass_through_ratio = 0.0

        # B: fast_out_share: share of the account's outgoing txns that occur within 60 minutes after some incoming txn
        if len(out_list) > 0 and len(in_list) > 0:
            in_times = np.array([t for t, _, _, _ in in_list])
            fast_out_count = 0
            for t_out, _, _, _ in out_list:
                diffs = t_out - in_times
                if np.any((diffs >= 0) & (diffs <= 60)):
                    fast_out_count += 1
            fast_out_share = fast_out_count / len(out_list)
        else:
            fast_out_share = 0.0

        # B: distinct_senders: number of distinct senders (use log1p)
        senders = {src for _, _, src, _ in in_list}
        distinct_senders = float(np.log1p(len(senders)))

        # B: burst_ratio: max inflow in any 3-day window / (avg_monthly_inflow/10 + 1), capped at 50, use log1p
        # 3-day window = 3 * 1440 = 4320 minutes
        if len(in_list) > 0:
            in_times = [t for t, _, _, _ in in_list]
            in_amts = [amt for _, amt, _, _ in in_list]
            max_3d_inflow = 0.0
            left = 0
            curr_window_sum = 0.0
            for right in range(len(in_times)):
                curr_window_sum += in_amts[right]
                while in_times[right] - in_times[left] > 4320:
                    curr_window_sum -= in_amts[left]
                    left += 1
                if curr_window_sum > max_3d_inflow:
                    max_3d_inflow = curr_window_sum
        else:
            max_3d_inflow = 0.0

        burst_denom = (avg_monthly_inflow / 10.0) + 1.0
        raw_burst = min(50.0, max_3d_inflow / burst_denom)
        burst_ratio = float(np.log1p(raw_burst))

        # B: income_mismatch: log1p(total received) - log1p(avg_monthly_inflow), clipped to [-5, 5]
        diff_income = np.log1p(total_received) - np.log1p(avg_monthly_inflow)
        income_mismatch = float(np.clip(diff_income, -5.0, 5.0))

        # T: scam_inflow_share: share of total inflow that arrives via txns with non-blank scam_id
        # (payments flagged by the trace)
        scam_inflow = sum(amt for _, amt, _, scam in in_list if scam != "")
        scam_inflow_share = (scam_inflow / total_received) if total_received > 0 else 0.0

        # T: hops_from_victim
        hops_from_victim = float(hops_map[aid])

        # T: tainted_holding_share
        tainted_holding_share = float(tainted_holding_share_map[aid])

        # H: age_log: log1p(age_days)
        age_log = float(np.log1p(age_days))

        # H: active_days_share: share of the 30 days with at least one txn involving the account
        active_days = set()
        for t, _, _, _ in in_list:
            active_days.add(min(29, t // 1440))
        for t, _, _, _ in out_list:
            active_days.add(min(29, t // 1440))
        active_days_share = len(active_days) / 30.0

        # H: regular_inflow_share: share of 4 equal time windows (each 10800 minutes) in which the account receives at least one inflow
        # windows: [0..10800), [10800..21600), [21600..32400), [32400..43200]
        inflow_windows = set()
        for t, _, _, _ in in_list:
            win_idx = min(3, t // 10800)
            inflow_windows.add(win_idx)
        regular_inflow_share = len(inflow_windows) / 4.0

        records.append({
            "account_id": aid,
            "pass_through_ratio": pass_through_ratio,
            "fast_out_share": fast_out_share,
            "distinct_senders": distinct_senders,
            "burst_ratio": burst_ratio,
            "income_mismatch": income_mismatch,
            "scam_inflow_share": scam_inflow_share,
            "hops_from_victim": hops_from_victim,
            "tainted_holding_share": tainted_holding_share,
            "age_log": age_log,
            "active_days_share": active_days_share,
            "regular_inflow_share": regular_inflow_share,
        })

    feat_df = pd.DataFrame(records).set_index("account_id")
    # Clean any possible NaN / inf
    feat_df = feat_df.fillna(0.0).replace([np.inf, -np.inf], 0.0)
    return feat_df
