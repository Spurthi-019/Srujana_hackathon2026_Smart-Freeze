import numpy as np
import pandas as pd


def add_innocents(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    scam_truth: pd.DataFrame,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Adds innocent edge cases:
    - Bystanders: normal accounts receiving small payments from leftover mule funds.
    - Aggregator tainted: one aggregator receiving tainted payments from 2 different scams.
    - Look-alikes (4 roles):
      1. lookalike_busy: age_days 150-400, opening_balance <= 1000, avg_monthly_inflow ~30% of real volume,
         forwards 85-95% within 20-40 mins, active on >= 20 days.
      2. lookalike_festival: 10x inflow during days 19-21, forwards ~70% within an hour during days 19-21.
      3. lookalike_new: age_days 20 with regular activity.
      4. lookalike_payout: receives large batch twice a month and forwards to ~20 gig accounts within 30-60 mins.
    - Account truth: labels all roles, records true tainted received and scam_ids.
    """
    rng = np.random.default_rng(seed)

    accounts2 = accounts.copy()
    txns2 = txns.copy()
    scam_truth2 = scam_truth.copy()

    # Initialize to_bystanders column in scam_truth2
    scam_truth2["to_bystanders"] = 0.0

    contract_cols = ["account_id", "type", "age_days", "avg_monthly_inflow", "opening_balance", "is_mule"]

    # We will identify candidate normal accounts for bystanders:
    # Must be type in (salaried, merchant, gig)
    # Must have opening_balance >= 3000
    normal_candidates = accounts2[
        accounts2["type"].isin(["salaried", "merchant", "gig"]) & (accounts2["opening_balance"] >= 3000)
    ]["account_id"].tolist()

    outgoing_by_acc = {aid: [] for aid in accounts2["account_id"]}
    for _, row in txns2.iterrows():
        outgoing_by_acc[row["src"]].append(int(row["time"]))

    exit_acc_set = {"EXIT_ATM_1", "EXIT_JEWELLER_1", "EXIT_EXCH_1"}
    scam_exit_txns = txns2[txns2["dst"].isin(exit_acc_set) & (txns2["scam_id"] != "")]

    live_balances = dict(zip(accounts2["account_id"], accounts2["opening_balance"].astype(float)))
    for _, row in txns2.sort_values(by=["time"]).iterrows():
        live_balances[row["src"]] -= float(row["amount"])
        live_balances[row["dst"]] += float(row["amount"])

    new_txns = []

    # a) Bystanders (about 8 across different scams)
    # For a scam whose start_time is before day 25 (< 25 * 1440 = 36000)
    eligible_scams = scam_truth2[scam_truth2["start_time"] < 25 * 1440].copy()

    bystander_records = {}
    used_bystanders = set()

    for _, s_row in eligible_scams.iterrows():
        sid = s_row["scam_id"]
        s_exits = scam_exit_txns[scam_exit_txns["scam_id"] == sid]
        if s_exits.empty:
            continue

        mule_src = s_exits.iloc[-1]["src"]
        exit_time = int(s_exits.iloc[-1]["time"])

        mule_bal = live_balances.get(mule_src, 0.0)
        if mule_bal < 2000.0:
            continue

        max_possible = min(25000.0, mule_bal * 0.30)
        if max_possible < 2000.0:
            continue
        amt = round(float(rng.uniform(2000.0, max_possible)), 2)

        receipt_time = exit_time + int(rng.integers(5, 61))
        if receipt_time > 43200:
            continue

        chosen_bystander = None
        shuffled_cands = rng.permutation(normal_candidates)
        for cand in shuffled_cands:
            if cand in used_bystanders:
                continue
            cand_op_bal = accounts2.loc[accounts2["account_id"] == cand, "opening_balance"].values[0]
            if cand_op_bal <= amt:
                continue
            out_times = outgoing_by_acc.get(cand, [])
            in_window = [t for t in out_times if receipt_time <= t <= receipt_time + 7200]
            if len(in_window) >= 3:
                chosen_bystander = cand
                break

        if chosen_bystander is not None:
            used_bystanders.add(chosen_bystander)
            new_txns.append({
                "time": receipt_time,
                "src": mule_src,
                "dst": chosen_bystander,
                "amount": amt,
                "scam_id": sid,
            })
            live_balances[mule_src] -= amt
            live_balances[chosen_bystander] += amt

            idx = scam_truth2.index[scam_truth2["scam_id"] == sid].tolist()[0]
            scam_truth2.at[idx, "remaining_in_mules"] = round(scam_truth2.at[idx, "remaining_in_mules"] - amt, 2)
            scam_truth2.at[idx, "to_bystanders"] = round(scam_truth2.at[idx, "to_bystanders"] + amt, 2)

            if chosen_bystander not in bystander_records:
                bystander_records[chosen_bystander] = {"tainted": 0.0, "scams": []}
            bystander_records[chosen_bystander]["tainted"] += amt
            bystander_records[chosen_bystander]["scams"].append(sid)

    # b) HARD CASE: one aggregator receives tainted payment from 2 different scams
    aggregator_ids = accounts2[accounts2["type"] == "aggregator"]["account_id"].tolist()
    chosen_aggregator = aggregator_ids[0]
    agg_scams_added = 0
    for _, s_row in scam_truth2.iterrows():
        if agg_scams_added >= 2:
            break
        sid = s_row["scam_id"]
        s_exits = scam_exit_txns[scam_exit_txns["scam_id"] == sid]
        if s_exits.empty:
            continue
        mule_src = s_exits.iloc[0]["src"]
        exit_time = int(s_exits.iloc[0]["time"])
        mule_bal = live_balances.get(mule_src, 0.0)
        max_possible = min(25000.0, mule_bal * 0.30)
        if max_possible >= 1000.0:
            amt = round(float(rng.uniform(1000.0, max_possible)), 2)
            t_receipt = exit_time + int(rng.integers(5, 61))
            if t_receipt <= 43200:
                new_txns.append({
                    "time": t_receipt,
                    "src": mule_src,
                    "dst": chosen_aggregator,
                    "amount": amt,
                    "scam_id": sid,
                })
                live_balances[mule_src] -= amt
                live_balances[chosen_aggregator] += amt
                idx = scam_truth2.index[scam_truth2["scam_id"] == sid].tolist()[0]
                scam_truth2.at[idx, "remaining_in_mules"] = round(scam_truth2.at[idx, "remaining_in_mules"] - amt, 2)
                scam_truth2.at[idx, "to_bystanders"] = round(scam_truth2.at[idx, "to_bystanders"] + amt, 2)
                agg_scams_added += 1

    # c) LOOK-ALIKES (4 roles):
    # 1. lookalike_busy:
    # age_days 150-400, opening_balance <= 1000, avg_monthly_inflow ~30% of real monthly volume,
    # forwards 85-95% of each batch to suppliers within 20-40 minutes, active on >= 20 days.
    regular_merchants = accounts2[(accounts2["type"] == "merchant") & (~accounts2["account_id"].isin(used_bystanders))]["account_id"].tolist()
    busy_merchant = regular_merchants[0]
    # Update busy_merchant attributes in accounts2
    idx_busy = accounts2.index[accounts2["account_id"] == busy_merchant].tolist()[0]
    accounts2.at[idx_busy, "age_days"] = int(rng.integers(150, 401))
    accounts2.at[idx_busy, "opening_balance"] = float(rng.uniform(200, 1000))
    # We will adjust avg_monthly_inflow below based on real volume

    customer_pool = accounts2[accounts2["type"].isin(["salaried", "gig"])]["account_id"].tolist()
    supplier_pool = [m for m in regular_merchants if m != busy_merchant]

    # Generate ~150 small inflows across at least 20 distinct days
    busy_days = rng.choice(np.arange(0, 30), size=24, replace=False)
    inflow_times = []
    for d in busy_days:
        n_in_day = int(rng.integers(5, 8))
        d_times = d * 1440 + rng.integers(60, 1380, size=n_in_day)
        inflow_times.extend(d_times)
    inflow_times = np.sort(np.array(inflow_times))

    busy_total_inflow = 0.0
    for t_in in inflow_times:
        amt_in = round(float(rng.uniform(300.0, 1800.0)), 2)
        sender = rng.choice(customer_pool)
        if live_balances[sender] >= amt_in:
            live_balances[sender] -= amt_in
            live_balances[busy_merchant] += amt_in
            busy_total_inflow += amt_in
            new_txns.append({
                "time": int(t_in),
                "src": sender,
                "dst": busy_merchant,
                "amount": amt_in,
                "scam_id": "",
            })
            # Forward 85-95% within 20-40 minutes
            fwd_pct = float(rng.uniform(0.85, 0.95))
            fwd_amt = round(amt_in * fwd_pct, 2)
            t_fwd = min(43200, int(t_in + rng.integers(20, 41)))
            supplier = rng.choice(supplier_pool)
            if live_balances[busy_merchant] >= fwd_amt:
                live_balances[busy_merchant] -= fwd_amt
                live_balances[supplier] += fwd_amt
                new_txns.append({
                    "time": t_fwd,
                    "src": busy_merchant,
                    "dst": supplier,
                    "amount": fwd_amt,
                    "scam_id": "",
                })

    accounts2.at[idx_busy, "avg_monthly_inflow"] = round(busy_total_inflow * 0.30, 2)

    # 2. lookalike_festival:
    # 10x inflow during days 19-21, also forwards ~70% within an hour during days 19-21
    fest_cand = [m for m in regular_merchants[1:] if m not in used_bystanders][0]
    fest_times = np.sort(rng.integers(27360, 31680, size=80))
    for t_f in fest_times:
        amt_f = round(float(rng.uniform(1000.0, 5000.0)), 2)
        sender = rng.choice(customer_pool)
        if live_balances[sender] >= amt_f:
            live_balances[sender] -= amt_f
            live_balances[fest_cand] += amt_f
            new_txns.append({
                "time": int(t_f),
                "src": sender,
                "dst": fest_cand,
                "amount": amt_f,
                "scam_id": "",
            })
            # Forwards ~70% within an hour
            fwd_fest = round(amt_f * float(rng.uniform(0.68, 0.72)), 2)
            t_fwd_f = min(43200, int(t_f + rng.integers(10, 55)))
            supplier = rng.choice(supplier_pool)
            if live_balances[fest_cand] >= fwd_fest:
                live_balances[fest_cand] -= fwd_fest
                live_balances[supplier] += fwd_fest
                new_txns.append({
                    "time": t_fwd_f,
                    "src": fest_cand,
                    "dst": supplier,
                    "amount": fwd_fest,
                    "scam_id": "",
                })

    # 3. lookalike_new: age_days 20 with regular activity
    new_acc_id = "ACC_NEW_001"
    new_acc_row = {
        "account_id": new_acc_id,
        "type": "salaried",
        "age_days": 20,
        "avg_monthly_inflow": 45000.0,
        "opening_balance": 35000.0,
        "is_mule": 0,
    }
    accounts2 = pd.concat([accounts2, pd.DataFrame([new_acc_row])], ignore_index=True)
    live_balances[new_acc_id] = new_acc_row["opening_balance"]

    new_tx_times = np.sort(rng.integers(500, 43000, size=20))
    for t_n in new_tx_times:
        amt_spend = round(float(rng.uniform(200.0, 1200.0)), 2)
        dst_m = rng.choice(supplier_pool)
        if live_balances[new_acc_id] >= amt_spend:
            live_balances[new_acc_id] -= amt_spend
            live_balances[dst_m] += amt_spend
            new_txns.append({
                "time": int(t_n),
                "src": new_acc_id,
                "dst": dst_m,
                "amount": amt_spend,
                "scam_id": "",
            })

    # 4. NEW lookalike_payout (type gig or aggregator):
    # receives a large batch from an employer-like account twice in the month and forwards it
    # to about 20 different gig accounts within 30-60 minutes, is_mule 0, no scam_id, age_days 200-600
    payout_acc_id = "ACC_PAYOUT_001"
    payout_acc_row = {
        "account_id": payout_acc_id,
        "type": "aggregator",
        "age_days": int(rng.integers(200, 601)),
        "avg_monthly_inflow": 500000.0,
        "opening_balance": 20000.0,
        "is_mule": 0,
    }
    accounts2 = pd.concat([accounts2, pd.DataFrame([payout_acc_row])], ignore_index=True)
    live_balances[payout_acc_id] = payout_acc_row["opening_balance"]

    employer_ids = accounts2[(accounts2["type"] == "merchant") & (accounts2["opening_balance"] > 1000000)]["account_id"].tolist()
    if not employer_ids:
        employer_ids = accounts2[accounts2["type"] == "merchant"]["account_id"].tolist()[:3]
    gig_accounts = accounts2[accounts2["type"] == "gig"]["account_id"].tolist()

    # Twice in the month: e.g. day 5 (minute 7200) and day 20 (minute 28800)
    for batch_t in [7200, 28800]:
        emp = rng.choice(employer_ids)
        batch_amt = round(float(rng.uniform(150000, 250000)), 2)
        if live_balances[emp] >= batch_amt:
            live_balances[emp] -= batch_amt
            live_balances[payout_acc_id] += batch_amt
            new_txns.append({
                "time": batch_t,
                "src": emp,
                "dst": payout_acc_id,
                "amount": batch_amt,
                "scam_id": "",
            })

            # Forwards to about 20 different gig accounts within 30-60 minutes
            n_targets = min(20, len(gig_accounts))
            target_gigs = rng.choice(gig_accounts, size=n_targets, replace=False)
            weights = rng.dirichlet(np.ones(n_targets))
            payout_amts = [round(batch_amt * 0.98 * w, 2) for w in weights]
            payout_amts[0] += round(batch_amt * 0.98 - sum(payout_amts), 2)

            for g_target, g_amt in zip(target_gigs, payout_amts):
                delay = int(rng.integers(30, 61))
                t_out = min(43200, batch_t + delay)
                if live_balances[payout_acc_id] >= g_amt:
                    live_balances[payout_acc_id] -= g_amt
                    live_balances[g_target] += g_amt
                    new_txns.append({
                        "time": t_out,
                        "src": payout_acc_id,
                        "dst": g_target,
                        "amount": g_amt,
                        "scam_id": "",
                    })

    # d) Replay check to ensure no negative balances anywhere
    all_combined = pd.concat([txns2, pd.DataFrame(new_txns)], ignore_index=True)
    all_combined = all_combined.sort_values(by=["time"]).reset_index(drop=True)

    sim_balances = dict(zip(accounts2["account_id"], accounts2["opening_balance"].astype(float)))
    final_txns = []
    txn_counter = 0

    for _, row in all_combined.iterrows():
        src = row["src"]
        dst = row["dst"]
        t = int(row["time"])
        req_amt = round(float(row["amount"]), 2)
        scam = row.get("scam_id", "")
        if pd.isna(scam):
            scam = ""

        src_bal = sim_balances[src]
        if src_bal <= 0:
            continue

        if src_bal < req_amt:
            act_amt = round(np.floor(src_bal * 100) / 100.0, 2)
        else:
            act_amt = req_amt

        if act_amt <= 0:
            continue

        sim_balances[src] -= act_amt
        sim_balances[dst] += act_amt

        final_txns.append({
            "txn_id": f"TXN_{txn_counter:06d}",
            "time": t,
            "src": src,
            "dst": dst,
            "amount": act_amt,
            "scam_id": scam
        })
        txn_counter += 1

    txns2 = pd.DataFrame(final_txns)

    # Build account_truth
    actual_bystander_tainted = {b: 0.0 for b in bystander_records}
    actual_bystander_scams = {b: set() for b in bystander_records}
    actual_agg_tainted = 0.0
    actual_agg_scams = set()

    mule_accs = set(accounts2[accounts2["is_mule"] == 1]["account_id"])

    for _, row in txns2.iterrows():
        if row["src"] in mule_accs and row["scam_id"] != "":
            dst = row["dst"]
            if dst in bystander_records:
                actual_bystander_tainted[dst] += float(row["amount"])
                actual_bystander_scams[dst].add(row["scam_id"])
            elif dst == chosen_aggregator:
                actual_agg_tainted += float(row["amount"])
                actual_agg_scams.add(row["scam_id"])

    scam_victim_map = {}
    scam_mule_map = {}
    for _, s_row in scam_truth2.iterrows():
        sid = s_row["scam_id"]
        v_list = s_row["victim_ids"].split(",")
        for v in v_list:
            scam_victim_map.setdefault(v, []).append(sid)
        m_list = s_row["mule_ids"].split(",")
        for m in m_list:
            scam_mule_map.setdefault(m, []).append(sid)

    truth_records = []
    for _, acc_row in accounts2.iterrows():
        aid = acc_row["account_id"]
        atype = acc_row["type"]

        if aid == chosen_aggregator:
            role = "aggregator_tainted"
            tainted = round(actual_agg_tainted, 2)
            scams_str = ",".join(sorted(actual_agg_scams))
        elif aid in bystander_records:
            role = "bystander"
            tainted = round(actual_bystander_tainted[aid], 2)
            scams_str = ",".join(sorted(actual_bystander_scams[aid]))
        elif aid == busy_merchant:
            role = "lookalike_busy"
            tainted = 0.0
            scams_str = ""
        elif aid == fest_cand:
            role = "lookalike_festival"
            tainted = 0.0
            scams_str = ""
        elif aid == new_acc_id:
            role = "lookalike_new"
            tainted = 0.0
            scams_str = ""
        elif aid == payout_acc_id:
            role = "lookalike_payout"
            tainted = 0.0
            scams_str = ""
        elif atype == "victim":
            role = "victim"
            tainted = 0.0
            scams_str = ",".join(sorted(scam_victim_map.get(aid, [])))
        elif atype == "mule":
            role = "mule"
            tainted = 0.0
            scams_str = ",".join(sorted(scam_mule_map.get(aid, [])))
        elif atype == "exit":
            role = "exit"
            tainted = 0.0
            scams_str = ""
        else:
            role = "normal"
            tainted = 0.0
            scams_str = ""

        truth_records.append({
            "account_id": aid,
            "role": role,
            "true_tainted_received": tainted,
            "scam_ids": scams_str,
        })

    account_truth = pd.DataFrame(truth_records)
    accounts2 = accounts2[contract_cols].copy()

    return accounts2, txns2, scam_truth2, account_truth
