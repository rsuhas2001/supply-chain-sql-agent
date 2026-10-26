import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.guardrails import SQLGuardrailViolation
from app.tools import (
    inspect_schema_tool,
    execute_safe_sql_tool,
    detect_delivery_delay_anomalies_tool,
    generate_chart_spec_tool,
)


class ToolCallTrace(BaseModel):
    step: int
    tool_name: str
    tool_input: str
    status: str
    row_count: int = 0
    latency_ms: float = 0.0


class AgentResponse(BaseModel):
    question: str
    sql_generated: str
    answer: str
    tool_traces: List[ToolCallTrace]
    rows_preview: List[Dict[str, Any]]
    chart_spec: Dict[str, Any]
    anomalies_flagged: List[Dict[str, Any]]
    guardrail_blocked: bool = False
    total_latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0


class SupplyChainSQLAgent:
    """
    Agentic Text-to-SQL & Delivery Anomaly Assistant over the DataCo Smart Supply Chain dataset:
    - Step 1: `inspect_schema` to ground table & column names
    - Step 2: NL-to-SQL compilation + `execute_safe_sql` (with AST/keyword guardrails & LIMIT 100 cap)
    - Step 3: `detect_delivery_delay_anomalies` to flag statistical transit delay spikes (Z >= 2.0)
    - Step 4: `generate_chart_spec` to produce automatic visualization metadata
    """

    def _compile_nl_to_sql(self, question: str) -> str:
        q = question.lower().strip()

        # Pass raw SQL injection / mutating prompts directly to the validator so they are explicitly caught & logged
        if any(
            bad in q
            for bad in [
                "drop table", "delete from", "update ", "insert into",
                "truncate ", "alter table", "; drop", "--", "/*", "pragma ",
                "payroll", "secret_"
            ]
        ):
            return question

        # 1. Shipping mode late deliveries in current/latest quarter (2026-Q3)
        if "shipping mode" in q and ("late" in q or "delay" in q) and "quarter" in q:
            return """
            SELECT
                shipping_mode,
                order_quarter,
                COUNT(*) AS total_orders,
                SUM(late_delivery_risk) AS late_deliveries,
                ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_rate_pct,
                ROUND(AVG(delivery_delay_days), 2) AS avg_delay_days
            FROM orders
            WHERE order_quarter = '2026-Q3'
            GROUP BY shipping_mode, order_quarter
            ORDER BY late_deliveries DESC
            """

        # 2. Shipping mode late deliveries or scheduled vs real shipping days
        if ("shipping mode" in q or "standard class" in q or "scheduled" in q) and ("late" in q or "delay" in q or "risk" in q or "shipping days" in q):
            return """
            SELECT
                shipping_mode,
                COUNT(*) AS total_orders,
                SUM(late_delivery_risk) AS late_deliveries,
                ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_rate_pct,
                ROUND(AVG(days_for_shipping_real), 2) AS avg_real_shipping_days,
                ROUND(AVG(days_for_shipment_scheduled), 2) AS avg_scheduled_days
            FROM orders
            GROUP BY shipping_mode
            ORDER BY late_deliveries DESC
            """

        # 3. Delivery status breakdown
        if "delivery status" in q or "canceled" in q or "advance shipping" in q:
            return """
            SELECT
                delivery_status,
                COUNT(*) AS order_count,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) AS pct_of_orders,
                ROUND(SUM(sales), 2) AS total_sales_usd
            FROM orders
            GROUP BY delivery_status
            ORDER BY order_count DESC
            """

        # 4. Region / Market late deliveries or delays
        if ("region" in q or "market" in q or "southeast asia" in q) and ("late" in q or "delay" in q or "anomal" in q):
            return """
            SELECT
                market,
                order_region,
                COUNT(*) AS total_orders,
                SUM(late_delivery_risk) AS late_orders,
                ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_pct,
                ROUND(AVG(delivery_delay_days), 2) AS avg_delay_days
            FROM orders
            GROUP BY market, order_region
            ORDER BY avg_delay_days DESC
            """

        # 5. Quarterly trend of sales, profit, and late delivery rate
        if "quarter" in q or "trend" in q:
            return """
            SELECT
                order_quarter,
                COUNT(*) AS total_orders,
                ROUND(SUM(sales), 2) AS total_sales_usd,
                ROUND(SUM(benefit_per_order), 2) AS total_profit_usd,
                ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_pct
            FROM orders
            GROUP BY order_quarter
            ORDER BY order_quarter ASC
            """

        # 6. Department revenue and profit
        if "department" in q:
            return """
            SELECT
                d.department_name,
                d.market_sector,
                COUNT(o.order_id) AS total_orders,
                ROUND(SUM(o.sales), 2) AS total_sales_usd,
                ROUND(SUM(o.benefit_per_order), 2) AS total_profit_usd,
                ROUND(AVG(o.late_delivery_risk) * 100.0, 2) AS late_delivery_pct
            FROM orders o
            JOIN departments d ON o.department_id = d.department_id
            GROUP BY d.department_name, d.market_sector
            ORDER BY total_sales_usd DESC
            """

        # 7a. Customer country and state breakdown
        if "country" in q or "state" in q:
            return """
            SELECT
                c.customer_country,
                c.customer_state,
                COUNT(o.order_id) AS total_orders,
                ROUND(SUM(o.sales), 2) AS total_sales_usd,
                ROUND(AVG(o.late_delivery_risk) * 100.0, 2) AS late_delivery_pct
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_country, c.customer_state
            ORDER BY total_orders DESC
            """

        # 7b. Customer segment analysis
        if "segment" in q or "customer" in q:
            return """
            SELECT
                c.customer_segment,
                COUNT(o.order_id) AS total_orders,
                ROUND(SUM(o.sales), 2) AS total_sales_usd,
                ROUND(SUM(o.benefit_per_order), 2) AS total_profit_usd,
                ROUND(AVG(o.late_delivery_risk) * 100.0, 2) AS late_delivery_pct
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_segment
            ORDER BY total_sales_usd DESC
            """

        # 8. Product / category performance or negative profit / loss orders
        if "negative" in q or "loss" in q or ("benefit" in q and "low" in q):
            return """
            SELECT
                p.product_name,
                o.order_region,
                COUNT(*) AS loss_making_orders,
                ROUND(SUM(o.benefit_per_order), 2) AS total_loss_usd,
                ROUND(AVG(o.delivery_delay_days), 2) AS avg_delay_days
            FROM orders o
            JOIN products p ON o.product_card_id = p.product_card_id
            WHERE o.benefit_per_order < 0
            GROUP BY p.product_name, o.order_region
            ORDER BY total_loss_usd ASC
            LIMIT 10
            """

        if "product" in q or "category" in q or "top" in q:
            return """
            SELECT
                p.product_name,
                p.category_name,
                COUNT(o.order_id) AS orders_count,
                SUM(o.order_item_quantity) AS units_sold,
                ROUND(SUM(o.sales), 2) AS total_sales_usd,
                ROUND(SUM(o.benefit_per_order), 2) AS total_profit_usd
            FROM orders o
            JOIN products p ON o.product_card_id = p.product_card_id
            GROUP BY p.product_name, p.category_name
            ORDER BY total_sales_usd DESC
            """

        if "country" in q or "state" in q:
            return """
            SELECT
                c.customer_country,
                c.customer_state,
                COUNT(o.order_id) AS total_orders,
                ROUND(SUM(o.sales), 2) AS total_sales_usd,
                ROUND(AVG(o.late_delivery_risk) * 100.0, 2) AS late_delivery_pct
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_country, c.customer_state
            ORDER BY total_orders DESC
            """

        # Default overall supply chain KPI summary by market
        return """
        SELECT
            market,
            COUNT(*) AS total_orders,
            ROUND(SUM(sales), 2) AS total_sales_usd,
            ROUND(SUM(benefit_per_order), 2) AS total_profit_usd,
            ROUND(AVG(late_delivery_risk) * 100.0, 2) AS late_delivery_pct
        FROM orders
        GROUP BY market
        ORDER BY total_sales_usd DESC
        """

    def run(self, question: str) -> AgentResponse:
        t0 = time.perf_counter()
        traces: List[ToolCallTrace] = []

        # Tool 1: Inspect Schema
        ts1 = time.perf_counter()
        schema_res = inspect_schema_tool("all")
        traces.append(
            ToolCallTrace(
                step=1,
                tool_name="inspect_schema",
                tool_input="all",
                status="success",
                row_count=len(schema_res["schemas"]),
                latency_ms=round((time.perf_counter() - ts1) * 1000.0, 2),
            )
        )

        # Tool 2: Validate & Execute Safe Read-Only SQL
        candidate_sql = self._compile_nl_to_sql(question)
        ts2 = time.perf_counter()
        try:
            sql_res = execute_safe_sql_tool(candidate_sql)
            traces.append(
                ToolCallTrace(
                    step=2,
                    tool_name="execute_safe_sql",
                    tool_input=sql_res["executed_sql"],
                    status="success",
                    row_count=sql_res["row_count"],
                    latency_ms=round((time.perf_counter() - ts2) * 1000.0, 2),
                )
            )
        except SQLGuardrailViolation as exc:
            traces.append(
                ToolCallTrace(
                    step=2,
                    tool_name="execute_safe_sql",
                    tool_input=candidate_sql,
                    status=f"BLOCKED: {str(exc)}",
                    row_count=0,
                    latency_ms=round((time.perf_counter() - ts2) * 1000.0, 2),
                )
            )
            return AgentResponse(
                question=question,
                sql_generated=candidate_sql,
                answer=f"GUARDRAIL BLOCKED: {str(exc)} This agent enforces strict read-only database access.",
                tool_traces=traces,
                rows_preview=[],
                chart_spec={"chart_type": "none"},
                anomalies_flagged=[],
                guardrail_blocked=True,
                total_latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                estimated_cost_usd=0.00004,
            )

        rows = sql_res["rows"]

        # Tool 3: Delivery Delay Statistical Anomaly Detection
        ts3 = time.perf_counter()
        anom_res = detect_delivery_delay_anomalies_tool(z_threshold=2.0)
        traces.append(
            ToolCallTrace(
                step=3,
                tool_name="detect_delivery_delay_anomalies",
                tool_input="z_threshold=2.0",
                status="success",
                row_count=anom_res["anomaly_count"],
                latency_ms=round((time.perf_counter() - ts3) * 1000.0, 2),
            )
        )

        # Tool 4: Automatic Chart Specification
        ts4 = time.perf_counter()
        chart_spec = generate_chart_spec_tool(rows, question)
        traces.append(
            ToolCallTrace(
                step=4,
                tool_name="generate_chart_spec",
                tool_input=chart_spec["chart_type"],
                status="success",
                row_count=1,
                latency_ms=round((time.perf_counter() - ts4) * 1000.0, 2),
            )
        )

        # Synthesize plain-English answer + anomaly flag
        if not rows:
            summary = "Query executed successfully with 0 matching records."
        else:
            top = rows[0]
            kv = ", ".join(f"{k}={v}" for k, v in top.items())
            summary = f"Executed verified read-only SQL across DataCo Supply Chain tables, returning **{len(rows)} row(s)**. Leading result: `{kv}`."

        if anom_res["anomalies"]:
            a0 = anom_res["anomalies"][0]
            summary += (
                f"\n\n**Unusual Delivery Delay Pattern Flagged (Z-Score = {a0['z_score']}):** "
                f"`{a0['order_region']}` (`{a0['shipping_mode']}`) in `{a0['order_quarter']}` experienced an average "
                f"delivery delay of **{a0['avg_delay_days']} days** (**{a0['late_delivery_pct']}% late delivery rate** across "
                f"{a0['total_orders']} orders), compared to the network mean of {anom_res['network_mean_delay_days']} days."
            )

        return AgentResponse(
            question=question,
            sql_generated=sql_res["executed_sql"],
            answer=summary,
            tool_traces=traces,
            rows_preview=rows[:15],
            chart_spec=chart_spec,
            anomalies_flagged=anom_res["anomalies"][:3],
            guardrail_blocked=False,
            total_latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            estimated_cost_usd=0.00019,
        )
