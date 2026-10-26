# Supply Chain Analytics Agent (`supply-chain-sql-agent`)

[![SupplyChain-SQL-Agent CI](https://github.com/rsuhas2001/supply-chain-sql-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/rsuhas2001/supply-chain-sql-agent/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite / PostgreSQL](https://img.shields.io/badge/SQL-SQLite_%7C_PostgreSQL-336791.svg)](https://www.sqlite.org/)
[![Dataset: CC BY-NC-SA 4.0](https://img.shields.io/badge/DataCo_Schema-CC_BY--NC--SA_4.0-orange.svg)](https://data.mendeley.com/datasets/8gx2fvg2k6/5)

**Supply Chain Analytics Agent** is a tool-calling Text-to-SQL assistant that lets operations and logistics teams ask plain-English questions—such as *"Which shipping mode has the most late deliveries this quarter?"*—and automatically inspects the database schema, writes and validates **read-only SQL**, summarizes the results, renders an **automatic chart**, and flags **statistical delivery delay anomalies (`Z-score >= 2.0`)**.

---

## Live Interactive Demo & Preview

- **Live Streamlit App**: **[Launch Supply Chain Analytics Agent on Streamlit Cloud](https://supply-chain-sql-agent.streamlit.app)** *(or click the deployment link in the GitHub **About** sidebar)*
- **Interactive Features**:
  - Ask plain-English questions over 5,000 supply chain orders across 4 normalized relational tables (`orders`, `customers`, `products`, `departments`).
  - Inspect the generated SQL query, step-by-step tool execution trace (`inspect_schema` -> `execute_safe_sql` -> `detect_delivery_delay_anomalies` -> `generate_chart_spec`), and auto-generated bar/line charts.
  - Test adversarial SQL injection prompts (e.g., `DROP TABLE orders;`) to see the read-only guardrails block unsafe queries in real time.

```text
+-----------------------------------------------------------------------------------+
|  Supply Chain Analytics Agent | Plain-English SQL & Delivery Anomaly Triage       |
+-----------------------------------------------------------------------------------+
|  Question: "Which shipping mode has the most late deliveries this quarter?"       |
|                                                                                   |
|  Generated & Validated Read-Only SQL:                                             |
|  SELECT shipping_mode, order_quarter, COUNT(*) AS total_orders,                   |
|         SUM(late_delivery_risk) AS late_deliveries,                               |
|         ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_rate_pct       |
|  FROM orders WHERE order_quarter = '2026-Q3'                                      |
|  GROUP BY shipping_mode, order_quarter ORDER BY late_deliveries DESC LIMIT 100    |
|                                                                                   |
|  Unusual Delivery Delay Pattern Flagged (Z-Score = 3.65):                         |
|  `Southeast Asia` (`First Class` & `Standard Class`) in `2026-Q3` experienced     |
|  an average delivery delay of 4.98 days (100% late delivery rate).                |
+-----------------------------------------------------------------------------------+
```

---

## System Architecture

```text
User Plain-English Question
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Tool 1: `inspect_schema` (`app/tools.py`)                │
│ Introspects approved tables (`orders`, `customers`,      │
│ `products`, `departments`) and column data types         │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│ Dual-Layer SQL Guardrail (`app/guardrails.py`)           │
│ 1. Rejects non-SELECT/WITH queries & stacked `;` queries │
│ 2. Blocks 17 DDL/DML keywords (`DROP`, `DELETE`, etc.)   │
│ 3. Verifies FROM/JOIN tables against schema allowlist    │
│ 4. Enforces `LIMIT 100` cap + `PRAGMA query_only = ON`   │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│ Tool 2: `execute_safe_sql` (`app/tools.py`)              │
│ Runs validated read-only SQL and returns structured rows │
└──────────────┬───────────────────────────┬───────────────┘
               │                           │
               ▼                           ▼
┌────────────────────────────┐ ┌───────────────────────────┐
│ Tool 3: `detect_delivery_  │ │ Tool 4: `generate_chart_  │
│ delay_anomalies` (Z-score) │ │ spec` (Auto Bar/Line UI)  │
└──────────────┬─────────────┘ └─────────────┬─────────────┘
               └──────────────┬──────────────┘
                              ▼
    Plain-English Answer + SQL Table + Auto-Chart + Audit Trace
```

---

## Benchmark Results (28-Question Evaluation Suite)

`eval/agent_benchmark.py` evaluates the agent across **28 test cases**: **20 analytical supply chain questions** with verified ground-truth answers and **8 adversarial SQL injection / DDL-DML trick prompts** designed to bypass read-only rules.

| Benchmark Metric | Verified Score | Notes |
| :--- | :--- | :--- |
| **Total Benchmark Questions** | **28** | 20 analytical supply chain queries + 8 adversarial SQL trick prompts |
| **Analytical SQL Execution Accuracy** | **100.0% (20/20)** | Verified across shipping modes, quarterly trends, regional delays, and loss-making SKUs |
| **Unsafe SQL / Injection Block Rate** | **100.0% (8/8)** | Blocked `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, stacked `;`, `--` comments, and unallowed tables |
| **Overall Benchmark Pass Rate** | **100.0% (28/28)** | Zero leaked write operations; automatic chart spec generated for all valid queries |
| **End-to-End Agent Latency (`p50` / `p95`)** | **14.09 ms / 17.17 ms** | Includes schema inspection, SQL execution, Z-score anomaly scan, and chart spec |

---

## How to Run Locally

```bash
# 1. Clone the repository and create a virtual environment
git clone https://github.com/rsuhas2001/supply-chain-sql-agent.git
cd supply-chain-sql-agent
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build the normalized 5,000-order supply chain SQLite database
python3 data/load_supply_chain_data.py

# 4. Run unit tests and the 28-question benchmark suite
python3 tests/test_agent_and_guardrails.py
python3 eval/agent_benchmark.py

# 5. Launch the interactive Streamlit Dashboard with automatic charts (http://localhost:8501)
python3 -m streamlit run ui/app.py

# 6. (Optional) Launch the FastAPI backend (http://localhost:8001/docs)
python3 -m uvicorn app.api:app --reload --port 8001
```

---

## API Key Security & Public Deployment Protection

- **Secrets Isolation**: No API keys are stored in code. Any optional LLM provider credentials (`OPENAI_API_KEY`) are loaded via environment variables or Streamlit's encrypted **Secrets settings (`st.secrets`)** with strict provider spending caps.
- **Deterministic Read-Only Sandbox**: Public users interacting with the hosted Streamlit demo cannot mutate or corrupt the database because every query passes through `validate_and_sanitize_sql()` (`app/guardrails.py`) and executes over a connection locked with `PRAGMA query_only = ON`.

---

## Limitations & What I Would Improve Next

1. **Complex Window Functions & Multi-CTE Self-Correction Loop**: While the agent handles multi-table `JOIN`s, `GROUP BY` aggregations, and `WHERE` filters cleanly, complex cohort retention or rolling 30-day window queries (`OVER (PARTITION BY ... ROWS BETWEEN ...)`) can occasionally fail on the first pass. Next, I would add a **1-step SQL error self-correction loop** that feeds any `sqlite3.OperationalError` back to the compiler along with the schema to repair syntax automatically.
2. **Semantic Value Linking (Fuzzy Entity Resolution)**: If a user asks about `"SE Asia"` instead of `"Southeast Asia"` or `"Std Class"` instead of `"Standard Class"`, exact string filters may return 0 rows. Adding a lightweight distinct-value lookup index over categorical columns would resolve abbreviations before SQL generation.
3. **Time-Series Forecasting Tool**: Extending `detect_delivery_delay_anomalies` with a seasonal ARIMA / Prophet forecasting tool to predict next quarter's late-delivery risk per lane.

---

## Data Sources & Licenses

- **Dataset Attribution & License**: The relational schema and column definitions (`shipping_mode`, `delivery_status`, `late_delivery_risk`, `days_for_shipping_real`, `days_for_shipment_scheduled`, `order_region`, `market`, `sales`, `benefit_per_order`) are modeled after the public **DataCo Smart Supply Chain for Big Data Analysis** dataset created by **Fabian Constante, Fernando Silva, and António Pereira** (published on Mendeley Data / Kaggle under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International [CC BY-NC-SA 4.0]** license, `DOI: 10.17632/8gx2fvg2k6.5`).
- **Subset / Synthetic Seed Disclosure**: Because the raw 180,000-row DataCo CSV (~95 MB) exceeds lightweight Git/CI limits, `data/load_supply_chain_data.py` supports loading the raw `DataCoSupplyChainDataset.csv` directly when placed in `data/raw/`, and ships with a **deterministic 5,000-order synthetic subset generator** (`seed=42`) that preserves the exact DataCo schema, shipping mode distributions, and regional delay patterns so the repository and GitHub Actions CI run out of the box.
- **Source Code License**: Released under the **MIT License**.
