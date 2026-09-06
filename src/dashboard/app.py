from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


REPORTS_DIR = Path("reports")


st.set_page_config(
    page_title="Web3 Risk Intelligence",
    page_icon="◈",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --ink: #0b1220;
        --ink-soft: #111c2d;
        --panel: #142338;
        --line: #263a53;
        --text: #edf3f7;
        --muted: #93a8ba;
        --amber: #f4b860;
        --teal: #65d1c3;
    }

    .stApp {
        background: var(--ink);
        color: var(--text);
        font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stSidebar"] {
        background: var(--ink-soft);
        border-right: 1px solid var(--line);
    }

    h1, h2, h3 {
        color: var(--text);
        letter-spacing: -0.03em;
    }

    h1 {
        font-size: clamp(2.1rem, 4vw, 3.7rem) !important;
        line-height: 0.98 !important;
        max-width: 760px;
        margin-bottom: 0.55rem !important;
    }

    h2 {
        font-size: 1.55rem !important;
        margin-top: 1.4rem !important;
    }

    [data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 4px;
        padding: 1rem 1.1rem;
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-size: 0.78rem;
    }

    [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-family: 'IBM Plex Mono', monospace;
    }

    .risk-pulse {
        border-left: 3px solid var(--amber);
        background: linear-gradient(105deg, var(--ink-soft), rgba(20, 35, 56, 0.5));
        padding: 1.15rem 1.4rem 1.25rem;
        margin: 1.4rem 0 1.35rem;
    }

    .risk-pulse-label {
        color: var(--amber);
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.4rem;
    }

    .risk-pulse-copy {
        color: var(--muted);
        font-size: 0.95rem;
        margin: 0;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid var(--line);
    }

    .stTabs [data-baseweb="tab"] {
        color: var(--muted);
        padding: 0.7rem 1rem;
    }

    .stTabs [aria-selected="true"] {
        color: var(--text);
        border-bottom-color: var(--amber);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--line);
    }

    .section-note {
        color: var(--muted);
        font-size: 0.9rem;
        margin: -0.5rem 0 1rem;
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            scroll-behavior: auto !important;
            transition: none !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_report(filename: str) -> pd.DataFrame:
    path = REPORTS_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


REPORT_NAMES = {
    "token_risk": "token_liquidity_risk_top50.csv",
    "token_trends": "token_liquidity_risk_trends.csv",
    "protocol_risk": "defi_protocol_risk_top50.csv",
    "protocol_trends": "defi_protocol_risk_trends.csv",
    "stablecoin_risk": "stablecoin_depeg_risk_top50.csv",
    "stablecoin_trends": "stablecoin_depeg_risk_trends.csv",
    "alerts": "risk_alerts_latest.csv",
}

reports = {key: load_report(filename) for key, filename in REPORT_NAMES.items()}
missing_reports = [
    filename
    for key, filename in REPORT_NAMES.items()
    if not (REPORTS_DIR / filename).exists()
    and not key.endswith("_trends")
]

if missing_reports:
    st.error(
        "Run the pipeline before opening the dashboard. Missing reports: "
        + ", ".join(missing_reports)
    )
    st.stop()

token_risk = reports["token_risk"]
token_trends = reports["token_trends"]
protocol_risk = reports["protocol_risk"]
protocol_trends = reports["protocol_trends"]
stablecoin_risk = reports["stablecoin_risk"]
stablecoin_trends = reports["stablecoin_trends"]
risk_alerts = reports["alerts"]

top_stablecoin = stablecoin_risk.iloc[0] if not stablecoin_risk.empty else None

st.title("Web3 Risk Intelligence")
st.caption(
    "A readable signal layer for liquidity stress, protocol drawdowns, "
    "and stablecoin depeg risk."
)

top_risk_symbol = str(top_stablecoin["symbol"]) if top_stablecoin is not None else "—"
top_risk_score = (
    int(top_stablecoin["depeg_risk_score"]) if top_stablecoin is not None else 0
)
st.markdown(
    f"""
    <div class="risk-pulse">
        <div class="risk-pulse-label">Risk pulse</div>
        <p class="risk-pulse-copy">
            Highest current stablecoin exposure is <strong>{top_risk_symbol}</strong>
            with a depeg score of <strong>{top_risk_score}</strong> out of 100.
            Scores combine price deviation, supply contraction, and chain breadth.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
metric_1.metric("Flagged tokens", len(token_risk))
metric_2.metric("Flagged protocols", len(protocol_risk))
metric_3.metric("Tracked stablecoins", len(stablecoin_risk))
metric_4.metric("Active alerts", len(risk_alerts))
metric_5.metric(
    "Peak depeg risk",
    f"{top_risk_score}/100",
    top_risk_symbol if top_stablecoin is not None else "No data",
)

st.markdown(
    '<p class="section-note">Latest batch outputs from CoinGecko and DefiLlama. '
    "Trend tabs compare the two most recent snapshots.</p>",
    unsafe_allow_html=True,
)


def show_empty_trend_state() -> None:
    st.info(
        "Trend data will appear after the pipeline has completed two runs. "
        "The latest risk tables are ready now."
    )


tab_tokens, tab_token_trends, tab_protocols, tab_protocol_trends, tab_stablecoins, tab_stablecoin_trends, tab_alerts = st.tabs(
    [
        "Token liquidity",
        "Token trends",
        "DeFi protocols",
        "Protocol trends",
        "Stablecoins",
        "Stablecoin trends",
        "Alerts",
    ]
)


with tab_tokens:
    st.subheader("Token liquidity risk")
    top_tokens = token_risk.head(20)
    fig = px.bar(
        top_tokens.sort_values("liquidity_risk_score"),
        x="liquidity_risk_score",
        y="symbol",
        orientation="h",
        hover_data=[
            "name",
            "market_cap",
            "total_volume",
            "volume_to_market_cap_ratio",
        ],
        title="Highest token liquidity risk scores",
        color_discrete_sequence=["#f4b860"],
    )
    st.plotly_chart(fig, width="stretch")
    st.dataframe(token_risk, width="stretch", hide_index=True)


with tab_token_trends:
    st.subheader("Token liquidity trends")
    if token_trends.empty:
        show_empty_trend_state()
    else:
        top_trends = token_trends.sort_values(
            ["risk_score_change", "liquidity_risk_score_latest"],
            ascending=[False, False],
        ).head(20)
        fig = px.bar(
            top_trends.sort_values("risk_score_change"),
            x="risk_score_change",
            y="symbol_latest",
            orientation="h",
            hover_data=[
                "name_latest",
                "liquidity_risk_score_previous",
                "liquidity_risk_score_latest",
                "market_cap_change_pct",
                "volume_change_pct",
            ],
            title="Largest token liquidity risk increases",
            color_discrete_sequence=["#65d1c3"],
        )
        st.plotly_chart(fig, width="stretch")
        st.dataframe(token_trends, width="stretch", hide_index=True)


with tab_protocols:
    st.subheader("DeFi protocol risk")
    top_protocols = protocol_risk.head(20)
    fig = px.bar(
        top_protocols.sort_values("protocol_risk_score"),
        x="protocol_risk_score",
        y="name",
        orientation="h",
        hover_data=["chain", "category", "tvl", "change_1d", "change_7d"],
        title="Highest DeFi protocol risk scores",
        color_discrete_sequence=["#f4b860"],
    )
    st.plotly_chart(fig, width="stretch")
    st.dataframe(protocol_risk, width="stretch", hide_index=True)


with tab_protocol_trends:
    st.subheader("DeFi protocol trends")
    if protocol_trends.empty:
        show_empty_trend_state()
    else:
        top_protocol_trends = protocol_trends.sort_values(
            ["risk_score_change", "protocol_risk_score_latest"],
            ascending=[False, False],
        ).head(20)
        fig = px.bar(
            top_protocol_trends.sort_values("risk_score_change"),
            x="risk_score_change",
            y="name_latest",
            orientation="h",
            hover_data=[
                "chain_latest",
                "category_latest",
                "protocol_risk_score_previous",
                "protocol_risk_score_latest",
                "tvl_previous",
                "tvl_latest",
                "tvl_change_pct",
            ],
            title="Largest DeFi protocol risk increases",
            color_discrete_sequence=["#65d1c3"],
        )
        st.plotly_chart(fig, width="stretch")
        st.dataframe(protocol_trends, width="stretch", hide_index=True)


with tab_stablecoins:
    st.subheader("Stablecoin depeg risk")
    top_stablecoins = stablecoin_risk.head(20)
    fig = px.bar(
        top_stablecoins.sort_values("depeg_risk_score"),
        x="depeg_risk_score",
        y="symbol",
        orientation="h",
        hover_data=[
            "name",
            "price",
            "absolute_depeg",
            "circulating_usd",
            "supply_change_1d_pct",
            "supply_change_7d_pct",
        ],
        title="Highest stablecoin depeg risk scores",
        color_discrete_sequence=["#f4b860"],
    )
    st.plotly_chart(fig, width="stretch")
    st.dataframe(stablecoin_risk, width="stretch", hide_index=True)


with tab_stablecoin_trends:
    st.subheader("Stablecoin depeg trends")
    if stablecoin_trends.empty:
        show_empty_trend_state()
    else:
        top_stablecoin_trends = stablecoin_trends.sort_values(
            ["risk_score_change", "depeg_risk_score_latest"],
            ascending=[False, False],
        ).head(20)
        fig = px.bar(
            top_stablecoin_trends.sort_values("risk_score_change"),
            x="risk_score_change",
            y="symbol_latest",
            orientation="h",
            hover_data=[
                "name_latest",
                "depeg_risk_score_previous",
                "depeg_risk_score_latest",
                "absolute_depeg_latest",
                "circulating_change_pct",
            ],
            title="Largest stablecoin depeg risk increases",
            color_discrete_sequence=["#65d1c3"],
        )
        st.plotly_chart(fig, width="stretch")
        st.dataframe(stablecoin_trends, width="stretch", hide_index=True)


with tab_alerts:
    st.subheader("Risk alerts")
    if risk_alerts.empty:
        st.info("No active alerts in the latest pipeline run.")
    else:
        st.caption(
            "Alerts mark high current scores or a risk-score increase of at least "
            "10 points. Webhook delivery is optional."
        )
        alert_chart = risk_alerts.head(20).copy()
        alert_chart["label"] = (
            alert_chart["symbol"].astype(str)
            + " · "
            + alert_chart["asset_type"].astype(str)
        )
        fig = px.bar(
            alert_chart.sort_values("risk_score"),
            x="risk_score",
            y="label",
            orientation="h",
            hover_data=[
                "name",
                "risk_score_change",
                "risk_level",
                "alert_reason",
                "risk_factors_json",
            ],
            title="Current risk alerts",
            color_discrete_sequence=["#f4b860"],
        )
        st.plotly_chart(fig, width="stretch")
        st.dataframe(risk_alerts, width="stretch", hide_index=True)
