"""
Smart Freeze: Streamlit Application (Prototype for banks).

SIMULATED DATA ONLY - prototype, human approves every action.
"""

import json
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

from engine.actions import decide, decide_all
from engine.harm import innocent_blocked

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


# ==============================================================================
# Helper Functions for Panels
# ==============================================================================

def render_account_header(
    aid: str,
    acc_type: str,
    balance: float,
    action: str,
    needs_human: bool,
    note: str,
) -> None:
    """Renders Header: id, type, balance, recommended action badge, needs_human flag, and decide note."""
    badge_colors = {
        "none": "#6c757d",      # grey
        "lien": "#0d6efd",      # blue
        "lien_cap": "#fd7e14",  # orange
        "timed_hold": "#dc3545" # red
    }
    bg_color = badge_colors.get(action, "#6c757d")
    badge_html = (
        f'<span style="background-color: {bg_color}; color: white; padding: 4px 12px; '
        f'border-radius: 12px; font-weight: bold; font-size: 0.9em; text-transform: uppercase;">'
        f'{action}</span>'
    )

    human_html = ""
    if needs_human:
        human_html = (
            ' <span style="background-color: #ffc107; color: #212529; padding: 4px 10px; '
            'border-radius: 12px; font-weight: bold; font-size: 0.85em;">'
            '⚠️ Human approval required</span>'
        )

    st.markdown(
        f"### Account `{aid}` ({acc_type}) — Balance: ₹{balance:,.2f} | Action: {badge_html}{human_html}",
        unsafe_allow_html=True,
    )
    st.info(f"**Recommendation note:** {note}")


def render_tracing_panel(
    balance: float,
    t_prop: float,
    t_fifo: float,
    t_libr: float,
    t_min: float,
    t_max: float,
) -> None:
    """Renders Tracing panel (plotly horizontal bars) against balance with sure part & maybe band."""
    st.markdown("#### Tracing Analysis")

    methods = ["Proportional", "FIFO", "LIBR"]
    values = [t_prop, t_fifo, t_libr]

    fig = go.Figure()

    # Reference full balance line/bar (background)
    ref_bal = max(balance, 1.0)

    # Shaded vertical regions for "sure part" [0, t_min] and "maybe band" [t_min, t_max]
    if t_min > 0:
        fig.add_vrect(
            x0=0,
            x1=t_min,
            fillcolor="#28a745",
            opacity=0.15,
            layer="below",
            line_width=0,
            annotation_text="Sure part",
            annotation_position="top left",
        )
    if t_max > t_min:
        fig.add_vrect(
            x0=t_min,
            x1=t_max,
            fillcolor="#ffc107",
            opacity=0.18,
            layer="below",
            line_width=0,
            annotation_text="Maybe band",
            annotation_position="top left",
        )

    # Tainted amount bars for each method
    fig.add_trace(go.Bar(
        y=methods,
        x=values,
        orientation="h",
        name="Tainted Amount",
        marker=dict(color="#1f77b4"),
        text=[f"₹{v:,.2f}" for v in values],
        textposition="auto",
    ))

    # Reference Balance marker line
    fig.add_vline(
        x=balance,
        line_width=2,
        line_dash="dash",
        line_color="#dc3545",
        annotation_text=f"Total Balance (₹{balance:,.2f})",
        annotation_position="bottom right",
    )

    fig.update_layout(
        xaxis_title="Rupees (₹)",
        xaxis=dict(range=[0, max(ref_bal * 1.08, t_max * 1.1, 10.0)]),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=20, t=30, b=30),
        height=260,
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption("three accepted tracing rules give a range; we lock the sure part first.")


def render_priority_panel(
    S: float,
    B: float,
    T: float,
    H: float,
    reasons_for: list,
    reasons_against: list,
) -> None:
    """Renders Priority panel: B, T, H contribution bars, S investigation priority, and reason lists."""
    st.markdown("#### Priority & Behaviour")
    st.markdown(f"**Investigation Priority $S$:** `{S:.4f}`")
    st.caption("a prioritisation signal on simulated data, not proof")

    # Contributions horizontal bars
    groups = ["Behaviour (B)", "Trail (T)", "History (H)"]
    contribs = [B, T, H]
    bar_colors = ["#dc3545" if c > 0 else "#28a745" for c in contribs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=groups,
        x=contribs,
        orientation="h",
        marker=dict(color=bar_colors),
        text=[f"{c:+.3f}" for c in contribs],
        textposition="auto",
    ))
    fig.add_vline(x=0, line_width=1.5, line_color="#333333")
    fig.update_layout(
        xaxis_title="Contribution to Priority (+ pushes mule-like, - pushes innocent)",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=20, t=20, b=30),
        height=220,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Why mule-like:**")
        if reasons_for and len(reasons_for) > 0:
            for r in reasons_for:
                st.markdown(f"- {r}")
        else:
            st.markdown("_none found_")

    with col2:
        st.markdown("**Why this might be innocent:**")
        if reasons_against and len(reasons_against) > 0:
            for r in reasons_against:
                st.markdown(f"- {r}")
        else:
            st.markdown("_none found_")


def render_harm_panel(harm_row: pd.Series) -> None:
    """Renders Harm panel: harm_score, cover_days, float_need, salary_dependence, thin_cover."""
    st.markdown("#### Account Vulnerability & Harm Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Harm Score", f"{harm_row.get('harm_score', 0.0):.3f}")
    c2.metric("Cover Days", f"{harm_row.get('cover_days', 0.0):.1f} d")
    c3.metric("Float Need", f"{harm_row.get('float_need', 0.0):.2f}")
    c4.metric("Salary Dependence", f"{harm_row.get('salary_dependence', 0.0):.2f}")
    c5.metric("Thin Cover", f"{harm_row.get('thin_cover', 0.0):.2f}")


def render_comparison_panel(
    balance: float,
    t_min: float,
    t_max: float,
    action: str,
    lien_amount: float,
    cap_share: float,
) -> tuple:
    """Renders Comparison: Blanket freeze vs Smart Freeze with held rupees and clean blocked range."""
    st.markdown("#### Impact Comparison: Blanket vs Smart Freeze")

    # Blanket freeze = hold the whole balance
    blanket_held = balance
    blanket_clean = innocent_blocked(balance, t_min, t_max, held=blanket_held)

    # Smart Freeze
    if action == "timed_hold":
        smart_held = balance
    elif action == "lien":
        smart_held = lien_amount
    elif action == "lien_cap":
        smart_held = lien_amount + cap_share * (balance - lien_amount)
    else:
        smart_held = 0.0

    smart_clean = innocent_blocked(balance, t_min, t_max, held=smart_held)

    col_blanket, col_smart = st.columns(2)

    with col_blanket:
        st.error("**Blanket Freeze** (Full Balance)")
        st.markdown(f"- **Rupees Held:** ₹{blanket_held:,.2f}")
        st.markdown(f"- **Clean Money Blocked Range:** ₹{blanket_clean['low']:,.2f} .. ₹{blanket_clean['high']:,.2f}")

    with col_smart:
        st.success(f"**Smart Freeze** (Action: `{action}`)")
        st.markdown(f"- **Rupees Actually Held:** ₹{smart_held:,.2f}")
        st.markdown(f"- **Clean Money Blocked Range:** ₹{smart_clean['low']:,.2f} .. ₹{smart_clean['high']:,.2f}")

    return smart_held, smart_clean


def find_nearest_lambda_row(sf_df: pd.DataFrame, target_lam: float) -> pd.Series:
    """Find the smart freeze row whose lam is nearest in log space (lam 0 counts as smallest)."""
    lams = sf_df["lam"].astype(float).values
    pos_lams = [l for l in lams if l > 0]
    min_pos = min(pos_lams) if len(pos_lams) > 0 else 0.005
    eff_zero = min_pos / 2.0
    target = max(float(target_lam), 1e-6)

    def log_dist(l: float) -> float:
        eff_l = l if l > 0 else eff_zero
        return abs(np.log(eff_l) - np.log(target))

    best_idx = min(range(len(sf_df)), key=lambda i: log_dist(lams[i]))
    return sf_df.iloc[best_idx]


def render_tradeoff_tab(results_csv_path: Path, selected_delay: int, sidebar_lam: float) -> None:
    """Render the Trade-off tab comparing policies across delays, recovery rates, and innocent harm."""
    if not results_csv_path.exists():
        st.warning("run python scripts/run_robust.py")
        return

    df = pd.read_csv(results_csv_path)
    delay_df = df[df["delay"] == selected_delay].copy()
    if delay_df.empty:
        st.warning(f"No robust evaluation data for delay {selected_delay} min.")
        return

    # Controls
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        agg_mode = st.radio(
            "Tracing rule aggregation",
            options=["Average over tracing rules", "Worst case over tracing rules"],
            index=0,
            horizontal=True,
        )
    with col_ctrl2:
        include_blanket = st.checkbox("include blanket freeze", value=False)

    if agg_mode == "Average over tracing rules":
        rec_col = "rec_rate_mean"
        clean_col = "clean_blocked_mean"
    else:
        rec_col = "rec_rate_worst"
        clean_col = "clean_blocked_worst"

    sf_df = delay_df[delay_df["policy"].str.startswith("tarazu_")].copy()
    if sf_df.empty:
        st.warning("No smart freeze records found in results.")
        return

    sf_df["lam_val"] = sf_df["lam"].astype(float)
    sf_df = sf_df.sort_values("lam_val")

    # Nearest lambda point
    nearest_row = find_nearest_lambda_row(sf_df, sidebar_lam)
    nearest_lam = nearest_row["lam_val"]

    # Baseline lien_only
    lien_row = delay_df[delay_df["policy"] == "lien_only"]
    lien_rec = lien_row.iloc[0][rec_col] if not lien_row.empty else 0.0
    lien_clean = lien_row.iloc[0][clean_col] if not lien_row.empty else 0.0

    sf_rec = nearest_row[rec_col]
    sf_clean = nearest_row[clean_col]

    # One-line summary above the chart
    summary_msg = (
        f"At this setting smart freeze recovers {sf_rec * 100:.1f}% vs {lien_rec * 100:.1f}% for lien-only, "
        f"while blocking Rs {sf_clean:,.0f} of innocent money vs Rs {lien_clean:,.0f}."
    )
    st.markdown(f"**{summary_msg}**")

    # Scatter plot
    fig = go.Figure()

    # Smart freeze points across evaluated lambdas joined by a line
    sf_x = sf_df[clean_col] / 100000.0
    sf_y = sf_df[rec_col] * 100.0
    sf_hover = [
        f"smart freeze (λ={r['lam']})<br>Recovery: {r[rec_col]*100:.1f}%<br>Innocent Blocked: Rs {r[clean_col]:,.0f} ({r[clean_col]/1e5:.2f}L)<br>Holds on Innocents: {int(r['innocent_holds'])}"
        for _, r in sf_df.iterrows()
    ]
    fig.add_trace(go.Scatter(
        x=sf_x,
        y=sf_y,
        mode="lines+markers",
        name="smart freeze",
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=8, color="#1f77b4"),
        hoverinfo="text",
        hovertext=sf_hover,
    ))

    # Single points
    single_policies = ["lien_only", "lien_prop", "lien_fifo", "lien_libr", "lien_min"]
    if include_blanket:
        single_policies.append("blanket")

    markers_cfg = {
        "lien_only": dict(symbol="diamond", size=10, color="#2ca02c"),
        "lien_prop": dict(symbol="triangle-up", size=10, color="#9467bd"),
        "lien_fifo": dict(symbol="square", size=10, color="#8c564b"),
        "lien_libr": dict(symbol="cross", size=10, color="#e377c2"),
        "lien_min": dict(symbol="triangle-down", size=10, color="#7f7f7f"),
        "blanket": dict(symbol="circle-open", size=12, line=dict(width=2, color="#d62728"), color="#d62728"),
    }

    for pol in single_policies:
        p_row = delay_df[delay_df["policy"] == pol]
        if not p_row.empty:
            r = p_row.iloc[0]
            px = r[clean_col] / 100000.0
            py = r[rec_col] * 100.0
            p_hover = f"{pol}<br>Recovery: {py:.1f}%<br>Innocent Blocked: Rs {r[clean_col]:,.0f} ({px:.2f}L)<br>Holds on Innocents: {int(r['innocent_holds'])}"
            m_style = markers_cfg.get(pol, dict(size=10))
            fig.add_trace(go.Scatter(
                x=[px],
                y=[py],
                mode="markers",
                name=pol,
                marker=m_style,
                hoverinfo="text",
                hovertext=[p_hover],
            ))

    # Highlighted smart freeze point nearest to sidebar lambda
    highlight_x = nearest_row[clean_col] / 100000.0
    highlight_y = nearest_row[rec_col] * 100.0
    highlight_hover = (
        f"smart freeze (nearest λ={nearest_lam})<br>"
        f"Recovery: {highlight_y:.1f}%<br>"
        f"Innocent Blocked: Rs {nearest_row[clean_col]:,.0f} ({highlight_x:.2f}L)<br>"
        f"Holds on Innocents: {int(nearest_row['innocent_holds'])}"
    )
    fig.add_trace(go.Scatter(
        x=[highlight_x],
        y=[highlight_y],
        mode="markers",
        name=f"smart freeze (λ={nearest_lam})",
        marker=dict(size=15, color="#ff7f0e", symbol="star", line=dict(width=1.5, color="#333333")),
        hoverinfo="text",
        hovertext=[highlight_hover],
    ))

    fig.update_layout(
        title=f"Recovery vs Innocent Harm (Delay = {selected_delay} min)",
        xaxis_title="innocent money blocked in Rs lakh (clean_blocked/100000)",
        yaxis_title="stolen money recovered %",
        hovermode="closest",
        legend=dict(x=1.02, y=1, orientation="v"),
        margin=dict(l=40, r=40, t=40, b=40),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)
    st.write(f"nearest evaluated lambda: {nearest_lam}")

    # Table under chart: policy, recovery %, innocent money blocked (Rs), holds on innocents
    table_rows = []

    # 1. lien_only
    if not lien_row.empty:
        lr = lien_row.iloc[0]
        table_rows.append({
            "policy": "lien_only",
            "recovery %": f"{lr[rec_col] * 100:.1f}%",
            "innocent money blocked (Rs)": f"{lr[clean_col]:,.2f}",
            "holds on innocents": int(lr["innocent_holds"]),
        })

    # 2. best single-rule lien
    single_rules = delay_df[delay_df["policy"].isin(["lien_prop", "lien_fifo", "lien_libr", "lien_min"])]
    if not single_rules.empty:
        best_single = single_rules.loc[single_rules[rec_col].idxmax()]
        table_rows.append({
            "policy": f"best single-rule lien ({best_single['policy']})",
            "recovery %": f"{best_single[rec_col] * 100:.1f}%",
            "innocent money blocked (Rs)": f"{best_single[clean_col]:,.2f}",
            "holds on innocents": int(best_single["innocent_holds"]),
        })

    # 3. smart freeze at highlighted lambda
    table_rows.append({
        "policy": f"smart freeze (λ={nearest_lam})",
        "recovery %": f"{nearest_row[rec_col] * 100:.1f}%",
        "innocent money blocked (Rs)": f"{nearest_row[clean_col]:,.2f}",
        "holds on innocents": int(nearest_row["innocent_holds"]),
    })

    # 4. blanket
    b_row = delay_df[delay_df["policy"] == "blanket"]
    if not b_row.empty:
        br = b_row.iloc[0]
        table_rows.append({
            "policy": "blanket",
            "recovery %": f"{br[rec_col] * 100:.1f}%",
            "innocent money blocked (Rs)": f"{br[clean_col]:,.2f}",
            "holds on innocents": int(br["innocent_holds"]),
        })

    table_df = pd.DataFrame(table_rows)
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    # Captions (exact text)
    st.caption("Simulated data, 14 scams, one seed. Smart freeze zero harm is by construction: the sure part is safe under all three tracing rules.")
    st.caption("Recovery assumes simulated exit timing; earlier decisions recover more.")


# ==============================================================================
# Main App Layout
# ==============================================================================

tab_case, tab_tradeoff = st.tabs(["Case view", "Trade-off"])

with tab_case:
    st.subheader(f"Case View: Scam {selected_scam} (as_of = {as_of:.0f} min, delay = {selected_delay} min)")

    # 1. Money-flow graph
    clean_scam = txns_df["scam_id"].fillna("").astype(str).str.strip()
    scam_txns = txns_df[(clean_scam == selected_scam) & (txns_df["time"] <= as_of)].sort_values(["time", "txn_id"]).copy()

    if len(scam_txns) == 0:
        st.info("No scam transactions recorded up to this decision time.")
    else:
        G = nx.DiGraph()
        for _, row in scam_txns.iterrows():
            G.add_edge(row["src"], row["dst"], amount=float(row["amount"]), time=float(row["time"]))

        pos = nx.spring_layout(G, seed=42)

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

            share = (tmax / bal) if bal > 0 else 0.0
            share = float(np.clip(share, 0.0, 1.0))
            node_colors.append(share)

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

        edge_x = []
        edge_y = []
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

    victim_ids = set(accounts_df.loc[accounts_df["type"] == "victim", "account_id"])
    exit_ids = set(accounts_df.loc[accounts_df["type"] == "exit", "account_id"])

    actionable_df = trace_df[
        (trace_df["tainted_max"] > 1.0) & (~trace_df["account_id"].isin(victim_ids | exit_ids))
    ].copy()

    decisions_dict = {}
    if len(actionable_df) > 0:
        decisions_df = decide_all(actionable_df, scores_df, harm_df, txns_df, as_of=as_of, lam=lam)
        decisions_dict = decisions_df.set_index("account_id").to_dict(orient="index")

    table_candidates = trace_df[trace_df["tainted_max"] > 1.0].copy()

    acc_type_map = dict(zip(accounts_df["account_id"], accounts_df["type"]))
    scores_dict = scores_df.set_index("account_id").to_dict(orient="index")

    table_rows = []
    card_options = []
    card_map = {}

    for _, row in table_candidates.iterrows():
        aid = row["account_id"]
        atype = acc_type_map.get(aid, "unknown")
        bal = float(row["balance"])
        tmin = float(row["tainted_min"])
        tmax = float(row["tainted_max"])
        s_info = scores_dict.get(aid, {})
        s_val = s_info.get("S", None)
        s_str = f"{s_val:.4f}" if s_val is not None else "N/A"

        if atype in ("victim", "exit"):
            dec_row = {
                "action": "none",
                "lien_amount": 0.0,
                "cap_share": 0.0,
                "needs_human": False,
                "note": f"Account {aid} is classified as {atype}; exempt from action.",
            }
        else:
            dec_row = decisions_dict.get(aid, {
                "action": "none",
                "lien_amount": 0.0,
                "cap_share": 0.0,
                "needs_human": False,
                "note": "No action recommended.",
            })

        act = dec_row["action"]

        table_rows.append({
            "account_id": aid,
            "type": atype,
            "balance": f"₹{bal:,.2f}",
            "tainted_min": f"₹{tmin:,.2f}",
            "tainted_max": f"₹{tmax:,.2f}",
            "S": s_str,
            "action": act,
        })

        opt_label = f"{aid} ({atype}, {act})"
        card_options.append(opt_label)
        card_map[opt_label] = {
            "account_id": aid,
            "type": atype,
            "balance": bal,
            "t_prop": float(row["tainted_prop"]),
            "t_fifo": float(row["tainted_fifo"]),
            "t_libr": float(row["tainted_libr"]),
            "tainted_min": tmin,
            "tainted_max": tmax,
            "S": float(s_info.get("S", 0.0)),
            "B": float(s_info.get("B", 0.0)),
            "T": float(s_info.get("T", 0.0)),
            "H": float(s_info.get("H", 0.0)),
            "reasons_for": s_info.get("reasons_for", []),
            "reasons_against": s_info.get("reasons_against", []),
            "action": act,
            "lien_amount": float(dec_row.get("lien_amount", 0.0)),
            "cap_share": float(dec_row.get("cap_share", 0.0)),
            "needs_human": bool(dec_row.get("needs_human", False)),
            "note": dec_row.get("note", ""),
        }

    display_table = pd.DataFrame(table_rows)
    st.dataframe(display_table, use_container_width=True)

    # 3. Account Card Section
    st.markdown("---")
    st.subheader("Account Card")

    if not card_options:
        st.info("No candidate accounts with tainted_max > ₹1.00.")
    else:
        chosen_opt = st.selectbox("Select Account to Inspect", card_options)
        acc_data = card_map[chosen_opt]
        aid = acc_data["account_id"]

        # Parse reasons
        rf = acc_data["reasons_for"]
        if isinstance(rf, str):
            try:
                rf = json.loads(rf)
            except Exception:
                rf = [rf] if rf else []

        ra = acc_data["reasons_against"]
        if isinstance(ra, str):
            try:
                ra = json.loads(ra)
            except Exception:
                ra = [ra] if ra else []

        harm_row = harm_df.loc[aid] if aid in harm_df.index else pd.Series()

        # a) Header
        render_account_header(
            aid=aid,
            acc_type=acc_data["type"],
            balance=acc_data["balance"],
            action=acc_data["action"],
            needs_human=acc_data["needs_human"],
            note=acc_data["note"],
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # b) Tracing panel & c) Priority panel side by side
        col_tr, col_pri = st.columns([1, 1])

        with col_tr:
            render_tracing_panel(
                balance=acc_data["balance"],
                t_prop=acc_data["t_prop"],
                t_fifo=acc_data["t_fifo"],
                t_libr=acc_data["t_libr"],
                t_min=acc_data["tainted_min"],
                t_max=acc_data["tainted_max"],
            )

        with col_pri:
            render_priority_panel(
                S=acc_data["S"],
                B=acc_data["B"],
                T=acc_data["T"],
                H=acc_data["H"],
                reasons_for=rf,
                reasons_against=ra,
            )

        # d) Harm panel
        st.markdown("<br>", unsafe_allow_html=True)
        render_harm_panel(harm_row)

        # e) Comparison panel
        st.markdown("<br>", unsafe_allow_html=True)
        smart_held, smart_clean = render_comparison_panel(
            balance=acc_data["balance"],
            t_min=acc_data["tainted_min"],
            t_max=acc_data["tainted_max"],
            action=acc_data["action"],
            lien_amount=acc_data["lien_amount"],
            cap_share=acc_data["cap_share"],
        )

        # f) Plain-text decision record download
        rf_str = ", ".join(rf) if rf else "none found"
        ra_str = ", ".join(ra) if ra else "none found"

        record_text = (
            f"SMART FREEZE DECISION RECORD\n"
            f"---------------------------\n"
            f"Account ID:             {aid}\n"
            f"Account Type:           {acc_data['type']}\n"
            f"Decision Time (as_of):  {as_of:.0f} minutes\n"
            f"Balance:                Rs {acc_data['balance']:,.2f}\n"
            f"Tracing (Proportional): Rs {acc_data['t_prop']:,.2f}\n"
            f"Tracing (FIFO):         Rs {acc_data['t_fifo']:,.2f}\n"
            f"Tracing (LIBR):         Rs {acc_data['t_libr']:,.2f}\n"
            f"Sure Part (tmin):       Rs {acc_data['tainted_min']:,.2f}\n"
            f"Ceiling (tmax):         Rs {acc_data['tainted_max']:,.2f}\n"
            f"Priority Score S:       {acc_data['S']:.4f} (B={acc_data['B']:+.3f}, T={acc_data['T']:+.3f}, H={acc_data['H']:+.3f})\n"
            f"Reasons for (mule):     {rf_str}\n"
            f"Reasons against (inn):  {ra_str}\n"
            f"Action Recommended:     {acc_data['action']}\n"
            f"Amount Held:            Rs {smart_held:,.2f}\n"
            f"Clean Blocked Range:    Rs {smart_clean['low']:,.2f} .. Rs {smart_clean['high']:,.2f}\n"
            f"Needs Human Approval:   {acc_data['needs_human']}\n"
            f"Decision Note:          {acc_data['note']}\n"
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="📄 Download Decision Record",
            data=record_text,
            file_name=f"decision_record_{aid}_{selected_scam}_{selected_delay}m.txt",
            mime="text/plain",
        )

with tab_tradeoff:
    render_tradeoff_tab(data_dir / "results_robust.csv", selected_delay, lam)

