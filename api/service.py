"""
Backend service layer for Smart Freeze API.

SIMULATED DATA ONLY - prototype for banks, human approves every action.
Never exposes is_mule, role, mule_ids, or victim_ids.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from engine.actions import decide, decide_all
from engine.harm import innocent_blocked

ALLOWED_DELAYS = [60, 180, 300]

# assumption, demo only
EVIDENCE_LOGIT_STEP = 1.5


def compute_held_amount(balance: float, action: str, lien_amount: float, cap_share: float) -> float:
    """Compute held rupees for a given freeze/lien action."""
    if action == "timed_hold":
        return float(balance)
    elif action == "lien":
        return float(min(balance, lien_amount))
    elif action == "lien_cap":
        base_held = min(balance, lien_amount)
        return float(base_held + cap_share * max(0.0, balance - base_held))
    return 0.0


def get_recent_inflow(txns_df: pd.DataFrame, account_id: str, as_of: float) -> float:
    """Compute recent inflow (last 120 minutes up to as_of) into account_id."""
    window_start = as_of - 120.0
    recent = txns_df[
        (txns_df["dst"] == account_id)
        & (txns_df["time"] > window_start)
        & (txns_df["time"] <= as_of)
    ]
    return float(recent["amount"].sum()) if len(recent) > 0 else 0.0


def sanitize_response(obj: Any) -> Any:
    """Recursively strip any forbidden keys from responses."""
    forbidden = {"is_mule", "role", "mule_ids", "victim_ids"}
    if isinstance(obj, dict):
        return {k: sanitize_response(v) for k, v in obj.items() if k not in forbidden}
    elif isinstance(obj, list):
        return [sanitize_response(item) for item in obj]
    return obj


class BackendService:
    """Loads dataset and precomputed caches once at startup and serves API requests."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data"
        self.data_dir = data_dir
        self.cache_dir = data_dir / "cache"

        # 1. Accounts (Never keep is_mule or role)
        raw_accounts = pd.read_csv(self.data_dir / "accounts.csv")
        acc_cols = [c for c in ["account_id", "type", "age_days", "avg_monthly_inflow", "opening_balance"] if c in raw_accounts.columns]
        self.accounts_df = raw_accounts[acc_cols].copy()
        self.account_map = self.accounts_df.set_index("account_id").to_dict(orient="index")

        # 2. Transactions (clean scam_id)
        self.txns_df = pd.read_csv(self.data_dir / "transactions.csv")
        self.txns_df["scam_id"] = self.txns_df["scam_id"].fillna("").astype(str).str.strip()

        # 3. Scams (only id, start_time, total_stolen)
        raw_scams = pd.read_csv(self.data_dir / "scam_truth.csv")
        self.scams_df = raw_scams[["scam_id", "start_time", "total_stolen"]].copy()
        self.scam_map = self.scams_df.set_index("scam_id").to_dict(orient="index")

        # 4. Results robust
        raw_results = pd.read_csv(self.data_dir / "results_robust.csv")
        self.results_robust_df = raw_results.copy()

        # 5. Pre-load per-scam caches
        self.caches: Dict[tuple, Dict[str, pd.DataFrame]] = {}
        for sid in self.scams_df["scam_id"]:
            for delay in ALLOWED_DELAYS:
                t_path = self.cache_dir / f"{sid}_{delay}_trace.csv"
                s_path = self.cache_dir / f"{sid}_{delay}_scores.csv"
                h_path = self.cache_dir / f"{sid}_{delay}_harm.csv"
                if t_path.exists() and s_path.exists() and h_path.exists():
                    t_df = pd.read_csv(t_path)
                    s_df = pd.read_csv(s_path)
                    # Strip is_mule or any forbidden columns
                    s_cols = [c for c in ["account_id", "S", "B", "T", "H", "reasons_for", "reasons_against"] if c in s_df.columns]
                    s_df = s_df[s_cols].copy()

                    h_df = pd.read_csv(h_path)
                    h_cols = [c for c in ["account_id", "harm_score", "salary_dependence", "float_need", "thin_cover", "cover_days"] if c in h_df.columns]
                    h_df = h_df[h_cols].copy()

                    self.caches[(sid, delay)] = {
                        "trace": t_df,
                        "scores": s_df,
                        "harm": h_df,
                    }

    def validate_scam(self, scam_id: str) -> None:
        if scam_id not in self.scam_map:
            raise KeyError(f"Scam '{scam_id}' not found")

    def validate_delay(self, delay: int) -> None:
        if delay not in ALLOWED_DELAYS:
            raise ValueError(f"Invalid delay {delay}. Allowed delays: {ALLOWED_DELAYS}")

    def validate_account(self, account_id: str) -> None:
        if account_id not in self.account_map:
            raise KeyError(f"Account '{account_id}' not found")

    def get_as_of(self, scam_id: str, delay: int) -> tuple[float, float]:
        self.validate_scam(scam_id)
        self.validate_delay(delay)
        start_time = float(self.scam_map[scam_id]["start_time"])
        as_of = min(start_time + delay, 43200.0)
        return start_time, as_of

    def get_scams(self) -> List[Dict[str, Any]]:
        records = self.scams_df.to_dict(orient="records")
        return sanitize_response(records)

    def get_graph(self, scam_id: str, delay: int) -> Dict[str, Any]:
        start_time, as_of = self.get_as_of(scam_id, delay)
        scam_txns = self.txns_df[
            (self.txns_df["scam_id"] == scam_id) & (self.txns_df["time"] <= as_of)
        ].sort_values(["time", "txn_id"])

        edges = [
            {
                "src": row["src"],
                "dst": row["dst"],
                "amount": float(row["amount"]),
                "time": float(row["time"]),
            }
            for _, row in scam_txns.iterrows()
        ]

        touched_ids = set(scam_txns["src"]).union(set(scam_txns["dst"]))
        cache = self.caches.get((scam_id, delay), {})
        tr_map = cache["trace"].set_index("account_id").to_dict(orient="index") if "trace" in cache else {}
        sc_map = cache["scores"].set_index("account_id").to_dict(orient="index") if "scores" in cache else {}

        nodes = []
        for aid in sorted(touched_ids):
            acc_info = self.account_map.get(aid, {})
            tr_info = tr_map.get(aid, {})
            sc_info = sc_map.get(aid, {})

            bal = float(tr_info.get("balance", acc_info.get("opening_balance", 0.0)))
            tmin = float(tr_info.get("tainted_min", 0.0))
            tmax = float(tr_info.get("tainted_max", 0.0))
            s_val = float(sc_info.get("S", 0.0))

            nodes.append({
                "id": aid,
                "type": acc_info.get("type", "unknown"),
                "balance": bal,
                "tainted_min": tmin,
                "tainted_max": tmax,
                "S": s_val,
            })

        result = {
            "nodes": nodes,
            "edges": edges,
            "start_time": start_time,
            "as_of": as_of,
        }
        return sanitize_response(result)

    def get_decisions(self, scam_id: str, delay: int, lam: float) -> List[Dict[str, Any]]:
        start_time, as_of = self.get_as_of(scam_id, delay)
        cache = self.caches.get((scam_id, delay))
        if not cache:
            raise KeyError(f"Cache for scam '{scam_id}' at delay {delay} not found")

        trace_df = cache["trace"]
        scores_df = cache["scores"]
        harm_df = cache["harm"]

        victim_ids = set(self.accounts_df.loc[self.accounts_df["type"] == "victim", "account_id"])
        exit_ids = set(self.accounts_df.loc[self.accounts_df["type"] == "exit", "account_id"])

        actionable_df = trace_df[
            (trace_df["tainted_max"] > 1.0) & (~trace_df["account_id"].isin(victim_ids | exit_ids))
        ].copy()

        decisions_dict = {}
        if len(actionable_df) > 0:
            harm_indexed = harm_df.set_index("account_id")
            dec_df = decide_all(actionable_df, scores_df, harm_indexed, self.txns_df, as_of=as_of, lam=lam)
            decisions_dict = dec_df.set_index("account_id").to_dict(orient="index")

        scores_dict = scores_df.set_index("account_id").to_dict(orient="index")
        candidates = trace_df[trace_df["tainted_max"] > 1.0]

        rows = []
        for _, row in candidates.iterrows():
            aid = row["account_id"]
            atype = self.account_map.get(aid, {}).get("type", "unknown")
            bal = float(row["balance"])
            tmin = float(row["tainted_min"])
            tmax = float(row["tainted_max"])
            s_val = float(scores_dict.get(aid, {}).get("S", 0.0))

            if atype in ("victim", "exit"):
                dec_info = {
                    "action": "none",
                    "lien_amount": 0.0,
                    "cap_share": 0.0,
                    "hold_hours": 0,
                    "needs_human": False,
                    "note": f"Account {aid} is classified as {atype}; exempt from action.",
                }
            else:
                dec_info = decisions_dict.get(aid, {
                    "action": "none",
                    "lien_amount": 0.0,
                    "cap_share": 0.0,
                    "hold_hours": 0,
                    "needs_human": False,
                    "note": "No action recommended.",
                })

            rows.append({
                "account_id": aid,
                "type": atype,
                "balance": bal,
                "tainted_min": tmin,
                "tainted_max": tmax,
                "S": s_val,
                "action": dec_info["action"],
                "lien_amount": float(dec_info.get("lien_amount", 0.0)),
                "cap_share": float(dec_info.get("cap_share", 0.0)),
                "hold_hours": int(dec_info.get("hold_hours", 0)),
                "needs_human": bool(dec_info.get("needs_human", False)),
                "note": str(dec_info.get("note", "")),
            })

        return sanitize_response(rows)

    def get_account(self, account_id: str, scam_id: str, delay: int, lam: float) -> Dict[str, Any]:
        self.validate_account(account_id)
        start_time, as_of = self.get_as_of(scam_id, delay)
        cache = self.caches.get((scam_id, delay))
        if not cache:
            raise KeyError(f"Cache for scam '{scam_id}' at delay {delay} not found")

        acc_info = self.account_map[account_id]
        atype = acc_info.get("type", "unknown")

        # Trace info
        tr_df = cache["trace"]
        tr_match = tr_df[tr_df["account_id"] == account_id]
        if not tr_match.empty:
            tr_row = tr_match.iloc[0]
            bal = float(tr_row["balance"])
            t_prop = float(tr_row["tainted_prop"])
            t_fifo = float(tr_row["tainted_fifo"])
            t_libr = float(tr_row["tainted_libr"])
            tmin = float(tr_row["tainted_min"])
            tmax = float(tr_row["tainted_max"])
        else:
            bal = float(acc_info.get("opening_balance", 0.0))
            t_prop = t_fifo = t_libr = tmin = tmax = 0.0

        # Score info
        sc_df = cache["scores"]
        sc_match = sc_df[sc_df["account_id"] == account_id]
        if not sc_match.empty:
            sc_row = sc_match.iloc[0]
            S = float(sc_row["S"])
            B = float(sc_row["B"])
            T = float(sc_row["T"])
            H = float(sc_row["H"])
            rf = sc_row["reasons_for"]
            ra = sc_row["reasons_against"]
            if isinstance(rf, str):
                try:
                    rf = json.loads(rf)
                except Exception:
                    rf = [rf] if rf else []
            if isinstance(ra, str):
                try:
                    ra = json.loads(ra)
                except Exception:
                    ra = [ra] if ra else []
        else:
            S = B = T = H = 0.0
            rf, ra = [], []

        # Harm info
        h_df = cache["harm"]
        h_match = h_df[h_df["account_id"] == account_id]
        if not h_match.empty:
            h_row = h_match.iloc[0]
            harm_score = float(h_row["harm_score"])
            cover_days = float(h_row["cover_days"])
            float_need = float(h_row["float_need"])
            salary_dependence = float(h_row["salary_dependence"])
            thin_cover = float(h_row["thin_cover"])
        else:
            harm_score = 0.5
            cover_days = float_need = salary_dependence = thin_cover = 0.0

        # Decision
        recent_inflow = get_recent_inflow(self.txns_df, account_id, as_of)
        if atype in ("victim", "exit"):
            decision = {
                "action": "none",
                "lien_amount": 0.0,
                "cap_share": 0.0,
                "hold_hours": 0,
                "needs_human": False,
                "expected_recovered": 0.0,
                "expected_clean_blocked": 0.0,
                "losses": {},
                "note": f"Account {account_id} is classified as {atype}; exempt from action.",
            }
        else:
            row_decide = {
                "account_id": account_id,
                "balance": bal,
                "tainted_min": tmin,
                "tainted_max": tmax,
                "S": S,
                "harm_score": harm_score,
                "recent_inflow": recent_inflow,
            }
            decision = decide(row_decide, lam=lam)

        # Blanket impact
        b_clean = innocent_blocked(bal, tmin, tmax, held=bal)
        blanket = {
            "held": float(bal),
            "clean_low": float(b_clean["low"]),
            "clean_high": float(b_clean["high"]),
        }

        # Smart impact
        s_held = compute_held_amount(
            bal,
            decision["action"],
            float(decision.get("lien_amount", 0.0)),
            float(decision.get("cap_share", 0.0)),
        )
        s_clean = innocent_blocked(bal, tmin, tmax, held=s_held)
        smart = {
            "held": float(s_held),
            "clean_low": float(s_clean["low"]),
            "clean_high": float(s_clean["high"]),
        }

        result = {
            "balance": bal,
            "type": atype,
            "tainted_prop": t_prop,
            "tainted_fifo": t_fifo,
            "tainted_libr": t_libr,
            "tainted_min": tmin,
            "tainted_max": tmax,
            "S": S,
            "B": B,
            "T": T,
            "H": H,
            "reasons_for": rf,
            "reasons_against": ra,
            "harm_score": harm_score,
            "cover_days": cover_days,
            "float_need": float_need,
            "salary_dependence": salary_dependence,
            "thin_cover": thin_cover,
            "decision": decision,
            "blanket": blanket,
            "smart": smart,
        }
        return sanitize_response(result)

    def whatif(
        self,
        account_id: str,
        scam_id: str,
        delay: int,
        lam: float,
        evidence_count: int,
    ) -> Dict[str, Any]:
        self.validate_account(account_id)
        start_time, as_of = self.get_as_of(scam_id, delay)
        cache = self.caches.get((scam_id, delay))
        if not cache:
            raise KeyError(f"Cache for scam '{scam_id}' at delay {delay} not found")

        acc_info = self.account_map[account_id]
        atype = acc_info.get("type", "unknown")

        tr_df = cache["trace"]
        tr_match = tr_df[tr_df["account_id"] == account_id]
        bal = float(tr_match.iloc[0]["balance"]) if not tr_match.empty else float(acc_info.get("opening_balance", 0.0))
        tmin = float(tr_match.iloc[0]["tainted_min"]) if not tr_match.empty else 0.0
        tmax = float(tr_match.iloc[0]["tainted_max"]) if not tr_match.empty else 0.0

        sc_df = cache["scores"]
        sc_match = sc_df[sc_df["account_id"] == account_id]
        S = float(sc_match.iloc[0]["S"]) if not sc_match.empty else 0.0

        h_df = cache["harm"]
        h_match = h_df[h_df["account_id"] == account_id]
        h_score = float(h_match.iloc[0]["harm_score"]) if not h_match.empty else 0.5

        recent_inflow = get_recent_inflow(self.txns_df, account_id, as_of)

        # S_new computation
        if S <= 0.0:
            s_new = 0.0
        else:
            s_clip = float(np.clip(S, 1e-6, 1.0 - 1e-6))
            logit_s = float(np.log(s_clip / (1.0 - s_clip)))
            logit_s_new = logit_s - EVIDENCE_LOGIT_STEP * evidence_count
            s_new = float(1.0 / (1.0 + np.exp(-logit_s_new)))
            s_new = float(np.clip(s_new, 0.0, 1.0))

        if atype in ("victim", "exit"):
            before = {"S": S, "action": "none", "held": 0.0}
            after = {"S": s_new, "action": "none", "held": 0.0}
        else:
            # Before
            row_b = {
                "account_id": account_id,
                "balance": bal,
                "tainted_min": tmin,
                "tainted_max": tmax,
                "S": S,
                "harm_score": h_score,
                "recent_inflow": recent_inflow,
            }
            dec_b = decide(row_b, lam=lam)
            act_b = dec_b["action"]
            held_b = compute_held_amount(
                bal,
                act_b,
                float(dec_b.get("lien_amount", 0.0)),
                float(dec_b.get("cap_share", 0.0)),
            )
            before = {"S": S, "action": act_b, "held": held_b}

            # After
            row_a = {
                "account_id": account_id,
                "balance": bal,
                "tainted_min": tmin,
                "tainted_max": tmax,
                "S": s_new,
                "harm_score": h_score,
                "recent_inflow": recent_inflow,
            }
            dec_a = decide(row_a, lam=lam)
            act_a = dec_a["action"]
            held_a = compute_held_amount(
                bal,
                act_a,
                float(dec_a.get("lien_amount", 0.0)),
                float(dec_a.get("cap_share", 0.0)),
            )
            after = {"S": s_new, "action": act_a, "held": held_a}

        result = {
            "before": before,
            "after": after,
        }
        return sanitize_response(result)

    def get_tradeoff(self, delay: int) -> List[Dict[str, Any]]:
        self.validate_delay(delay)
        delay_df = self.results_robust_df[self.results_robust_df["delay"] == delay].copy()
        # Replace NaN with None for valid JSON serialization
        records = delay_df.replace({np.nan: None}).to_dict(orient="records")
        return sanitize_response(records)
