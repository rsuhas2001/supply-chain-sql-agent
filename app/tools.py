import sqlite3
from typing import Dict, Any, List, Optional
import numpy as np

from app.guardrails import validate_and_sanitize_sql, ALLOWED_TABLES
from data.load_supply_chain_data import populate_dataco_connection

_SHARED_CONN: Optional[sqlite3.Connection] = None


def get_readonly_connection() -> sqlite3.Connection:
    """Returns a SQLite connection initialized with DataCo data and locked with `PRAGMA query_only = ON`."""
    global _SHARED_CONN
    if _SHARED_CONN is None:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        populate_dataco_connection(conn)
        conn.execute("PRAGMA query_only = ON;")
        _SHARED_CONN = conn
    return _SHARED_CONN


def inspect_schema_tool(table_name: str = "all") -> Dict[str, Any]:
    """Tool 1: Introspects table names, column definitions, and row counts."""
    conn = get_readonly_connection()
    cur = conn.cursor()
    targets = sorted(ALLOWED_TABLES) if table_name == "all" else [table_name]
    schemas = {}
    for tbl in targets:
        if tbl not in ALLOWED_TABLES:
            continue
        cols = cur.execute(f"PRAGMA table_info({tbl})").fetchall()
        cnt = cur.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()["c"]
        schemas[tbl] = {
            "row_count": cnt,
            "columns": [{"name": r["name"], "type": r["type"]} for r in cols],
        }
    return {"tool": "inspect_schema", "schemas": schemas}


def execute_safe_sql_tool(sql_query: str) -> Dict[str, Any]:
    """Tool 2: Validates SQL via AST/keyword guardrails and runs it on a read-only connection."""
    sanitized_sql, notes = validate_and_sanitize_sql(sql_query)
    conn = get_readonly_connection()
    cur = conn.cursor()
    rows = cur.execute(sanitized_sql).fetchall()
    records = [dict(r) for r in rows]
    return {
        "tool": "execute_safe_sql",
        "executed_sql": sanitized_sql,
        "guardrail_notes": notes,
        "row_count": len(records),
        "rows": records,
    }


def detect_delivery_delay_anomalies_tool(z_threshold: float = 2.0) -> Dict[str, Any]:
    """
    Tool 3: Runs statistical Z-score anomaly detection across (order_quarter, order_region, shipping_mode)
    cohorts to flag unusual spikes in delivery_delay_days and late_delivery_risk.
    """
    sql = """
    SELECT
        order_quarter,
        order_region,
        shipping_mode,
        COUNT(*) AS total_orders,
        SUM(late_delivery_risk) AS late_orders,
        ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_pct,
        ROUND(AVG(delivery_delay_days), 2) AS avg_delay_days,
        ROUND(SUM(benefit_per_order), 2) AS total_profit_usd
    FROM orders
    GROUP BY order_quarter, order_region, shipping_mode
    HAVING COUNT(*) >= 15
    ORDER BY avg_delay_days DESC
    """
    res = execute_safe_sql_tool(sql)
    rows = res["rows"]
    delays = np.array([r["avg_delay_days"] for r in rows], dtype=float)
    mean_d = float(np.mean(delays))
    std_d = float(np.std(delays)) or 1.0

    anomalies: List[Dict[str, Any]] = []
    for r in rows:
        z = (r["avg_delay_days"] - mean_d) / std_d
        if z >= z_threshold:
            item = dict(r)
            item["z_score"] = round(z, 2)
            anomalies.append(item)

    return {
        "tool": "detect_delivery_delay_anomalies",
        "network_mean_delay_days": round(mean_d, 2),
        "network_std_delay_days": round(std_d, 2),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:8],
    }


def generate_chart_spec_tool(rows: List[Dict[str, Any]], question: str) -> Dict[str, Any]:
    """
    Tool 4: Automatically selects and builds a chart specification (bar, grouped_bar, or line)
    from the SQL query result columns so the Streamlit UI / API consumer can render an immediate chart.
    """
    if not rows:
        return {"chart_type": "none", "x_col": None, "y_col": None, "title": "No data"}

    cols = list(rows[0].keys())
    str_cols = [c for c in cols if isinstance(rows[0][c], str)]
    num_cols = [c for c in cols if isinstance(rows[0][c], (int, float)) and not c.endswith("_id")]

    x_col = str_cols[0] if str_cols else cols[0]
    y_col = num_cols[0] if num_cols else cols[-1]
    color_col = str_cols[1] if len(str_cols) > 1 else None

    chart_type = "line" if "quarter" in x_col or "date" in x_col else "bar"
    return {
        "tool": "generate_chart_spec",
        "chart_type": chart_type,
        "x_col": x_col,
        "y_col": y_col,
        "color_col": color_col,
        "title": f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}",
    }
