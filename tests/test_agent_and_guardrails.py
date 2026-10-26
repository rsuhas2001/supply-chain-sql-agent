import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.guardrails import validate_and_sanitize_sql, SQLGuardrailViolation
from app.tools import detect_delivery_delay_anomalies_tool
from app.agent import SupplyChainSQLAgent


class TestSupplyChainSQLAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SupplyChainSQLAgent()

    def test_valid_select_passes_and_caps_limit(self):
        sql, notes = validate_and_sanitize_sql("SELECT order_id, shipping_mode FROM orders")
        self.assertIn("LIMIT 100", sql)
        self.assertEqual(len(notes), 1)

        sql2, notes2 = validate_and_sanitize_sql("SELECT order_id FROM orders LIMIT 5000")
        self.assertIn("LIMIT 100", sql2)

    def test_ddl_dml_and_injection_queries_blocked(self):
        bad_queries = [
            "DROP TABLE orders",
            "DELETE FROM orders WHERE late_delivery_risk = 1",
            "UPDATE orders SET sales = 0",
            "SELECT * FROM orders; DROP TABLE customers",
            "SELECT * FROM orders -- inline comment",
            "SELECT * FROM unauthorized_table",
        ]
        for q in bad_queries:
            with self.subTest(query=q):
                with self.assertRaises(SQLGuardrailViolation):
                    validate_and_sanitize_sql(q)

    def test_southeast_asia_q3_delay_anomaly_flagged(self):
        data = detect_delivery_delay_anomalies_tool(z_threshold=2.0)
        self.assertGreaterEqual(data["anomaly_count"], 1)
        top = data["anomalies"][0]
        self.assertEqual(top["order_quarter"], "2026-Q3")
        self.assertEqual(top["order_region"], "Southeast Asia")
        self.assertGreaterEqual(top["z_score"], 2.5)

    def test_shipping_mode_late_deliveries_this_quarter_query(self):
        resp = self.agent.run("Which shipping mode has the most late deliveries this quarter?")
        self.assertFalse(resp.guardrail_blocked)
        self.assertEqual(resp.rows_preview[0]["shipping_mode"], "Standard Class")
        self.assertEqual(resp.chart_spec["chart_type"], "bar")


if __name__ == "__main__":
    unittest.main(verbosity=2)
