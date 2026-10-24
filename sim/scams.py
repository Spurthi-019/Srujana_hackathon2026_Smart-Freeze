import numpy as np
import pandas as pd


def add_scams(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    n_scams: int = 14,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Simulates scam money trails (layered_chain, fan_out, fan_in, fan_out_gather)
    and merges them into the normal transaction and account datasets.

    Changes:
    - Default n_scams = 14; mule pool = 16 (MULE_00 to MULE_15).
    - HARD mules: 4 (MULE_12 to MULE_15), age_days > 700.
      avg_monthly_inflow set to 60-100% of average amount received across scams.
      steady background activity: credits and debits of 500-5000 on >= 20 distinct days.
    - MEDIUM mules: 4 (MULE_08 to MULE_11), age_days 100-400.
      background activity on >= 12 distinct days, avg_monthly_inflow 30-60% of received.
    - Basic mules: 8 (MULE_00 to MULE_07), age_days 3-60.
    """
    rng = np.random.default_rng(seed)

    accounts2 = accounts.copy()
    existing_txns = txns.copy()

    # 1. Exit accounts: exactly 3
    exit_ids = ["EXIT_ATM_1", "EXIT_JEWELLER_1", "EXIT_EXCH_1"]
    new_accounts = []
    for eid in exit_ids:
        new_accounts.append({
            "account_id": eid,
            "type": "exit",
            "age_days": int(rng.integers(300, 2000)),
            "avg_monthly_inflow": 0.0,
            "opening_balance": 0.0,
            "is_mule": 0,
        })

    # 2. Shared pool of 16 mules: MULE_00 to MULE_15
    mule_pool_ids = [f"MULE_{i:02d}" for i in range(16)]
    hard_mules = set(mule_pool_ids[12:16])    # 4 hard mules
    medium_mules = set(mule_pool_ids[8:12])   # 4 medium mules
    basic_mules = set(mule_pool_ids[0:8])     # 8 basic mules

    # Setup scam shapes cycle
    shapes_cycle = ["layered_chain", "fan_out", "fan_in", "fan_out_gather"]
    assigned_shapes = [shapes_cycle[i % len(shapes_cycle)] for i in range(n_scams)]
    rng.shuffle(assigned_shapes)

    # Start times spread across days 1-29 (minutes: 1440 to 41760)
    raw_start_times = np.linspace(1440, 40000, n_scams) + rng.uniform(-600, 600, size=n_scams)
    raw_start_times = np.clip(raw_start_times, 1440, 41760).astype(int)

    scam_txns = []
    truth_rows = []
    victim_counter = 0

    # Track inflows per mule across scams to calculate avg_monthly_inflow appropriately
    mule_scam_inflows = {m: [] for m in mule_pool_ids}

    for i in range(n_scams):
        scam_id = f"S{i+1:02d}"
        shape = assigned_shapes[i]
        start_time = int(raw_start_times[i])

        n_mules = int(rng.choice([3, 4, 5]))
        selected_mules = list(rng.choice(mule_pool_ids, size=n_mules, replace=False))

        scam_victim_ids = []
        this_scam_txns = []
        total_stolen = 0.0
        mule_holdings = {m: 0.0 for m in selected_mules}

        if shape == "layered_chain":
            v_id = f"VIC_{victim_counter:04d}"
            victim_counter += 1
            stolen = round(float(rng.uniform(50000, 500000)), 2)
            total_stolen = stolen
            scam_victim_ids.append(v_id)
            new_accounts.append({
                "account_id": v_id,
                "type": "victim",
                "age_days": int(rng.integers(500, 3001)),
                "avg_monthly_inflow": float(rng.uniform(60000, 200000)),
                "opening_balance": stolen + float(rng.uniform(10000, 50000)),
                "is_mule": 0,
            })

            mules = selected_mules
            curr_t = start_time
            this_scam_txns.append({
                "time": curr_t,
                "src": v_id,
                "dst": mules[0],
                "amount": stolen,
                "scam_id": scam_id
            })
            mule_holdings[mules[0]] += stolen
            mule_scam_inflows[mules[0]].append(stolen)

            for k in range(len(mules) - 1):
                hop_delay = int(rng.integers(1, 21))
                curr_t += hop_delay
                fwd_pct = float(rng.uniform(0.90, 1.00))
                fwd_amt = round(mule_holdings[mules[k]] * fwd_pct, 2)
                mule_holdings[mules[k]] -= fwd_amt
                mule_holdings[mules[k+1]] += fwd_amt
                mule_scam_inflows[mules[k+1]].append(fwd_amt)
                this_scam_txns.append({
                    "time": curr_t,
                    "src": mules[k],
                    "dst": mules[k+1],
                    "amount": fwd_amt,
                    "scam_id": scam_id
                })

            exit_delay = int(rng.integers(30, 181))
            exit_t = max(curr_t + int(rng.integers(1, 10)), start_time + exit_delay)
            last_mule = mules[-1]
            exit_pct = float(rng.uniform(0.60, 0.90))
            exit_amt = round(mule_holdings[last_mule] * exit_pct, 2)
            mule_holdings[last_mule] -= exit_amt
            this_scam_txns.append({
                "time": exit_t,
                "src": last_mule,
                "dst": rng.choice(exit_ids),
                "amount": exit_amt,
                "scam_id": scam_id
            })

        elif shape == "fan_out":
            mules = selected_mules
            v_id = f"VIC_{victim_counter:04d}"
            victim_counter += 1
            stolen = round(float(rng.uniform(60000, 500000)), 2)
            total_stolen = stolen
            scam_victim_ids.append(v_id)
            new_accounts.append({
                "account_id": v_id,
                "type": "victim",
                "age_days": int(rng.integers(500, 3001)),
                "avg_monthly_inflow": float(rng.uniform(60000, 200000)),
                "opening_balance": stolen + float(rng.uniform(10000, 50000)),
                "is_mule": 0,
            })

            curr_t = start_time
            m1 = mules[0]
            this_scam_txns.append({
                "time": curr_t,
                "src": v_id,
                "dst": m1,
                "amount": stolen,
                "scam_id": scam_id
            })
            mule_holdings[m1] += stolen
            mule_scam_inflows[m1].append(stolen)

            rem_mules = mules[1:]
            hop_delay = int(rng.integers(1, 21))
            split_t = curr_t + hop_delay
            fwd_total_pct = float(rng.uniform(0.90, 1.00))
            fwd_total = mule_holdings[m1] * fwd_total_pct
            weights = rng.dirichlet(np.ones(len(rem_mules)))
            split_amts = [round(fwd_total * w, 2) for w in weights]
            split_amts[0] += round(fwd_total - sum(split_amts), 2)

            for m_sub, amt in zip(rem_mules, split_amts):
                mule_holdings[m1] -= amt
                mule_holdings[m_sub] += amt
                mule_scam_inflows[m_sub].append(amt)
                this_scam_txns.append({
                    "time": split_t,
                    "src": m1,
                    "dst": m_sub,
                    "amount": amt,
                    "scam_id": scam_id
                })

            exit_delay = int(rng.integers(30, 181))
            exit_base_t = max(split_t + 5, start_time + exit_delay)
            for m_sub in rem_mules:
                t_exit = exit_base_t + int(rng.integers(0, 15))
                exit_pct = float(rng.uniform(0.60, 0.90))
                exit_amt = round(mule_holdings[m_sub] * exit_pct, 2)
                mule_holdings[m_sub] -= exit_amt
                this_scam_txns.append({
                    "time": t_exit,
                    "src": m_sub,
                    "dst": rng.choice(exit_ids),
                    "amount": exit_amt,
                    "scam_id": scam_id
                })

        elif shape == "fan_in":
            n_vic = int(rng.choice([2, 3]))
            vics = []
            for _ in range(n_vic):
                vid = f"VIC_{victim_counter:04d}"
                victim_counter += 1
                v_stolen = round(float(rng.uniform(50000, 250000)), 2)
                total_stolen += v_stolen
                scam_victim_ids.append(vid)
                vics.append((vid, v_stolen))
                new_accounts.append({
                    "account_id": vid,
                    "type": "victim",
                    "age_days": int(rng.integers(500, 3001)),
                    "avg_monthly_inflow": float(rng.uniform(60000, 200000)),
                    "opening_balance": v_stolen + float(rng.uniform(10000, 50000)),
                    "is_mule": 0,
                })

            mules = selected_mules
            m1 = mules[0]
            last_vic_t = start_time
            for vid, v_amt in vics:
                v_t = start_time + int(rng.integers(0, 15))
                last_vic_t = max(last_vic_t, v_t)
                this_scam_txns.append({
                    "time": v_t,
                    "src": vid,
                    "dst": m1,
                    "amount": v_amt,
                    "scam_id": scam_id
                })
                mule_holdings[m1] += v_amt
                mule_scam_inflows[m1].append(v_amt)

            curr_t = last_vic_t
            for k in range(len(mules) - 1):
                hop_delay = int(rng.integers(1, 21))
                curr_t += hop_delay
                fwd_pct = float(rng.uniform(0.90, 1.00))
                fwd_amt = round(mule_holdings[mules[k]] * fwd_pct, 2)
                mule_holdings[mules[k]] -= fwd_amt
                mule_holdings[mules[k+1]] += fwd_amt
                mule_scam_inflows[mules[k+1]].append(fwd_amt)
                this_scam_txns.append({
                    "time": curr_t,
                    "src": mules[k],
                    "dst": mules[k+1],
                    "amount": fwd_amt,
                    "scam_id": scam_id
                })

            exit_delay = int(rng.integers(30, 181))
            exit_t = max(curr_t + 5, start_time + exit_delay)
            last_m = mules[-1]
            exit_pct = float(rng.uniform(0.60, 0.90))
            exit_amt = round(mule_holdings[last_m] * exit_pct, 2)
            mule_holdings[last_m] -= exit_amt
            this_scam_txns.append({
                "time": exit_t,
                "src": last_m,
                "dst": rng.choice(exit_ids),
                "amount": exit_amt,
                "scam_id": scam_id
            })

        elif shape == "fan_out_gather":
            if len(selected_mules) < 4:
                for candidate in mule_pool_ids:
                    if candidate not in selected_mules:
                        selected_mules.append(candidate)
                        mule_holdings[candidate] = 0.0
                        if len(selected_mules) >= 4:
                            break

            mules = selected_mules
            m1 = mules[0]
            mid_mules = mules[1:-1]
            last_m = mules[-1]

            v_id = f"VIC_{victim_counter:04d}"
            victim_counter += 1
            stolen = round(float(rng.uniform(60000, 500000)), 2)
            total_stolen = stolen
            scam_victim_ids.append(v_id)
            new_accounts.append({
                "account_id": v_id,
                "type": "victim",
                "age_days": int(rng.integers(500, 3001)),
                "avg_monthly_inflow": float(rng.uniform(60000, 200000)),
                "opening_balance": stolen + float(rng.uniform(10000, 50000)),
                "is_mule": 0,
            })

            curr_t = start_time
            this_scam_txns.append({
                "time": curr_t,
                "src": v_id,
                "dst": m1,
                "amount": stolen,
                "scam_id": scam_id
            })
            mule_holdings[m1] += stolen
            mule_scam_inflows[m1].append(stolen)

            hop_delay = int(rng.integers(1, 21))
            split_t = curr_t + hop_delay
            fwd_total = mule_holdings[m1] * float(rng.uniform(0.90, 1.00))
            weights = rng.dirichlet(np.ones(len(mid_mules)))
            split_amts = [round(fwd_total * w, 2) for w in weights]
            split_amts[0] += round(fwd_total - sum(split_amts), 2)

            for m_sub, amt in zip(mid_mules, split_amts):
                mule_holdings[m1] -= amt
                mule_holdings[m_sub] += amt
                mule_scam_inflows[m_sub].append(amt)
                this_scam_txns.append({
                    "time": split_t,
                    "src": m1,
                    "dst": m_sub,
                    "amount": amt,
                    "scam_id": scam_id
                })

            hop_delay2 = int(rng.integers(1, 21))
            gather_t = split_t + hop_delay2
            for m_sub in mid_mules:
                mid_fwd = round(mule_holdings[m_sub] * float(rng.uniform(0.90, 1.00)), 2)
                mule_holdings[m_sub] -= mid_fwd
                mule_holdings[last_m] += mid_fwd
                mule_scam_inflows[last_m].append(mid_fwd)
                this_scam_txns.append({
                    "time": gather_t,
                    "src": m_sub,
                    "dst": last_m,
                    "amount": mid_fwd,
                    "scam_id": scam_id
                })

            exit_delay = int(rng.integers(30, 181))
            exit_t = max(gather_t + 5, start_time + exit_delay)
            exit_pct = float(rng.uniform(0.60, 0.90))
            exit_amt = round(mule_holdings[last_m] * exit_pct, 2)
            mule_holdings[last_m] -= exit_amt
            this_scam_txns.append({
                "time": exit_t,
                "src": last_m,
                "dst": rng.choice(exit_ids),
                "amount": exit_amt,
                "scam_id": scam_id
            })

        exit_total = sum(t["amount"] for t in this_scam_txns if t["dst"] in exit_ids)
        exit_total = round(exit_total, 2)
        remaining_in_mules = round(sum(mule_holdings.values()), 2)
        end_time = max(t["time"] for t in this_scam_txns)
        duration_min = end_time - start_time

        truth_rows.append({
            "scam_id": scam_id,
            "shape": shape,
            "start_time": start_time,
            "victim_ids": ",".join(scam_victim_ids),
            "total_stolen": round(total_stolen, 2),
            "exit_total": exit_total,
            "remaining_in_mules": remaining_in_mules,
            "duration_min": duration_min,
            "mule_ids": ",".join(selected_mules),
        })

        scam_txns.extend(this_scam_txns)

    truth_df = pd.DataFrame(truth_rows)

    # 3. Create Mule Accounts and Background Activity
    # Hard mules: 4, age_days > 700, avg_monthly_inflow 60-100% of average received, background activity on >= 20 days
    # Medium mules: 4, age_days 100-400, avg_monthly_inflow 30-60% of received, background activity on >= 12 days
    # Basic mules: 8, age_days 3-60, opening_bal 0-2000, low avg_monthly_inflow
    extra_normal_txns = []
    normal_account_ids = accounts2[accounts2["type"].isin(["salaried", "merchant", "gig"])]["account_id"].tolist()

    for mid in mule_pool_ids:
        scam_received_list = mule_scam_inflows[mid]
        mean_received = float(np.mean(scam_received_list)) if len(scam_received_list) > 0 else 50000.0

        if mid in hard_mules:
            age_days = int(rng.integers(701, 1600))
            avg_inflow = round(mean_received * float(rng.uniform(0.60, 1.00)), 2)
            opening_bal = float(rng.uniform(25000, 50000))
            n_bg_days = int(rng.integers(21, 28))
        elif mid in medium_mules:
            age_days = int(rng.integers(100, 401))
            avg_inflow = round(mean_received * float(rng.uniform(0.30, 0.60)), 2)
            opening_bal = float(rng.uniform(15000, 30000))
            n_bg_days = int(rng.integers(13, 19))
        else:
            age_days = int(rng.integers(3, 61))
            avg_inflow = float(rng.uniform(1000, 5000))
            opening_bal = float(rng.uniform(0, 2000))
            n_bg_days = 0

        new_accounts.append({
            "account_id": mid,
            "type": "mule",
            "age_days": age_days,
            "avg_monthly_inflow": avg_inflow,
            "opening_balance": opening_bal,
            "is_mule": 1,
        })

        # Generate background activity (credits and debits of 500-5000 with normal accounts)
        if n_bg_days > 0:
            chosen_days = rng.choice(np.arange(0, 30), size=n_bg_days, replace=False)
            for d in chosen_days:
                # 1 credit in the morning, 1 debit in the afternoon
                c_time = int(d * 1440 + rng.integers(100, 600))
                c_amt = round(float(rng.uniform(500, 5000)), 2)
                src_acc = rng.choice(normal_account_ids)
                extra_normal_txns.append({
                    "time": c_time,
                    "src": src_acc,
                    "dst": mid,
                    "amount": c_amt,
                    "scam_id": "",
                })

                d_time = int(d * 1440 + rng.integers(700, 1200))
                d_amt = round(float(rng.uniform(500, min(5000, c_amt + 500))), 2)
                dst_acc = rng.choice(normal_account_ids)
                extra_normal_txns.append({
                    "time": d_time,
                    "src": mid,
                    "dst": dst_acc,
                    "amount": d_amt,
                    "scam_id": "",
                })

    # Merge accounts
    new_accounts_df = pd.DataFrame(new_accounts)
    accounts2 = pd.concat([accounts2, new_accounts_df], ignore_index=True)

    # Merge all transactions: normal txns + extra normal txns + scam txns
    extra_df = pd.DataFrame(extra_normal_txns + scam_txns)
    all_raw_txns = pd.concat([existing_txns, extra_df], ignore_index=True)
    all_raw_txns = all_raw_txns.sort_values(by=["time"]).reset_index(drop=True)

    # Replay simulation to ensure balances NEVER go below 0
    sim_balances = dict(zip(accounts2["account_id"], accounts2["opening_balance"].astype(float)))
    valid_txns = []
    txn_counter = 0

    for _, row in all_raw_txns.iterrows():
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

        valid_txns.append({
            "txn_id": f"TXN_{txn_counter:06d}",
            "time": t,
            "src": src,
            "dst": dst,
            "amount": act_amt,
            "scam_id": scam
        })
        txn_counter += 1

    txns2 = pd.DataFrame(valid_txns)
    contract_cols = ["account_id", "type", "age_days", "avg_monthly_inflow", "opening_balance", "is_mule"]
    accounts2 = accounts2[contract_cols].copy()

    return accounts2, txns2, truth_df
