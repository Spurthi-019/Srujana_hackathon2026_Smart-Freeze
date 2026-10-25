"""
Smart Freeze: Streamlit Application (Prototype for banks).

SIMULATED DATA ONLY - prototype, human approves every action.
"""

from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.actions import decide_all

st.set_page_config(
    page_title="Smart Freeze",
    page_icon="❄️",
    layout="wide",
)

# Top Banner
st.warning("⚠️ **SIMULATED DATA - prototype, human approves every action**")

data_dir = PROJECT_ROOT / "data"
cache_dir = data_dir / "cache"

# Check required base data files
scam_truth_path = data_dir / "scam_truth.csv"
accounts_path = data_dir / "accounts.csv"
transactions_path = data_dir / "transactions.csv"

if not (scam_truth_path.exists() and accounts_path.exists() and transactions_path.exists()):
    st.error("Base data files are missing in `data/`. Please generate data first.")
    st.stop()

scams_df = pd.read_csv(scam_truth_path)
accounts_df = pd.read_csv(accounts_path)
txns_df = pd.read_csv(transactions_path)

# Sidebar controls
st.sidebar.title("Smart Freeze Controls")

scam_options = scams_df["scam_id"].tolist()
selected_scam = st.sidebar.selectbox("Select Scam", scam_options)

selected_delay = st.sidebar.selectbox("Decision Delay (minutes)", [60, 180, 300], index=0)

# Log-scale lambda slider 0.001 to 0.25, default 0.05
# Using log10 slider: log10(0.001) = -3.0, log10(0.25) ~= -0.602, log10(0.05) ~= -1.301
lambda_exp = st.sidebar.slider(
    "Lambda Trade-off (log-scale): max recovery <-> min harm",
    min_value=-3.0,
    max_value=-0.60205999,
    value=-1.301029995,
    step=0.05,
    help="Higher lambda prioritizes minimizing harm to clean accounts; lower lambda prioritizes recovery.",
)
lam = float(10 ** lambda_exp)
st.sidebar.markdown(f"**Current λ:** `{lam:.4f}`")

# Check cache files
trace_file = cache_dir / f"{selected_scam}_{selected_delay}_trace.csv"
scores_file = cache_dir / f"{selected_scam}_{selected_delay}_scores.csv"
harm_file = cache_dir / f"{selected_scam}_{selected_delay}_harm.csv"

if not (trace_file.exists() and scores_file.exists() and harm_file.exists()):
    st.info("⚠️ Cache files are missing for this selection. Please run: `python scripts/precompute.py`")
    st.stop()

# Load cached data
trace_df = pd.read_csv(trace_file)
scores_df = pd.read_csv(scores_file)
harm_df = pd.read_csv(harm_file, index_col="account_id")

# Compute as_of
scam_info = scams_df[scams_df["scam_id"] == selected_scam].iloc[0]
t0 = float(scam_info["start_time"])
as_of = min(t0 + selected_delay, 43200.0)

# Navigation tabs
tab_case, = st.tabs(["Case View"])

with tab_case:
    st.subheader(f"Case View: Scam {selected_scam} (as_of = {as_of:.0f} min, delay = {selected_delay} min)")

    # 1. Build money-flow graph from txns with this scam_id and time <= as_of
    clean_scam = txns_df["scam_id"].fillna("").astype(str).str.strip()
    scam_txns = txns_df[(clean_scam == selected_scam) & (txns_df["time"] <= as_of)].sort_values(["time", "txn_id"]).copy()

    if len(scam_txns) == 0:
        st.info("No scam transactions recorded up to this decision time.")
    else:
        # Build DiGraph
        G = nx.DiGraph()
        for _, row in scam_txns.iterrows():
            G.add_edge(row["src"], row["dst"], amount=float(row["amount"]), time=float(row["time"]))

        # Fixed layout seed 42
        pos = nx.spring_layout(G, seed=42)

        # Merge account metadata with trace info
        tr_map = trace_df.set_index("account_id").to_dict(orient="index")
        acc_map = accounts_df.set_index("account_id").to_dict(orient="index")

        node_x = []
        node_y = []
        node_colors = []
        node_sizes = []
        node_texts = []

        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)

            tr_info = tr_map.get(node, {})
            acc_info = acc_map.get(node, {})

            acc_type = acc_info.get("type", "unknown")
            bal = float(tr_info.get("balance", acc_info.get("opening_balance", 0.0)))
            tmin = float(tr_info.get("tainted_min", 0.0))
            tmax = float(tr_info.get("tainted_max", 0.0))

            # node colour = tainted_max / balance share (0 - 1)
            share = (tmax / bal) if bal > 0 else 0.0
            share = float(np.clip(share, 0.0, 1.0))
            node_colors.append(share)

            # size by balance (scaled for visibility)
            size = 18 + 22 * (np.log1p(max(0.0, bal)) / 12.0)
            node_sizes.append(float(np.clip(size, 16, 45)))

            hover = (
                f"<b>Account:</b> {node}<br>"
                f"<b>Type:</b> {acc_type}<br>"
                f"<b>Balance:</b> ₹{bal:,.2f}<br>"
                f"<b>Tainted Min..Max:</b> ₹{tmin:,.2f} .. ₹{tmax:,.2f}<br>"
                f"<b>Tainted Share:</b> {share:.1%}"
            )
            node_texts.append(hover)

        # Edges
        edge_x = []
        edge_y = []
        edge_texts = []

        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=1.5, color="#888888"),
            hoverinfo="none",
            mode="lines",
        )

        # Middle points for edge hover
        edge_mid_x = []
        edge_mid_y = []
        edge_mid_text = []
        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_mid_x.append((x0 + x1) / 2.0)
            edge_mid_y.append((y0 + y1) / 2.0)
            amt = data.get("amount", 0.0)
            hrs = data.get("time", 0.0) / 60.0
            edge_mid_text.append(f"Amount: ₹{amt:,.2f}<br>Time: {hrs:.2f} hrs")

        edge_hover_trace = go.Scatter(
            x=edge_mid_x,
            y=edge_mid_y,
            mode="markers",
            hoverinfo="text",
            hovertext=edge_mid_text,
            marker=dict(size=8, color="#555555", opacity=0.6),
        )

        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=[str(n) for n in G.nodes()],
            textposition="top center",
            hoverinfo="text",
            hovertext=node_texts,
            marker=dict(
                showscale=True,
                colorscale="YlOrRd",
                reversescale=False,
                color=node_colors,
                size=node_sizes,
                colorbar=dict(
                    thickness=15,
                    title="Tainted Share",
                    xanchor="left",
                ),
                line=dict(width=2, color="#222222"),
                cmin=0.0,
                cmax=1.0,
            ),
        )

        fig = go.Figure(
            data=[edge_trace, edge_hover_trace, node_trace],
            layout=go.Layout(
                showlegend=False,
                hovermode="closest",
                margin=dict(b=20, l=10, r=10, t=20),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=520,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 2. Table of accounts with tainted_max > 1
    st.markdown("### Action Recommendations (Accounts with Tainted Max > ₹1.00)")

    # Candidate accounts with tainted_max > 1
    # Exclude victim and exit for decide_all
    victim_ids = set(accounts_df.loc[accounts_df["type"] == "victim", "account_id"])
    exit_ids = set(accounts_df.loc[accounts_df["type"] == "exit", "account_id"])

    actionable_df = trace_df[
        (trace_df["tainted_max"] > 1.0) & (~trace_df["account_id"].isin(victim_ids | exit_ids))
    ].copy()

    if len(actionable_df) > 0:
        decisions_df = decide_all(actionable_df, scores_df, harm_df, txns_df, as_of=as_of, lam=lam)
        action_map = dict(zip(decisions_df["account_id"], decisions_df["action"]))
    else:
        action_map = {}

    # All accounts with tainted_max > 1 (including victims/exits in view, but labeled appropriately)
    table_candidates = trace_df[trace_df["tainted_max"] > 1.0].copy()

    acc_type_map = dict(zip(accounts_df["account_id"], accounts_df["type"]))
    scores_map = dict(zip(scores_df["account_id"], scores_df["S"]))

    table_rows = []
    for _, row in table_candidates.iterrows():
        aid = row["account_id"]
        atype = acc_type_map.get(aid, "unknown")
        bal = float(row["balance"])
        tmin = float(row["tainted_min"])
        tmax = float(row["tainted_max"])
        s_val = scores_map.get(aid, None)
        s_str = f"{s_val:.4f}" if s_val is not None else "N/A"

        if atype in ("victim", "exit"):
            act = "none"
        else:
            act = action_map.get(aid, "none")

        table_rows.append({
            "account_id": aid,
            "type": atype,
            "balance": f"₹{bal:,.2f}",
            "tainted_min": f"₹{tmin:,.2f}",
            "tainted_max": f"₹{tmax:,.2f}",
            "S": s_str,
            "action": act,
        })

    display_table = pd.DataFrame(table_rows)
    st.dataframe(display_table, use_container_width=True)
