import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from app.agent import SupplyChainSQLAgent

st.set_page_config(
    page_title="SupplyChain-SQL-Agent | DataCo Analytics & Anomaly Dashboard",
    page_icon="📦",
    layout="wide",
)

@st.cache_resource
def get_agent():
    return SupplyChainSQLAgent()

agent = get_agent()

st.title("📦 SupplyChain-SQL-Agent: Plain-English Analytics & Delivery Anomaly Triage")
st.caption(
    "Built on the DataCo Smart Supply Chain schema (5,000 orders across USCA, Europe, LATAM, and Pacific Asia) "
    "with Read-Only SQL Guardrails, Automatic Charting, and Statistical Delay Anomaly Detection."
)

sample_questions = [
    "Which shipping mode has the most late deliveries this quarter?",
    "Compare late delivery rate and average shipping days across all shipping modes.",
    "Which order region and market have the highest delivery delays and late delivery percentage?",
    "Show the quarterly trend of total sales, profit, and late delivery percentage across 2026-Q1 to 2026-Q3.",
    "Break down total sales, profit, and late delivery rate by department and market sector.",
    "Which products and regions have negative benefit per order (loss-making orders)?",
    "DROP TABLE orders; -- (Adversarial SQL Injection Test)",
]

chosen = st.selectbox("Choose a sample question (or type your own below):", sample_questions)
user_q = st.text_input("Ask a question in plain English:", value=chosen)

if st.button("Run Supply Chain Agent", type="primary"):
    resp = agent.run(user_q)

    if resp.guardrail_blocked:
        st.error(resp.answer)
    else:
        st.success(resp.answer)

    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Generated & Validated Read-Only SQL")
        st.code(resp.sql_generated, language="sql")

        if resp.rows_preview:
            df = pd.DataFrame(resp.rows_preview)
            st.subheader("Query Result Table")
            st.dataframe(df, use_container_width=True)

            # Render automatic chart from Tool 4 (`generate_chart_spec`)
            cs = resp.chart_spec
            if cs.get("chart_type") in ("bar", "line") and cs.get("x_col") in df.columns and cs.get("y_col") in df.columns:
                st.subheader(f"Automatic Chart: {cs.get('title')}")
                chart_df = df.set_index(cs["x_col"])[[cs["y_col"]]]
                if cs["chart_type"] == "line":
                    st.line_chart(chart_df)
                else:
                    st.bar_chart(chart_df)

    with col2:
        st.subheader("Agent Tool Execution Trace")
        for tr in resp.tool_traces:
            st.markdown(
                f"**Step {tr.step}: `{tr.tool_name}`** — `{tr.status}` "
                f"({tr.row_count} items, {tr.latency_ms:.2f} ms)"
            )
        if resp.anomalies_flagged:
            st.subheader("Flagged Delivery Delay Anomalies (Z >= 2.0)")
            st.dataframe(pd.DataFrame(resp.anomalies_flagged), use_container_width=True)
        st.metric("End-to-End Latency", f"{resp.total_latency_ms:.2f} ms")
