from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


REPORTS_DIR = Path("reports")


st.set_page_config(
    page_title="Web3 Risk Intelligence",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load_report(filename: str) -> pd.DataFrame:
    path = REPORTS_DIR / filename
    if not path.exists():
        st.error(f"Missing report: {path}")
        st.stop()
    return pd.read_csv(path)


token_risk = load_report("token_liquidity_risk_top50.csv")
token_trends = load_report("token_liquidity_risk_trends.csv")
protocol_risk = load_report("defi_protocol_risk_top50.csv")
protocol_trends = load_report("defi_protocol_risk_trends.csv")
stablecoin_risk = load_report("stablecoin_depeg_risk_top50.csv")


st.title("Web3 Risk Intelligence Dashboard")

st.caption(
    "Liquidity, protocol health, and stablecoin depeg monitoring from public Web3 data sources."
)


top_stablecoin = stablecoin_risk.iloc[0] if not stablecoin_risk.empty else None
top_token = token_risk.iloc[0] if not token_risk.empty else None
top_protocol = protocol_risk.iloc[0] if not protocol_risk.empty else None


metric_1, metric_2, metric_3, metric_4 = st.columns(4)

metric_1.metric("Tracked Tokens", len(token_risk))
metric_2.metric("Tracked Protocols", len(protocol_risk))
metric_3.metric("Tracked Stablecoins", len(stablecoin_risk))

if top_stablecoin is not None:
    metric_4.metric(
        "Highest Depeg Risk",
        str(top_stablecoin["symbol"]),
        int(top_stablecoin["depeg_risk_score"]),
    )


tab_tokens, tab_token_trends, tab_protocols, tab_protocol_trends, tab_stablecoins = (
    st.tabs(
        [
            "Token Liquidity",
            "Token Trends",
            "DeFi Protocols",
            "Protocol Trends",
            "Stablecoins",
        ]
    )
)


with tab_tokens:
    st.subheader("Token Liquidity Risk")

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
        title="Top Token Liquidity Risk Scores",
    )

    st.plotly_chart(fig, width="stretch")
    st.dataframe(token_risk, width="stretch", hide_index=True)


with tab_token_trends:
    st.subheader("Token Liquidity Risk Trends")

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
        title="Largest Token Liquidity Risk Increases",
    )

    st.plotly_chart(fig, width="stretch")
    st.dataframe(token_trends, width="stretch", hide_index=True)


with tab_protocols:
    st.subheader("DeFi Protocol Risk")

    top_protocols = protocol_risk.head(20)

    fig = px.bar(
        top_protocols.sort_values("protocol_risk_score"),
        x="protocol_risk_score",
        y="name",
        orientation="h",
        hover_data=["chain", "category", "tvl", "change_1d", "change_7d"],
        title="Top DeFi Protocol Risk Scores",
    )

    st.plotly_chart(fig, width="stretch")
    st.dataframe(protocol_risk, width="stretch", hide_index=True)


with tab_protocol_trends:
    st.subheader("DeFi Protocol Risk Trends")

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
        title="Largest DeFi Protocol Risk Increases",
    )

    st.plotly_chart(fig, width="stretch")
    st.dataframe(protocol_trends, width="stretch", hide_index=True)


with tab_stablecoins:
    st.subheader("Stablecoin Depeg Risk")

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
        title="Top Stablecoin Depeg Risk Scores",
    )

    st.plotly_chart(fig, width="stretch")
    st.dataframe(stablecoin_risk, width="stretch", hide_index=True)
