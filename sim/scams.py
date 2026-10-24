import numpy as np
import pandas as pd


def add_scams(
    accounts: pd.DataFrame,
    txns: pd.DataFrame,
    n_scams: int = 10,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Simulates scam money trails (layered_chain, fan_out, fan_in, fan_out_gather)
    and merges them into the normal transaction and account datasets.

    Returns: (accounts2, txns2, truth_df)
    """
    rng = np.random.default_rng(seed)

    accounts2 = accounts.copy()
    existing_txns = txns.copy()

    # Pre-calculate balances from existing accounts and normal txns
    # to know existing accounts' funds if needed
    running_balances = dict(zip(accounts2["account_id"], accounts2["opening_balance"].astype(float)))
    # We will simulate all transactions on a live ledger
    # 1. Create Exit Accounts: exactly 3 exit accounts
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
        running_balances[eid] = 0.0

    # 2. Shared pool of 12 mules: MULE_00 to MULE_11
    # Mostly age_days 3-60, opening_balance 0-2000, low avg_monthly_inflow.
    # 2 of them HARD cases: age_days above 700 and a few small normal-looking credits and debits in first 25 days.
    mule_pool_ids = [f"MULE_{i:02d}" for i in range(12)]
    # Pick 2 hard case mules, e.g. MULE_10 and MULE_11
    hard_mules = set(mule_pool_ids[-2:])

    extra_normal_txns = []
    normal_account_ids = accounts2["account_id"].tolist()

    for mid in mule_pool_ids:
        if mid in hard_mules:
            age_days = int(rng.integers(701, 1500))
            avg_inflow = float(rng.uniform(15000, 35000))
            opening_bal = float(rng.uniform(2000, 8000))
        else:
            age_days = int(rng.integers(3, 61))
            avg_inflow = float(rng.uniform(1000, 5000))
            opening_bal = float(rng.uniform(0, 2000))

        new_accounts.append({
            "account_id": mid,
            "type": "mule",
            "age_days": age_days,
            "avg_monthly_inflow": avg_inflow,
            "opening_balance": opening_bal,
            "is_mule": 1,
        })
        running_balances[mid] = opening_bal

        # For hard case mules: add a few small normal-looking credits/debits in the first 25 days (0..36000 min)
        if mid in hard_mules:
            # 2 credits and 2 debits
            for _ in range(2):
                c_time = int(rng.integers(100, 34000))
                c_amt = round(float(rng.uniform(200, 1500)), 2)
                src_acc = rng.choice(normal_account_ids)
                extra_normal_txns.append({
                    "time": c_time,
                    "src": src_acc,
                    "dst": mid,
                    "amount": c_amt,
                    "scam_id": "",
                })
            for _ in range(2):
                d_time = int(rng.integers(100, 35000))
                d_amt = round(float(rng.uniform(100, 500)), 2)
                dst_acc = rng.choice(normal_account_ids)
                extra_normal_txns.append({
                    "time": d_time,
                    "src": mid,
                    "dst": dst_acc,
                    "amount": d_amt,
                    "scam_id": "",
                })

    # Shapes spread across n_scams:
    # layered_chain, fan_out, fan_in, fan_out_gather
    shapes_cycle = ["layered_chain", "fan_out", "fan_in", "fan_out_gather"]
    assigned_shapes = [shapes_cycle[i % len(shapes_cycle)] for i in range(n_scams)]
    rng.shuffle(assigned_shapes)

    # Scam start times spread across days 1-29 (minutes: 1440 to 41760)
    # Generate sorted or spaced start times
    raw_start_times = np.linspace(1440, 40000, n_scams) + rng.uniform(-600, 600, size=n_scams)
    raw_start_times = np.clip(raw_start_times, 1440, 41760).astype(int)

    scam_txns = []
    truth_rows = []
    victim_counter = 0

    # Track which mules each scam uses to verify mule sharing
    for i in range(n_scams):
        scam_id = f"S{i+1:02d}"
        shape = assigned_shapes[i]
        start_time = int(raw_start_times[i])

        # Pick 3-5 mules from pool
        # To guarantee the hard mules and overlap, ensure selections from the 12 pool
        n_mules = int(rng.choice([3, 4, 5]))
        # We want at least some scams to include the hard cases and overlap
        selected_mules = list(rng.choice(mule_pool_ids, size=n_mules, replace=False))

        # Stolen amount per victim: 50,000 - 500,000 rupees
        # Shapes:
        # layered_chain: V -> M1 -> M2 -> M3 -> exit
        # fan_out: V -> M1 -> splits to M2, M3, M4 -> each to an exit
        # fan_in: 2-3 victims -> M1 -> M2 -> exit
        # fan_out_gather: V -> M1 -> M2, M3 -> M4 -> exit
        # Setup victims and hops
        scam_victim_ids = []
        this_scam_txns = []
        total_stolen = 0.0

        # We will track mule receipts & balances specifically from this scam
        # (while respecting total account balances)
        mule_holdings = {m: 0.0 for m in selected_mules}

        if shape == "layered_chain":
            # 3 to 4 mules in sequence: V -> M1 -> M2 -> ... -> Mn -> exit
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
            running_balances[v_id] = new_accounts[-1]["opening_balance"]

            # Transfer 1: V -> M1 at start_time
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

            # Hops M_k -> M_{k+1}
            for k in range(len(mules) - 1):
                hop_delay = int(rng.integers(1, 21))
                curr_t += hop_delay
                # Mule forwards 90-100% of what it received
                fwd_pct = float(rng.uniform(0.90, 1.00))
                fwd_amt = round(mule_holdings[mules[k]] * fwd_pct, 2)
                mule_holdings[mules[k]] -= fwd_amt
                mule_holdings[mules[k+1]] += fwd_amt
                this_scam_txns.append({
                    "time": curr_t,
                    "src": mules[k],
                    "dst": mules[k+1],
                    "amount": fwd_amt,
                    "scam_id": scam_id
                })

            # Exit from last mule:
            # Exit happens 30-180 minutes after the first transfer
            # and only 60-90% of the money exits. The rest stays sitting in the last mule.
            first_t = start_time
            exit_delay = int(rng.integers(30, 181))
            exit_t = max(curr_t + int(rng.integers(1, 10)), first_t + exit_delay)
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
            # V -> M1 -> splits to M2, M3, ... -> each to an exit
            # Needs at least 3 mules (M1, M2, M3)
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
            running_balances[v_id] = new_accounts[-1]["opening_balance"]

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

            # M1 splits to remaining mules
            rem_mules = mules[1:]
            hop_delay = int(rng.integers(1, 21))
            split_t = curr_t + hop_delay

            # M1 forwards 90-100% of received
            fwd_total_pct = float(rng.uniform(0.90, 1.00))
            fwd_total = mule_holdings[m1] * fwd_total_pct
            # Split roughly equally with small variation
            weights = rng.dirichlet(np.ones(len(rem_mules)))
            split_amts = [round(fwd_total * w, 2) for w in weights]
            # Adjust rounding difference
            split_amts[0] += round(fwd_total - sum(split_amts), 2)

            for m_sub, amt in zip(rem_mules, split_amts):
                mule_holdings[m1] -= amt
                mule_holdings[m_sub] += amt
                this_scam_txns.append({
                    "time": split_t,
                    "src": m1,
                    "dst": m_sub,
                    "amount": amt,
                    "scam_id": scam_id
                })

            # Each rem_mule forwards to an exit 30-180 min after first transfer
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
            # 2-3 victims -> M1 -> M2 -> exit (or M1 -> M2 -> M3 -> exit)
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
                running_balances[vid] = new_accounts[-1]["opening_balance"]

            mules = selected_mules
            m1 = mules[0]
            # Victims transfer within a short window of start_time
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

            curr_t = last_vic_t
            # M1 -> M2 -> ... -> Mn
            for k in range(len(mules) - 1):
                hop_delay = int(rng.integers(1, 21))
                curr_t += hop_delay
                fwd_pct = float(rng.uniform(0.90, 1.00))
                fwd_amt = round(mule_holdings[mules[k]] * fwd_pct, 2)
                mule_holdings[mules[k]] -= fwd_amt
                mule_holdings[mules[k+1]] += fwd_amt
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
            # V -> M1 -> M2, M3 -> M4 -> exit
            # Requires at least 4 mules
            if len(selected_mules) < 4:
                # Add one more from pool if needed
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
            running_balances[v_id] = new_accounts[-1]["opening_balance"]

            curr_t = start_time
            this_scam_txns.append({
                "time": curr_t,
                "src": v_id,
                "dst": m1,
                "amount": stolen,
                "scam_id": scam_id
            })
            mule_holdings[m1] += stolen

            # M1 splits to mid_mules
            hop_delay = int(rng.integers(1, 21))
            split_t = curr_t + hop_delay
            fwd_total = mule_holdings[m1] * float(rng.uniform(0.90, 1.00))
            weights = rng.dirichlet(np.ones(len(mid_mules)))
            split_amts = [round(fwd_total * w, 2) for w in weights]
            split_amts[0] += round(fwd_total - sum(split_amts), 2)

            for m_sub, amt in zip(mid_mules, split_amts):
                mule_holdings[m1] -= amt
                mule_holdings[m_sub] += amt
                this_scam_txns.append({
                    "time": split_t,
                    "src": m1,
                    "dst": m_sub,
                    "amount": amt,
                    "scam_id": scam_id
                })

            # Mid mules forward to last_m
            hop_delay2 = int(rng.integers(1, 21))
            gather_t = split_t + hop_delay2
            for m_sub in mid_mules:
                mid_fwd = round(mule_holdings[m_sub] * float(rng.uniform(0.90, 1.00)), 2)
                mule_holdings[m_sub] -= mid_fwd
                mule_holdings[last_m] += mid_fwd
                this_scam_txns.append({
                    "time": gather_t,
                    "src": m_sub,
                    "dst": last_m,
                    "amount": mid_fwd,
                    "scam_id": scam_id
                })

            # Exit from last_m
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

        # Calculate scam metrics
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

    # Merge accounts
    new_accounts_df = pd.DataFrame(new_accounts)
    accounts2 = pd.concat([accounts2, new_accounts_df], ignore_index=True)

    # Merge transactions: normal txns + extra normal txns (for hard mules) + scam txns
    # Prepare all extra transactions with correct column structure
    extra_df = pd.DataFrame(extra_normal_txns + scam_txns)
    all_raw_txns = pd.concat([existing_txns, extra_df], ignore_index=True)

    # Sort by time
    all_raw_txns = all_raw_txns.sort_values(by=["time"]).reset_index(drop=True)

    # Replay simulation to ensure balances NEVER go below 0
    # Any transaction that cannot be fulfilled is shrunk or skipped
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

    # Ensure accounts2 matches contract columns:
    # account_id, type, age_days, avg_monthly_inflow, opening_balance, is_mule
    contract_cols = ["account_id", "type", "age_days", "avg_monthly_inflow", "opening_balance", "is_mule"]
    accounts2 = accounts2[contract_cols].copy()

    return accounts2, txns2, truth_df
